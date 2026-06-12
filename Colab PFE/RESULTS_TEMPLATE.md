# Colab Results — paste back to Claude

Fill one section per notebook you ran (each notebook's last cell prints a
"=== RESULTS ===" block — paste it raw under the matching heading, plus answer
the two questions). Then give this whole file (or just the filled sections)
back to Claude, who will integrate the new weights locally and re-validate.

---

## 1. EEG full fine-tune (`colab_eeg_full_finetune.ipynb`)

**Paste the RESULTS block here:**

```
(paste)
```

- Did the run finish all epochs, or hit the Colab time limit? →
- Downloaded `biot_iiic.pt` from `My Drive/colab_pfe_outputs/eeg/` and placed it at `backend/models_weights/biot/biot_iiic.pt`? (yes/no) →

---

## 2. MRI ViT fine-tune (`colab_mri_vit_finetune.ipynb`)

**Paste the RESULTS block here:**

```
(paste)
```

- Final test accuracy vs the 0.804 baseline: →
- Downloaded + unzipped the model folder into `backend/models_weights/vit_brain_tumor/`? (yes/no) →

---

## 3. ECG per-pathology fine-tune (`colab_ecg_finetune.ipynb`)

**Paste the RESULTS block (the before/after table) here:**

```
(paste)
```

- Which pathologies beat the baseline (got a saved checkpoint)? →
- Copied the kept `<PATHOLOGY>.pt` files into `backend/models_weights/ecg_finetuned/`? (yes/no) →

---

## After pasting

Claude will then, locally:
1. re-run `tools/eval_eeg.py`, `tools/eval_mri_classifier.py`, `tools/eval_ecg_classifier.py` to confirm the new numbers on this machine,
2. re-run the pipeline test suite,
3. update `VALIDATION.md`, `README.md`, and `Mazen_PFE/` docs with the new, verified numbers.
