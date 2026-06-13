# Colab PFE — the GPU fixes

This folder contains **one self-contained Colab notebook per fix that needs a
GPU**, plus the helpers around them. Run them on Google Colab (free T4 is
enough), bring the outputs back, and the local code picks them up
automatically — the loaders were already patched to auto-detect the improved
weights.

> **Workflow:** run notebook → last cell prints a `=== RESULTS ===` block →
> paste it into [RESULTS_TEMPLATE.md](RESULTS_TEMPLATE.md) → give it back to
> Claude → local re-validation + docs update.

---

## 0. One-time setup

1. **Kaggle token** (MRI + EEG notebooks; ECG needs none — PTB-XL comes from
   PhysioNet directly). A **new-style token** (`KGAT_…`, from kaggle.com →
   *Settings* → *API*) is all you need — paste it when the credentials cell
   prompts you; no username, no `kaggle.json`. (A legacy `kaggle.json` also
   still works: press Enter at the prompt and upload it instead.) For EEG you
   must also **accept the rules** of the
   [HMS competition](https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification)
   once, on the Kaggle website, with the same account the token belongs to.
2. **Lean repo zip on Drive** (needed by the EEG and ECG notebooks; the MRI
   one is fully self-contained):

   ```bash
   python "Colab PFE/make_lean_zip.py"     # from the project root
   ```

   then upload the produced `medical-platform.zip` (~30–60 MB) to the **root**
   of your Google Drive.
3. In every notebook: *Runtime → Change runtime type → T4 GPU*.

---

## 1. The three fixes — honest targets

| # | Notebook | Fixes | Baseline → realistic target | ~T4 runtime |
|---|---|---|---|---|
| 1 | `colab_eeg_full_finetune.ipynb` | EEG balanced-acc 0.278 (frozen encoder, CPU subset) | **0.278 → 0.45–0.55** balanced accuracy | hours (the long one — see the timeout note inside) |
| 2 | `colab_mri_vit_finetune.ipynb` | MRI Swin 4-class accuracy (the `vit` in the notebook name is historical; the model is a Swin-T) | **0.804 → 0.92–0.97** — ✅ **DONE June 11 2026: 0.9544 on Colab, re-verified 95.4 % locally** | ~30–60 min |
| 3 | `colab_ecg_finetune.ipynb` | ECG weak-class F1 / macro balanced-acc | ✅ **DONE June 11 2026: 3/7 kept (1AVB, RBBB, PVC) — verified locally: macro F1 0.711→0.727, mean AUC 0.980, macro bal-acc 0.887; under the notebook's bal-acc objective: 0.942→0.946** | ~1–3 h (actual: 155 min) |

### Why EEG cannot reach 90–95 % — read this before the defence

The IIIC task (6-class harmful-brain-activity) is **not like the MRI task**.
Even *expert neurologists disagree with each other* on these labels — the
ictal–interictal continuum is genuinely ambiguous, which is why the field
scores it with balanced accuracy and Cohen's κ against *consensus* labels.
BIOT's own published full-data result is ≈ 0.5 balanced accuracy, and that is
considered strong. A model claiming 90 % on IIIC would mean it out-performs
the inter-rater agreement of the experts who created the labels — a red flag
for leakage, not a result. The honest, defensible claim after this notebook:
**“the full GPU fine-tune lifts our screening head from 0.28 to ≈ 0.5
balanced accuracy, matching the encoder authors' published level.”**

### Why there is no Echo or U-Net notebook

- **Echo** (EF MAE 4.01 %, R² 0.831 on 400 TEST videos; Dice 0.897) already matches the published
  EchoNet-Dynamic paper. It is a regression task — “percent accuracy” does
  not apply, and there is nothing for a GPU to win back.
- **MRI U-Net segmentation** (Dice 0.852) is within a few points of the source
  paper's ≈ 0.89, and the gap is a normalisation detail, not missing training.
  Dice is not “accuracy”; retraining risks the provenance story for marginal
  gain.

---

## 2. What comes back, and where it goes

| Notebook | Drive output | Place it locally at | Auto-detected by |
|---|---|---|---|
| EEG | `colab_pfe_outputs/eeg/biot_iiic.pt` (+ metrics json) | `backend/models_weights/biot/biot_iiic.pt` (replace) | already supported — `get_eeg_model()` loads full checkpoints |
| MRI | `colab_pfe_outputs/mri_vit/vit_brain_tumor.zip` | unzip → `backend/models_weights/vit_brain_tumor/` | `get_mri_classifier()` (new auto-detect; `VIT_BRAIN_TUMOR_WEIGHTS` overrides) |
| ECG | `colab_pfe_outputs/ecg_finetuned/<PATHOLOGY>.pt` (only the ones that beat baseline) | `backend/models_weights/ecg_finetuned/` | `get_ecg_models()` (new auto-detect; `ECG_FINETUNED_DIR` overrides) |

No weights present → the platform behaves exactly as before (verified by the
pipeline test suite). Each fix is fully independent: you can run one, two, or
all three, in any order.

---

## 3. After you paste the results back

Claude will re-run the local eval harnesses (`tools/eval_eeg.py`,
`tools/eval_mri_classifier.py`, `tools/eval_ecg_classifier.py`) so every new
number is **verified on this machine, not just trusted from Colab**, re-run
the pipeline tests, and update `VALIDATION.md` / `README.md` /
`Mazen_PFE/` with the new figures.
