# MRI Explainability Pilot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Grad-CAM (live) + SHAP (on-demand) explanations to the MRI Swin classifier, wire the Grad-CAM evidence into the 3D brain view, and ship a faithfulness harness — as the reusable vertical-slice pattern for the other modalities.

**Architecture:** New `backend/apps/inference/explainers/` package (hook-based Grad-CAM + Captum GradientShap + shared helpers). Grad-CAM is computed **inline** in `analyze_mri` (cheap), persisted/served like the existing mask/overlay images. SHAP runs **on-demand** via a new `POST /api/mri/<pk>/explain/`. The frontend gets a Grad-CAM tab, an "Explain (SHAP)" button, and a second 3D focus marker driven by the backend-returned Grad-CAM peak. A `tools/eval_mri_explainer.py` harness reports Grad-CAM↔SHAP agreement, localization, and a deletion sanity-check.

**Tech Stack:** PyTorch + HuggingFace `transformers` (Swin-Tiny `SwinForImageClassification`), **Captum** (GradientShap), matplotlib (overlay figures), Django/DRF, React 19 + react-three-fiber, Vitest, scipy.

**Spec:** [docs/superpowers/specs/2026-06-17-mri-explainability-pilot-design.md](../specs/2026-06-17-mri-explainability-pilot-design.md)
**Branch:** `feat/mri-xai-pilot` (commits stay on this branch; do **not** push without asking).

---

## Key refinements from recon (read before starting)

