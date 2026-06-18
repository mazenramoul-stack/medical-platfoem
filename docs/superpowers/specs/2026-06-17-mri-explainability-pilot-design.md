# MRI Explainability Pilot — Design Spec

**Date:** 2026-06-17
**Status:** Approved (design); pre-implementation
**Branch:** `feat/mri-xai-pilot`
**Author:** Mazen + Claude

## 1. Goal & scope

Add **explainable-AI (XAI)** to the platform: faithful, citable explanations of *why* each
model predicted what it did, **and** wire those explanations into the existing 3D anatomy
views so the highlighting reflects the model's actual evidence (goal **C** — explanations as
a feature *and* in the 3D).

This spec covers the **MRI modality only** — the deliberate **vertical-slice pilot**. It
establishes the reusable pattern (an `explainers/` package, the inline+on-demand flow, the
3D-wiring contract, the faithfulness harness). ECG, EEG, and Echo are **follow-on specs**
that reuse this pattern; they are **out of scope here**.

### Honest framing (constraints that shaped the design)
- The 3D meshes ([Brain3D.jsx](../../../frontend/src/components/three/Brain3D.jsx) etc.) are
  **generic procedural anatomy**, not patient reconstructions. XAI makes the *highlight*
  evidence-grounded; it does **not** make the mesh patient-accurate. "Accurate" here =
  *"the glow reflects where the model actually looked."*
- Inference is **synchronous in the request thread** on **CPU**, no queue. This is why heavy
  XAI is opt-in (see §4).

## 2. Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Methods | **Grad-CAM** (live driver) + **Captum GradientShap** (citable "SHAP"; DeepLift-SHAP as fallback if GradientShap is unstable on Swin) | Grad-CAM is sub-second & faithful for the Swin classifier; SHAP gives the named method for the thesis; their **agreement** is a faithfulness argument. |
| LIME / KernelSHAP | **Deferred** to offline report figures only (if a supervisor demands LIME by name) | Too slow (10–60 s/image) for a synchronous CPU path, and less faithful for deep nets. |
| Library | **Captum** (`LayerGradCam` + `GradientShap`) | One PyTorch-native dep for both methods; cleaner than `pytorch-grad-cam` + `shap`. |
| Run model | **Hybrid** — Grad-CAM inline (always), SHAP on-demand | Keeps the upload path fast; SHAP is the "click to dig deeper" view. |
| 3D marker priority | **U-Net mask wins when present**; Grad-CAM peak fills in when absent | The mask is a real segmentation; Grad-CAM corroborates it (or flags disagreement). |
| Faithfulness ground truth | **LGG GT masks** where available, else the **U-Net predicted mask** on the Kaggle set | Uses existing data; the GT-mask version is the rigorous "does the classifier look at the lesion" metric. |
| Retraining | **None** — reuse `get_mri_classifier()` (Swin) and the existing U-Net | XAI is post-hoc on the deployed models. |

## 3. Architecture

New package mirroring the pipeline structure:

```
backend/apps/inference/explainers/
  __init__.py
  base.py            # shared helpers: tensor prep, colormap overlay, peak→coords, agreement metrics
  mri_explainer.py   # gradcam(), gradient_shap(), explain_mri() orchestrator
```

- Reuses `model_loader.get_mri_classifier()` (Swin-T). **Swin Grad-CAM detail:** target the
  last stage's feature map; supply Captum a `reshape_transform` to recover the 7×7 spatial grid.
- `gradcam(model, x, target_class) -> np.ndarray[H,W] in [0,1]`.
- `gradient_shap(model, x, target_class, baselines) -> np.ndarray[H,W]` (baselines: black +
  blurred variants of the input).
- `explain_mri(image_path, want_shap=False) -> {gradcam, shap?, peak_xy, agreement?}` — pure-ish,
  returns arrays + the derived peak; the **view/pipeline** handles PNG persistence + URLs.

## 4. Data flow (hybrid)

**Inline (always, cheap):** in the MRI pipeline, after the Swin prediction, compute Grad-CAM
for the predicted class → save a colormapped **overlay PNG** to media (same mechanism as
existing result images) → add to the result dict:
```
result["explanation"] = {"gradcam_url": <signed url>, "peak": {"x":…, "y":…},
                         "method": "grad-cam", "target_class": <label>}
```
**Hard contract:** wrap the whole explanation step in `try/except`; on any failure the field
is **omitted** and inference proceeds — this preserves the *pipeline result envelope*
(`{status, …, error?}`) which must never raise into the view.

**On-demand (SHAP, ~seconds):** new endpoint
```
POST /api/mri/<id>/explain/
```
→ loads the stored image for analysis `<id>`, runs GradientShap + recomputes Grad-CAM,
computes agreement, returns `{shap_url, gradcam_url, agreement:{spearman, topk_iou}}`.
**Doctor isolation enforced:** the queryset filters by the requesting doctor (FK chain
`MRIAnalysis → patient → doctor`); a result belonging to another doctor returns 404.

## 5. 3D wiring

Extend [mapMriToHighlight](../../../frontend/src/modules/MRI/mriAnatomy.js) to accept an
optional `gradcamPeak {x,y}`:
- **Mask present:** keep the mask-derived `focus` marker as the localizer; attach
  `explanation: { source: 'unet-mask', gradcamAgrees: <bool> }` so the panel can note
  corroboration (or flag disagreement).
- **No mask:** use `gradcamPeak` as the `focus` marker (`source: 'grad-cam'`) — strictly
  better than today's whole-cerebrum glow.
- [Anatomy3DPanel.jsx](../../../frontend/src/components/three/Anatomy3DPanel.jsx) legend gains
  a line distinguishing *"where the classifier looked (Grad-CAM)"* vs *"tumour segmentation
  (U-Net)"*, keeping the existing 2D→3D projection caveat. Follow
  [THEME-I18N-CONVENTIONS.md](../../../frontend/THEME-I18N-CONVENTIONS.md) (tokens + EN/FR keys).

## 6. Faithfulness harness (thesis rigor)

`tools/eval_mri_explainer.py` (mirrors `tools/eval_*.py`), over a test set → numbers for
VALIDATION.md:
1. **Grad-CAM ↔ SHAP agreement** — Spearman rank-corr + top-k region IoU (method robustness).
2. **Localization (the strong metric)** — pointing-game accuracy / IoU of the Grad-CAM peak
   region vs a tumour mask (LGG GT masks; else the U-Net predicted mask on Kaggle). Answers
   *"does the classifier attend to the lesion, not an artifact?"*
3. **Deletion sanity check** (optional) — masking the top-attributed region drops predicted
   confidence → attribution is causal.

## 7. UI

[MRIResult.jsx](../../../frontend/src/modules/MRI/MRIResult.jsx):
- Grad-CAM overlay rendered beside the existing `Anatomy3DPanel` (from the inline field).
- An **"Explain (SHAP)"** button → calls the on-demand endpoint → renders the SHAP overlay +
  the agreement number. Loading/empty/error states handled (the endpoint can take a few seconds).
- Functional component; reuse the axios service + JWT pattern in `services/`.

## 8. Contracts to preserve

- **Pipeline result envelope** — explanation never raises into the view (try/except, omit on fail).
- **Doctor isolation** — the explain endpoint filters by requesting doctor.
- **Theme + i18n** — new UI strings get EN/FR keys; colors via `useTokens`.
- **CI** — explainer tests need the Swin weights, so they run with the weight-requiring suite
  (`manage.py test tests.test_pipelines`-style), **not** in CI (which is weight-free).

## 9. Testing

- Unit: `gradcam()`/`gradient_shap()` return `[H,W]` in `[0,1]`, deterministic for fixed input.
- Unit: `mapMriToHighlight` with/without `gradcamPeak` (extend `mriAnatomy.test.js`, Vitest).
- API: explain endpoint enforces doctor isolation (DB-backed test, in-memory SQLite).
- Harness smoke: `eval_mri_explainer.py --limit N` runs end-to-end on a few images.

## 10. Out of scope (explicit)

- ECG / EEG / Echo explainers — **follow-on specs** reusing this pattern.
- LIME / KernelSHAP in the live path (offline report figures only, if required).
- Any model retraining; any change to make the 3D mesh patient-specific (would need 3D
  segmentation/registration — a separate project).

## 11. Open assumptions to verify during planning

- LGG GT masks present under `data/` (else metric #2 uses the U-Net predicted mask).
- Captum installs cleanly on the pinned torch/Python (3.10/3.11) stack.
- The Swin target layer + `reshape_transform` produce a sensible CAM (verify on one image early).