- **Grad-CAM = hook-based** on `model.swin.layernorm` (final LayerNorm, `[B,L,C]`, C=768). Reshape `L=49 → 7×7`. Resolve the target layer **defensively** (`getattr`), and run the CAM forward/backward **outside** `torch.no_grad()` (the pipeline's classifier forward at `mri_pipeline.py:291` is under `no_grad`).
- **Grad-CAM only in `run_cls` modes** (`classify`/`full`), never `segment` — guard it, return `gradcam_path=None` otherwise (mirrors how cls fields are None when `run_cls` is False).
- **Result-envelope contract:** the inline Grad-CAM step gets its **own** try/except; failure sets `gradcam_path=None` and the result still returns `status='success'`. Never raise into the view.
- **Wiring a gradcam image touches 4 backend places:** pipeline (produce abs path) → model (`result_gradcam_path` CharField + migration) → view (`_relative_to_media` store + delete-cleanup) → serializer (`gradcam_url` SerializerMethodField). All PHI media goes through `signed_media_url` — never a raw `/media/` URL.
- **The 3D peak is returned NUMERICALLY by the backend** as normalized `{nx, ny}` in `[0,1]` (avoid the client-side canvas/CORS-taint fragility recon flagged). The frontend applies the **existing** projection `x:(nx-0.5)*1.7, y:(0.5-ny)*1.3` (note the **flipped Y** and per-axis scales) — the same formula the mask centroid uses at `MRIResult.jsx:110-112`.
- **LGG GT masks are absent** (`data/` has only `brain-tumor-mri/`, `hms/`, `samples/`). Localization metric defaults to the **U-Net predicted mask** on `brain-tumor-mri`; LGG GT is an optional positional arg that errors clearly if absent.
- **`MRIResult.jsx` is a LIGHT-ERA file** — keep `text-gray-*`/`bg-card`; do **not** add `useTokens`/neon. Accent for the new 3D marker lives in `Anatomy3DPanel`/`Brain3D` (which already use `useTokens`). Every new i18n key goes in **both** en and fr trees.

---

## Phase 1 — Backend explainer core

### Task 1: Hook-based Grad-CAM for the Swin classifier

**Files:**
- Create: `backend/apps/inference/explainers/__init__.py`
- Create: `backend/apps/inference/explainers/gradcam.py`
- Test: `backend/tests/test_explainers.py`

- [ ] **Step 1: Write the failing test** (weight-requiring; runs with the pipeline suite, not CI)

```python
# backend/tests/test_explainers.py
import numpy as np
from PIL import Image
from django.test import SimpleTestCase
from apps.inference.model_loader import ModelLoader
from apps.inference.explainers.gradcam import swin_gradcam

class GradCamTest(SimpleTestCase):
    def test_gradcam_shape_and_range(self):
        processor, model = ModelLoader().get_mri_classifier()
        img = Image.fromarray((np.random.rand(224, 224, 3) * 255).astype("uint8"))
        cam, idx, conf, peak = swin_gradcam(processor, model, img)
        self.assertEqual(cam.ndim, 2)
        self.assertGreaterEqual(cam.min(), 0.0)
        self.assertLessEqual(cam.max(), 1.0 + 1e-6)
        self.assertIn(idx, range(model.config.num_labels))
        self.assertTrue(0.0 <= peak[0] <= 1.0 and 0.0 <= peak[1] <= 1.0)
```

- [ ] **Step 2: Run it, verify it fails** — `cd backend && python -m pytest tests/test_explainers.py -k gradcam -v` (or `python manage.py test tests.test_explainers`). Expected: `ModuleNotFoundError: apps.inference.explainers`.

- [ ] **Step 3: Create the package + implementation**

```python
# backend/apps/inference/explainers/__init__.py
"""Post-hoc explainers (Grad-CAM, SHAP) for the deployed models. MRI first."""
```

```python
# backend/apps/inference/explainers/gradcam.py
"""Hook-based Grad-CAM for the HuggingFace Swin MRI classifier.

Swin's final LayerNorm emits a token sequence [B, L, C] (L = 7*7 for 224px input),
so a plain CNN Grad-CAM does not apply: we fold L back to a 7x7 grid, weight channels
by their mean gradient, ReLU, and normalise to [0,1]. The forward/backward run OUTSIDE
torch.no_grad() (the pipeline's classifier forward is under no_grad and cannot backprop).
"""
import numpy as np
import torch


def _resolve_target_layer(model):
    swin = getattr(model, "swin", model)
    layer = getattr(swin, "layernorm", None)
    if layer is None:
        raise RuntimeError("Grad-CAM: could not resolve Swin target layer (model.swin.layernorm)")
    return layer


def swin_gradcam(processor, model, pil_image, target_class=None):
    """Return (heatmap[h,w] float32 in [0,1], pred_idx, confidence, peak (nx,ny) in [0,1])."""
    device = next(model.parameters()).device
    inputs = processor(images=pil_image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    target_layer = _resolve_target_layer(model)

    store = {}
    h_fwd = target_layer.register_forward_hook(lambda m, i, o: store.__setitem__("act", o))
    h_bwd = target_layer.register_full_backward_hook(lambda m, gi, go: store.__setitem__("grad", go[0]))
    try:
        model.zero_grad(set_to_none=True)
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        idx = int(probs.argmax(dim=-1).item()) if target_class is None else int(target_class)
        conf = float(probs[0, idx].item())
        logits[0, idx].backward()
        act = store["act"].detach()[0]    # (L, C)
        grad = store["grad"].detach()[0]  # (L, C)
    finally:
        h_fwd.remove()
        h_bwd.remove()

    L, _ = act.shape
    side = int(round(L ** 0.5))
    if side * side != L:
        raise RuntimeError(f"Grad-CAM: token length {L} is not a square grid")
    weights = grad.mean(dim=0)                       # (C,)
    cam = torch.relu((act * weights).sum(dim=-1)).reshape(side, side)
    cam = cam - cam.min()
    cam = (cam / (cam.max() + 1e-8)).cpu().numpy().astype(np.float32)
    py, px = np.unravel_index(int(cam.argmax()), cam.shape)
    peak = ((px + 0.5) / side, (py + 0.5) / side)    # normalized (nx, ny)
    return cam, idx, conf, peak
```

- [ ] **Step 4: Run it, verify it passes** — same command. Expected: PASS (downloads Swin weights on first run, ~minutes).

- [ ] **Step 5: Commit** — `git add backend/apps/inference/explainers backend/tests/test_explainers.py && git commit -m "feat(mri-xai): hook-based Grad-CAM for the Swin classifier"`

---

### Task 2: SHAP via Captum GradientShap

**Files:**
- Modify: `backend/requirements.txt` (add `captum`)
- Create: `backend/apps/inference/explainers/shap_attr.py`
- Test: `backend/tests/test_explainers.py` (add a case)

- [ ] **Step 1: Add the dependency** — append `captum>=0.7,<0.8` to `backend/requirements.txt` (the heavy-ML file), then `pip install -r backend/requirements.txt`.

- [ ] **Step 2: Write the failing test**

```python
# add to backend/tests/test_explainers.py
from apps.inference.explainers.shap_attr import swin_gradient_shap

class ShapTest(SimpleTestCase):
    def test_shap_shape_and_range(self):
        processor, model = ModelLoader().get_mri_classifier()
        img = Image.fromarray((np.random.rand(224, 224, 3) * 255).astype("uint8"))
        attr = swin_gradient_shap(processor, model, img, target_class=0, n_samples=4)
        self.assertEqual(attr.ndim, 2)
        self.assertGreaterEqual(attr.min(), 0.0)
        self.assertLessEqual(attr.max(), 1.0 + 1e-6)
```

- [ ] **Step 3: Run it, verify it fails** — `ModuleNotFoundError: apps.inference.explainers.shap_attr`.

- [ ] **Step 4: Implement**

```python
# backend/apps/inference/explainers/shap_attr.py
"""SHAP attribution (Captum GradientShap) for the Swin MRI classifier.

GradientShap is the fast, faithful, gradient-based SHAP variant — appropriate for a deep
net and our synchronous CPU path (unlike KernelSHAP/LIME). Pixel attributions are reduced
to a [H,W] saliency map (abs sum over channels), normalised to [0,1].
"""
import numpy as np
import torch
from captum.attr import GradientShap


def swin_gradient_shap(processor, model, pil_image, target_class, n_samples=32):
    """Return a [H,W] float32 saliency map in [0,1] for `target_class`."""
    device = next(model.parameters()).device
    px = processor(images=pil_image, return_tensors="pt")["pixel_values"].to(device)

    def forward(pixel_values):
        return model(pixel_values=pixel_values).logits

    baselines = torch.cat([torch.zeros_like(px), torch.full_like(px, float(px.mean()))], dim=0)
    attr = GradientShap(forward).attribute(
        px, baselines=baselines, target=int(target_class), n_samples=int(n_samples), stdevs=0.09)
    a = attr.detach()[0].abs().sum(dim=0)            # (H, W)
    a = a - a.min()
    return (a / (a.max() + 1e-8)).cpu().numpy().astype(np.float32)
```

- [ ] **Step 5: Run it, verify it passes; then commit** — `git add backend/requirements.txt backend/apps/inference/explainers/shap_attr.py backend/tests/test_explainers.py && git commit -m "feat(mri-xai): Captum GradientShap attribution for the Swin classifier"`

---

### Task 3: Shared helpers — overlay figure, peak, agreement (CI-friendly, no weights)

**Files:**
- Create: `backend/apps/inference/explainers/base.py`
- Test: `backend/tests/test_explainers_base.py`

- [ ] **Step 1: Write the failing test** (pure numpy/scipy — runs in CI)

```python
# backend/tests/test_explainers_base.py
import numpy as np
from django.test import SimpleTestCase
from apps.inference.explainers.base import attribution_agreement, resize_to

class AgreementTest(SimpleTestCase):
    def test_identical_maps_agree(self):
        a = np.random.rand(7, 7).astype("float32")
        out = attribution_agreement(a, a.copy())
        self.assertAlmostEqual(out["spearman"], 1.0, places=5)
        self.assertAlmostEqual(out["topk_iou"], 1.0, places=5)

    def test_resize_changes_shape_only(self):
        a = np.random.rand(7, 7).astype("float32")
        b = resize_to(a, (224, 224))
        self.assertEqual(b.shape, (224, 224))
```

- [ ] **Step 2: Run it, verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/apps/inference/explainers/base.py
"""Shared explainer helpers: heatmap resize, overlay figure, peak, agreement metrics."""
import numpy as np


def resize_to(arr, shape):
    """Nearest-neighbour resize a 2D map to `shape` (H, W) without extra deps."""
    from PIL import Image
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype("uint8"))
    im = im.resize((shape[1], shape[0]), Image.BILINEAR)
    return (np.asarray(im, dtype=np.float32) / 255.0)


def heatmap_peak_xy(cam):
    """Argmax of a 2D heatmap as normalized (nx, ny) in [0,1]."""
    h, w = cam.shape
    py, px = np.unravel_index(int(np.asarray(cam).argmax()), cam.shape)
    return ((px + 0.5) / w, (py + 0.5) / h)


def attribution_agreement(a, b, topk_frac=0.1):
    """Spearman rank-corr + top-k IoU between two heatmaps (resized to `a`'s shape)."""
    from scipy.stats import spearmanr
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if b.shape != a.shape:
        b = resize_to(b, a.shape)
    af, bf = a.ravel(), b.ravel()
    rho = spearmanr(af, bf).correlation
    k = max(1, int(len(af) * topk_frac))
    ta, tb = set(np.argsort(af)[-k:]), set(np.argsort(bf)[-k:])
    iou = len(ta & tb) / len(ta | tb)
    return {"spearman": float(0.0 if rho != rho else rho), "topk_iou": float(iou)}


def gradcam_overlay_figure(image_rgb, cam):
    """matplotlib Figure: original image with a jet heatmap overlaid (mirrors the red-overlay
    pattern at mri_pipeline.py:344-360). Caller saves it via utils.save_visualization."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h, w = image_rgb.shape[:2]
    cam_up = resize_to(cam, (h, w))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.imshow(image_rgb)
    ax.imshow(cam_up, cmap="jet", alpha=0.40)
    ax.axis("off")
    return fig
```

- [ ] **Step 4: Run it, verify it passes** — `cd backend && python manage.py test tests.test_explainers_base`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add backend/apps/inference/explainers/base.py backend/tests/test_explainers_base.py && git commit -m "feat(mri-xai): shared explainer helpers (overlay, peak, agreement)"`

---

## Phase 2 — Inline Grad-CAM in the pipeline + persistence

### Task 4: Compute Grad-CAM inline in `analyze_mri`

**Files:**
- Modify: `backend/apps/inference/mri_pipeline.py` (defaults block ~210-222; inside `run_cls` after the forward ~295; success dict ~444-467)
- Test: `backend/tests/test_pipelines.py` (MRI pipeline test — weight-requiring)

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/test_pipelines.py MRIPipelineTest
def test_classify_emits_gradcam_path(self):
    result = analyze_mri(self.sample_image_path, mode="classify")
    self.assertEqual(result["status"], "success")
    self.assertIn("gradcam_path", result)
    self.assertTrue(result["gradcam_path"] is None or result["gradcam_path"].endswith("_gradcam.png"))
```

- [ ] **Step 2: Run it, verify it fails** — `KeyError: 'gradcam_path'`.

- [ ] **Step 3: Implement.** In the mode-agnostic defaults (~`mri_pipeline.py:210-222`) add `gradcam_path = None`. Immediately after the classifier forward block (`mri_pipeline.py:295`), inside `if run_cls:`, add:

```python
        # --- explainability: Grad-CAM overlay (best-effort; never breaks inference) ---
        try:
            from .explainers.gradcam import swin_gradcam
            from .explainers.base import gradcam_overlay_figure
            cam, _cam_idx, _cam_conf, cam_peak = swin_gradcam(processor, vit, crop_pil, target_class=pred_idx)
            fig_g = gradcam_overlay_figure(crop_arr, cam)
            gradcam_path = save_visualization(fig_g, MRI_RESULTS_DIR, f"{timestamp}_gradcam.png")
            plt.close(fig_g)
            gradcam_peak = {"nx": float(cam_peak[0]), "ny": float(cam_peak[1])}
        except Exception as e:  # noqa: BLE001 — explanation must never break the result envelope
            logger.warning("Grad-CAM failed (%s); continuing without it", e)
            gradcam_path, gradcam_peak = None, None
```

Add `gradcam_peak = None` to the defaults block too. Then in the success dict (`mri_pipeline.py:444-467`) add `'gradcam_path': gradcam_path,` and `'gradcam_peak': gradcam_peak,` next to `'overlay_path'`.

- [ ] **Step 4: Run it, verify it passes** — `cd backend && python manage.py test tests.test_pipelines.MRIPipelineTest.test_classify_emits_gradcam_path`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add backend/apps/inference/mri_pipeline.py backend/tests/test_pipelines.py && git commit -m "feat(mri-xai): compute Grad-CAM overlay inline in analyze_mri"`

---

### Task 5: Persist & serve the Grad-CAM image (model + view + serializer)

**Files:**
- Modify: `backend/apps/mri/models.py:27-29` (add field) + new migration
- Modify: `backend/apps/mri/views.py:174-176` (store) and `:225-233` (delete-cleanup)
- Modify: `backend/apps/mri/serializers.py` (add `gradcam_url` + Meta)
- Test: `backend/tests/test_mri_explain.py` (serializer field — CI-friendly DB test)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mri_explain.py
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from apps.mri.serializers import MRIAnalysisSerializer

class GradcamUrlFieldTest(TestCase):
    def test_serializer_exposes_gradcam_url_key(self):
        self.assertIn("gradcam_url", MRIAnalysisSerializer().fields)
```

- [ ] **Step 2: Run it, verify it fails** — `AssertionError: 'gradcam_url' not found`.

- [ ] **Step 3: Implement (four mirror-edits).**

`models.py` (after `result_overlay_path`): `result_gradcam_path = models.CharField(max_length=500, null=True, blank=True)`

`serializers.py` — add method + register in `Meta.fields` and `read_only_fields`:
```python
    gradcam_url = serializers.SerializerMethodField()

    def get_gradcam_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.result_gradcam_path)
```

`views.py` success branch (after `:176`): `analysis.result_gradcam_path = _relative_to_media(result.get('gradcam_path'))`
`views.py` `perform_destroy` artifact loop (`:225-233`): include `instance.result_gradcam_path` among the paths removed.

- [ ] **Step 4: Make + apply the migration** — `cd backend && python manage.py makemigrations mri && python manage.py migrate`. Then run the test: `python manage.py test tests.test_mri_explain`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add backend/apps/mri && git commit -m "feat(mri-xai): persist + serve the Grad-CAM overlay (gradcam_url)"`

---

## Phase 3 — On-demand SHAP endpoint

### Task 6: `explain_mri()` pipeline function

**Files:**
- Modify: `backend/apps/inference/mri_pipeline.py` (new function) and `backend/apps/inference/__init__.py:10-19` (export)
- Test: `backend/tests/test_pipelines.py` (weight-requiring)

- [ ] **Step 1: Write the failing test**

```python
def test_explain_mri_envelope(self):
    out = explain_mri(self.sample_image_path)
    self.assertIn(out["status"], ("success", "failed"))
    if out["status"] == "success":
        for k in ("gradcam_path", "shap_path", "peak", "agreement"):
            self.assertIn(k, out)
        self.assertIn("spearman", out["agreement"])
```

- [ ] **Step 2: Run it, verify it fails** — `NameError: explain_mri`.

- [ ] **Step 3: Implement** a new top-level function in `mri_pipeline.py` that returns the `{status, ...}` envelope (own try/except), reusing `load_image_universal`, the HF processor, `swin_gradcam`, `swin_gradient_shap`, `gradcam_overlay_figure`, `attribution_agreement`, `save_visualization`:

```python
def explain_mri(file_path: str):
    """On-demand Grad-CAM + SHAP for one MRI image. Returns the {status,...} envelope."""
    try:
        import matplotlib.pyplot as plt
        from PIL import Image
        from .explainers.gradcam import swin_gradcam
        from .explainers.shap_attr import swin_gradient_shap
        from .explainers.base import gradcam_overlay_figure, attribution_agreement, resize_to
        loader = ModelLoader()
        processor, vit = loader.get_mri_classifier()
        image_rgb = load_image_universal(file_path)
        pil = Image.fromarray(image_rgb)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(MRI_RESULTS_DIR, exist_ok=True)

        cam, idx, conf, peak = swin_gradcam(processor, vit, pil)
        fig_g = gradcam_overlay_figure(image_rgb, cam)
        gradcam_path = save_visualization(fig_g, MRI_RESULTS_DIR, f"{timestamp}_gradcam.png"); plt.close(fig_g)

        shap_map = swin_gradient_shap(processor, vit, pil, target_class=idx)
        fig_s = gradcam_overlay_figure(image_rgb, shap_map)
        shap_path = save_visualization(fig_s, MRI_RESULTS_DIR, f"{timestamp}_shap.png"); plt.close(fig_s)

        agreement = attribution_agreement(resize_to(cam, shap_map.shape), shap_map)
        return {"status": "success", "gradcam_path": gradcam_path, "shap_path": shap_path,
                "peak": {"nx": float(peak[0]), "ny": float(peak[1])},
                "predicted_class": int(idx), "confidence": float(conf), "agreement": agreement}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e), "error_type": type(e).__name__}
```

Add `explain_mri` to `apps/inference/__init__.py` imports and `__all__`.

- [ ] **Step 4: Run it, verify it passes** — `python manage.py test tests.test_pipelines.MRIPipelineTest.test_explain_mri_envelope`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add backend/apps/inference && git commit -m "feat(mri-xai): explain_mri() on-demand Grad-CAM+SHAP pipeline function"`

---

### Task 7: `MRIExplainView` endpoint with doctor isolation

**Files:**
- Modify: `backend/apps/mri/views.py` (new view) and `backend/apps/mri/urls.py:3,7-11`
- Test: `backend/tests/test_mri_explain.py` (isolation — CI-friendly)

- [ ] **Step 1: Write the failing test** (404 for another doctor's record — the isolation contract)

```python
# add to backend/tests/test_mri_explain.py — build two doctors + one analysis (reuse helpers
# from tests/test_doctor_isolation.py for user/patient/analysis creation).
def test_explain_is_doctor_isolated(self):
    other = self.make_doctor("other@test.com")
    self.client.force_authenticate(other)
    resp = self.client.post(f"/api/mri/{self.analysis.pk}/explain/")
    self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run it, verify it fails** — 404 route missing or wrong status.

- [ ] **Step 3: Implement the view** (mirror `MRIUploadView` APIView style; isolation in the queryset):

```python
class MRIExplainView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        analysis = get_object_or_404(MRIAnalysis, pk=pk, patient__doctor=request.user)
        if not analysis.file:
            return Response({"detail": "No image on this analysis."}, status=400)
        result = run_inference_with_timeout(explain_mri, analysis.file.path)
        if result.get("status") != "success":
            return Response(result, status=502)
        for k in ("gradcam_path", "shap_path"):
            result[k] = signed_media_url(request, _relative_to_media(result[k]))
        return Response(result, status=200)
```

Import `explain_mri`, `signed_media_url`, `get_object_or_404` as needed. Add the route to `urls.py`: `path('<int:pk>/explain/', MRIExplainView.as_view(), name='explain')`, and add `MRIExplainView` to the `from .views import ...` line.

- [ ] **Step 4: Run it, verify it passes** — `cd backend && python manage.py test tests.test_mri_explain`. Expected: PASS (isolation test is DB-only, no weights).

- [ ] **Step 5: Commit** — `git add backend/apps/mri && git commit -m "feat(mri-xai): POST /api/mri/<pk>/explain/ (doctor-isolated)"`

---

## Phase 4 — Frontend

### Task 8: Service call + Grad-CAM tab + "Explain (SHAP)" button + i18n

**Files:**
- Modify: `frontend/src/services/mriService.js:23`
- Modify: `frontend/src/modules/MRI/MRIResult.jsx` (TAB_IDS:20; activeUrl:144; action area ~244/271-288)
- Modify: `frontend/src/i18n/locales/mri.js` (en `:2-104` + fr `:105-206`)
- Test: manual + lint/build (Vitest covers logic in Task 9)

- [ ] **Step 1: Add the service method** — in `mriService.js`: `explainMri: (id) => api.post(`/mri/${id}/explain/`).then((r) => r.data),`

- [ ] **Step 2: Grad-CAM tab** — add `'gradcam'` to `TAB_IDS` (only render the tab when `mri.gradcam_url` is truthy); extend `activeUrl` (`:144`): `... : tab === 'gradcam' ? mri.gradcam_url : ...`. Add `mri.result.tabs.gradcam` to **both** en and fr in `mri.js`.

- [ ] **Step 3: Explain button** — in the action row (mirror the Save button classes `inline-flex items-center gap-2 ... px-4 py-2 rounded-lg text-sm font-medium` and the `disabled={mri.status !== 'completed'}` gate). On click: `const ex = await mriService.explainMri(mri.id)`; store in state; show the SHAP overlay image (`ex.shap_path`) and `ex.agreement.spearman` (e.g. `t('mri.explain.agreement', { rho: … })`). Handle loading + error (toast `t('mri.explain.failed')`). Add `mri.explain.*` keys to **both** en and fr.

- [ ] **Step 4: Verify** — `cd frontend && npm run lint && npm run build`. Expected: exit 0.

- [ ] **Step 5: Commit** — `git add frontend/src/services/mriService.js frontend/src/modules/MRI/MRIResult.jsx frontend/src/i18n/locales/mri.js && git commit -m "feat(mri-xai): Grad-CAM tab + SHAP explain button (frontend)"`

---

### Task 9: Wire the Grad-CAM peak into the 3D brain

**Files:**
- Modify: `frontend/src/modules/MRI/mriAnatomy.js:19-43`
- Modify: `frontend/src/modules/MRI/mriAnatomy.test.js`
- Modify: `frontend/src/components/three/Anatomy3DPanel.jsx:28-46` and `Brain3D.jsx` (2nd marker)
- Modify: `frontend/src/modules/MRI/MRIResult.jsx:124` (pass 3rd arg) + i18n

- [ ] **Step 1: Write the failing test** (Vitest — pure function)

```js
// add to frontend/src/modules/MRI/mriAnatomy.test.js
it('emits gradcamFocus when a peak is supplied', () => {
  const h = mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'glioma' }, null,
                              { x: 0.2, y: -0.1 });
  expect(h.gradcamFocus).toEqual({ x: 0.2, y: -0.1, severity: 'high' });
});
```

- [ ] **Step 2: Run it, verify it fails** — `cd frontend && npm test -- mriAnatomy`. Expected: FAIL (`gradcamFocus` undefined).

- [ ] **Step 3: Implement.** Extend the signature to `mapMriToHighlight(mri, maskInfo = null, gradcamPeak = null)` and, when `gradcamPeak` is present, attach `gradcamFocus: { x: gradcamPeak.x, y: gradcamPeak.y, severity: 'high' }` to the returned descriptor in **both** the segmentation and classifier branches. In `MRIResult.jsx`: add `const [gradcamPeak, setGradcamPeak] = useState(null)`, set it from the explain response (`ex.peak` → project with the **same** formula: `{ x: (ex.peak.nx - 0.5) * 1.7, y: (0.5 - ex.peak.ny) * 1.3 }`), and pass it: `mapMriToHighlight(mri, maskInfo, gradcamPeak)` (`:124`). In `Anatomy3DPanel.jsx` map `highlight.gradcamFocus` → `m.gradcamFocus` (parallel to `m.focus`, distinct color e.g. `colors.cardio` to differentiate from the mask focus). In `Brain3D.jsx` add a second marker ref + `<mesh>` (mirror `:259-261`) + an `applyFocus` call (`:230`) for `highlight.gradcamFocus`. Add a legend line `t('anatomy3d.gradcamLooked')` (en+fr) distinguishing "where the classifier looked" from the U-Net mask focus.

- [ ] **Step 4: Run it, verify it passes; lint/build** — `npm test -- mriAnatomy && npm run lint && npm run build`. Expected: PASS / exit 0.

- [ ] **Step 5: Commit** — `git add frontend/src && git commit -m "feat(mri-xai): show the Grad-CAM peak as a second 3D brain marker"`

---

## Phase 5 — Faithfulness harness

### Task 10: `tools/eval_mri_explainer.py`

**Files:**
- Create: `tools/eval_mri_explainer.py`
- (Docs follow-up: add a row to `maybe read/VALIDATION.md` once numbers exist — not in this plan.)

- [ ] **Step 1: Implement the harness.** Model the CLI on `eval_mri_segmentation.py` (positional `data_dir`, `--limit`, `--from-cache`, **no** `--seed`). Reuse helpers via `sys.path.insert(0, tools)` then `from eval_mri_classifier import CLASSES, iter_images, normalize_label, truth_from_path`. Get models via `ModelLoader().get_mri_classifier()` + (for localization) `get_mri_segmentation_model()`. For each image: run `swin_gradcam` + `swin_gradient_shap`, compute:
  1. **agreement** — `attribution_agreement(resize_to(cam, shap.shape), shap)` (no masks needed; works on `data/brain-tumor-mri`).
  2. **localization** — resize CAM to the mask frame; `peak_in_mask = mask[peak_y, peak_x]`. Mask source: **U-Net predicted mask** (default, present data) OR **LGG GT mask** when a `--lgg-root <path>` is given (reuse `find_pairs` + `gt = np.array(Image.open(m).convert("L")) > 127`); restrict to tumor-positive slices.
  3. **deletion** (optional `--deletion`) — zero the top-10% CAM pixels in the input, re-run the classifier, record the confidence drop.
  Cache `list[dict]` to `tools/mri_explainer.json` (schema `{name, truth, pred, spearman, topk_iou, peak_in_mask, conf_drop}`), support `--from-cache`. Print a summary (mean agreement, peak-in-mask rate over positive slices, mean conf-drop). Docstring states plainly it needs `data/brain-tumor-mri` (always) and optionally the LGG dataset for GT-mask localization, erroring clearly if a requested source is absent.

- [ ] **Step 2: Smoke-run** — `python tools/eval_mri_explainer.py data/brain-tumor-mri/Testing --limit 20`. Expected: prints agreement + (U-Net) localization summary; writes `tools/mri_explainer.json`.

- [ ] **Step 3: Commit** — `git add tools/eval_mri_explainer.py && git commit -m "feat(mri-xai): faithfulness harness (Grad-CAM<->SHAP agreement, localization, deletion)"`

---

## Self-review (done by author)

- **Spec coverage:** §3 explainers module → T1–T3; §4 inline+on-demand → T4–T7; §5 3D wiring → T9; §6 faithfulness → T10; §7 UI → T8–T9; §8 contracts (envelope/isolation/theme/i18n) → enforced in T4/T7/T8/T9; §9 testing → tests in every task. No spec section is unimplemented.
- **Placeholders:** none — every code step shows real code; mechanical mirror-edits cite the exact existing lines.
- **Type/name consistency:** `swin_gradcam`/`swin_gradient_shap`/`attribution_agreement`/`resize_to`/`gradcam_overlay_figure`/`explain_mri`/`MRIExplainView`/`result_gradcam_path`/`gradcam_url`/`gradcamFocus`/`gradcamPeak` are used consistently across tasks. Peak is normalized `{nx,ny}` backend-side, projected to `{x,y}` frontend-side via the existing formula.
- **Known risks flagged in-plan:** Swin target-layer name (resolved defensively), LGG masks absent (U-Net-predicted-mask default), `no_grad` (separate CAM forward), `captum` new dep.
