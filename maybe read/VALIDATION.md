# Model Validation Report

> Scope note (read first). This platform runs four **independent** pretrained
> pipelines (brain-MRI, 12-lead ECG, echocardiography, and EEG) and concatenates
> their outputs into one PDF. It does **not** model any neuro-cardiac correlation: the
> "combined interpretation" is rule-based template text, not a learned or measured
> link between modalities. No paired multi-modality dataset exists in this project,
> so a cross-modal correlation cannot be — and is not — reported here. That
> correlation is stated as a hypothesis / future work.

Reproduce all ECG numbers with:
```
python tools/eval_ecg_classifier.py --ptbxl <PTB-XL root> --tune-fold 9 --fold 10
```
Reproduce MRI numbers with:
```
python tools/eval_mri_classifier.py <Kaggle Brain-Tumor Testing dir>
python tools/eval_mri_segmentation.py <LGG root>
```
Reproduce Echo numbers with:
```
python tools/eval_echo.py <EchoNet-Dynamic root>
```
Reproduce EEG numbers with (after fine-tuning the IIIC head — see §5):
```
python tools/train_eeg_head.py --hms-dir <HMS dir> --limit 4000 --epochs 80
python tools/eval_eeg.py --hms-dir <HMS dir> --weights backend/models_weights/biot/biot_iiic.pt
```

---

## 0. Safety-first operating points — minimizing false negatives (June 2026)

A screening tool must not MISS a sick patient: a false negative (telling a
patient they are fine when they are not) is far costlier than a false positive
(an extra review). On that requirement, the **decision threshold / decision
rule — not the model weights — is the lever**, so every change below is a
local re-calibration (no GPU retraining). Each is tuned on a validation fold and
reported on a held-out test fold, and each states the **precision cost** paid for
the higher recall.

| Modality | Clinically-critical "don't-miss" recall | Result | False negatives | Precision cost |
|---|---|---|---|---|
| **ECG** (7 pathologies) | per-pathology detection recall on PTB-XL fold 10 | **all 7 ≥ 0.95** (macro recall **0.982**) | **13** / 2,198 records (was ~62 at F1 thresholds) | macro precision **0.35** (was 0.69) — flags liberally |
| **MRI** (tumour vs healthy) | of 1,200 tumour images, fraction NOT called `notumor` | **0.998** (gate 0.99); **1.000** at gate 1.0 | **2** of 1,200 (gate 0.99); **0** at gate 1.0 | 2/400 healthy flagged (gate 0.99); 17/400 (gate 1.0) |
| **EEG** (IIIC screen) | abnormal-vs-benign detection recall on HMS held-out (n=1,883) | **0.931** (seizures routed **0.966** ✓) | 128 / 1,850 abnormal windows | precision **0.98**; specificity ≈0 (cannot rule out benign) |
| **Echo** (reduced EF) | reduced-EF (EF<50 %) detection recall on EchoNet TEST | **0.952** at +5 % margin (flag EF<55 %) | 4 / 83 reduced studies (was 18 at no margin) | precision **0.68** (margin trades false alarms for safety) |

**ECG, MRI and Echo need no GPU** — all three reach ≥0.95 on the don't-miss
metric by moving the operating point on the existing models. **EEG is the honest
exception:** seizure-routing recall (0.966) clears the bar, but the *general*
abnormal-vs-benign screen (0.931) falls just short, because this head has almost
no benign specificity (it gets 0/33 true-`Other` windows right — Other recall
0.000). Two routes to ≥0.95 general screen recall, both with real costs: (a)
route every non-confident `Other` as a flag — pushes recall → ~1.0 but flags
essentially everything (no filtering value); or (b) the **GPU full fine-tune**
(the pending `Colab PFE/colab_eeg_full_finetune.ipynb`) to improve benign
discrimination — the one place GPU work is genuinely warranted. Even then, 6-way
*type* recall (seizure-vs-GPD-vs-…) stays unreachable: IIIC is inter-rater-
ambiguous (expert κ ≈ 0.5), so 0.95 type recall is not achievable by anyone.
Per-modality detail and reproduce commands are in each section below.

> **Two ECG operating points ship** (switch via `ECG_THRESHOLD_MODE`):
> `recall` (default — the safety-first thresholds in this section) and `f1` (the
> balanced macro-F1 0.727 set from §1). `tools/tune_ecg_recall.py` reproduces the
> recall set; `tools/eval_mri_recall.py`, `tools/eval_echo_recall.py`, and
> `tools/eval_eeg.py` reproduce the others.

---

## 0.5 Statistical robustness — bootstrap 95% CIs (June 2026)

Headline numbers are single-split point estimates; to show they are stable (not lucky
splits) every one carries a **95% confidence interval** from 2,000 bootstrap resamples
of the *cached per-record predictions* (no model re-run needed). Reproduce:
`python tools/bootstrap_cis.py --boot 2000 --seed 0`.

| Modality | Metric | Point | 95% CI |
|---|---|---:|---|
| MRI | 4-class accuracy (n=1,600) | 95.4% | **[94.3, 96.4]** |
| MRI | macro F1 (4-class) | 0.954 | [0.942, 0.963] |
| MRI | tumour-detection recall (gate 0.99) | 0.998 | [0.996, 1.000] |
| ECG | macro ROC-AUC (PTB-XL fold 10, n=2,198) | 0.980 | **[0.973, 0.985]** |
| ECG | macro recall (recall-first) | 0.982 | [0.972, 0.992] |
| Echo | EF MAE (n=400) | 4.01% | **[3.68, 4.35]** |
| Echo | EF R² | 0.831 | [0.789, 0.863] |
| Echo | reduced-EF recall (flag EF<55) | 0.952 | [0.898, 0.989] |
| EEG | balanced accuracy (n=1,883) | 0.278 | **[0.257, 0.299]** |

**EEG above-chance significance.** A permutation test (2,000 label shuffles) puts the
6-class chance line at ~0.167 (95th percentile 0.186); the observed **0.278** sits well
outside it: **p = 0.0005**. So the IIIC head is **significantly above chance** — it is
genuinely learning, not noise — even though it is far from the ~0.5 frozen-encoder
ceiling. The CIs are all narrow, confirming the headline numbers are statistically
stable. (Per-pathology ECG AUCs with CIs are printed by the script, e.g. SBRAD
0.950 [0.913, 0.974], RBBB 0.995 [0.992, 0.997].)

---

## 1. ECG pathology classification (ecglib DenseNet-1D, 7 models)

**Dataset:** PTB-XL (PhysioNet v1.0.3), official held-out **test fold 10**.
**Labels:** SCP codes mapped to the 7 ecglib pathologies; a present code = positive.
**Decision thresholds:** tuned per pathology on **fold 9 (validation)** to maximize
F1, then applied unchanged to fold 10 (no test-set leakage).

> **June 2026 — fine-tuned checkpoints now deployed (3 of 7).** Per-pathology
> continue-training on Colab T4 (`Colab PFE/colab_ecg_finetune.ipynb`, folds 1–8,
> early-stop on fold 9) produced checkpoints that beat baseline for **1AVB, RBBB
> and PVC**; a no-regression rule kept the stock weights for the other four.
> They live in `backend/models_weights/ecg_finetuned/` (auto-detected by
> `get_ecg_models()`; `ECG_FINETUNED_DIR` overrides) and the pipeline thresholds
> were re-tuned for the new ensemble. **Verified locally June 11 2026** with this
> same harness — the Colab-reported AUCs reproduced exactly (1AVB 0.972,
> RBBB 0.995, PVC 0.993).

> **Report-grade results: full PTB-XL fold 10 — 2,198 test records** (tuned on
> 2,183 validation records from fold 9). Reproduce: same command, no `--limit`.

### Per-pathology metrics — current (fine-tuned ensemble, test fold 10, tuned thresholds)

| Pathology | Support | AUC | Balanced Acc | Sensitivity | Specificity | Precision | F1 |
|-----------|--------:|----:|-------------:|------------:|------------:|----------:|---:|
| AFIB    | 152 | 0.975 | 0.920 | 0.855 | 0.985 | 0.812 | 0.833 |
| 1AVB ★  |  79 | 0.972 | 0.883 | 0.797 | 0.969 | 0.488 | 0.606 |
| STACH   |  82 | 0.990 | 0.813 | 0.634 | 0.991 | 0.743 | 0.684 |
| SBRAD   |  64 | 0.950 | 0.769 | 0.562 | 0.976 | 0.409 | 0.474 |
| RBBB ★  | 166 | 0.995 | 0.925 | 0.861 | 0.989 | 0.867 | 0.864 |
| LBBB    |  62 | 0.982 | 0.962 | 0.935 | 0.988 | 0.699 | 0.800 |
| PVC ★   | 114 | 0.993 | 0.936 | 0.886 | 0.986 | 0.777 | 0.828 |

★ = fine-tuned checkpoint (June 2026). The headline win is **1AVB: F1
0.521 → 0.606** (precision 0.41 → 0.49, sensitivity 0.71 → 0.80); RBBB gains
+0.020 F1 and PVC +0.007. SBRAD stays the weakest class (its fine-tune did not
beat baseline and was not kept) — still precision-limited despite AUC 0.95.

### Aggregate metrics — current (fine-tuned ensemble; stock baseline in parentheses)

| Metric | Value |
|---|---|
| Mean ROC-AUC | **0.980** (0.978) |
| Macro F1 | **0.727** (0.711) |
| Micro F1 | 0.755 (0.740) |
| Weighted F1 | 0.763 (0.748) |
| **Macro balanced accuracy** | **0.887** (0.884) — 0.50 = trivial all-negative model |
| Subset / exact-match accuracy | 0.848 (0.831) |
| Jaccard (example-based) | 0.866 (0.852) |
| Hamming loss (lower better) | 0.025 (0.027) |

### Stock-baseline per-pathology metrics (pre-fine-tune, kept for the thesis)

| Pathology | Support | AUC | Balanced Acc | Sensitivity | Specificity | Precision | F1 |
|-----------|--------:|----:|-------------:|------------:|------------:|----------:|---:|
| AFIB  | 152 | 0.975 | 0.920 | 0.855 | 0.985 | 0.812 | 0.833 |
| 1AVB  |  79 | 0.960 | 0.836 | 0.709 | 0.962 | 0.412 | 0.521 |
| STACH |  82 | 0.990 | 0.813 | 0.634 | 0.991 | 0.743 | 0.684 |
| SBRAD |  64 | 0.950 | 0.769 | 0.562 | 0.976 | 0.409 | 0.474 |
| RBBB  | 166 | 0.993 | 0.947 | 0.916 | 0.979 | 0.784 | 0.844 |
| LBBB  |  62 | 0.982 | 0.962 | 0.935 | 0.988 | 0.699 | 0.800 |
| PVC   | 114 | 0.992 | 0.944 | 0.904 | 0.984 | 0.752 | 0.821 |

(Stock thresholds were AFIB 0.89, 1AVB 0.96, STACH 0.97, SBRAD 0.97, RBBB 0.94,
LBBB 0.99, PVC 0.69. The deployed thresholds for the fine-tuned ensemble live in
`apps/inference/ecg_pipeline.py` — notably PVC moved to 0.96 because its
fine-tuned model is calibrated higher.)

### Threshold calibration (engineering contribution)

The original pipeline used a flat 0.5 cut-off, which over-flagged badly. Tuning a
per-pathology threshold (validation fold only) raises performance with **no
retraining**. Current ensemble (June 2026):

| Average | Before (0.5) | After (tuned) | Δ |
|---|---|---|---|
| Macro F1 | 0.544 | 0.727 | **+0.183** |
| Micro F1 | 0.534 | 0.755 | **+0.221** |
| Weighted F1 | 0.614 | 0.763 | **+0.149** |

(Same experiment on the stock models: macro F1 0.514 → 0.711, micro
0.503 → 0.740, weighted 0.580 → 0.748.) ROC-AUC is unchanged
(threshold-independent), confirming the gain is calibration, not a different
model.

### Recall-first operating point (safety-first / screening — default since June 2026)

For the "never miss a positive" requirement (see §0) the thresholds are lowered
to guarantee **recall ≥ 0.95 per pathology on the held-out test fold**. Tuned to
recall ≥ 0.98 on fold 9 (a safety margin so test recall clears 0.95), reported on
fold 10. Reproduce: `python tools/tune_ecg_recall.py --target 0.98`.

| Pathology | thr | Recall | Precision | Specificity | F1 | FN | FP |
|-----------|----:|-------:|----------:|------------:|---:|---:|---:|
| AFIB  | 0.10 | 0.961 | 0.338 | 0.860 | 0.500 |  6 | 286 |
| 1AVB  | 0.12 | 0.975 | 0.137 | 0.772 | 0.241 |  2 | 484 |
| STACH | 0.26 | 0.988 | 0.259 | 0.890 | 0.410 |  1 | 232 |
| SBRAD | 0.18 | 0.984 | 0.139 | 0.817 | 0.243 |  1 | 391 |
| RBBB  | 0.43 | 0.994 | 0.583 | 0.942 | 0.735 |  1 | 118 |
| LBBB  | 0.66 | 0.984 | 0.296 | 0.932 | 0.455 |  1 | 145 |
| PVC   | 0.49 | 0.991 | 0.685 | 0.975 | 0.810 |  1 |  52 |

**Macro recall 0.982** (all classes ≥ 0.95), **only 13 false negatives** across
2,198 records — versus ~62 at the F1-balanced thresholds. **The cost is
precision: macro 0.35** (vs 0.69), i.e. 1,708 false positives — the tool flags
liberally for human review. This is the deliberate screening posture; the
balanced operating point above (macro F1 0.727, precision 0.69) is one
`ECG_THRESHOLD_MODE=f1` away for contexts where over-flagging is costlier than a
miss. Both are honest, leakage-free calibrations of the same models.

### A note on the two "macro F1" numbers (don't mix them up)

The Colab fine-tune notebook reports macro F1 ≈ 0.57 → 0.60 — *lower* than the
0.711/0.727 here. That is **not** a contradiction: the notebook tunes its
thresholds to maximize **balanced accuracy** (its model-selection metric), while
this report and the deployed pipeline tune thresholds to maximize **F1**. Same
models, same fold-10 records, different threshold objective. The numbers in this
file are the deployment-relevant ones; under the notebook's balanced-accuracy
objective the same ensemble scores macro balanced-acc 0.946.

### Why not headline "accuracy"?
Under class imbalance, plain accuracy is inflated (an all-negative predictor
already scores ~95–99%). Therefore we report **balanced accuracy, AUC, F1,
sensitivity and specificity** against a majority-class baseline. Macro balanced
accuracy of **0.887** (vs a 0.50 floor) shows the models detect pathologies
genuinely, not by exploiting prevalence.

---

## 2. MRI tumor-type classification (Swin Transformer (Swin-T), 4-class)

**Dataset:** Kaggle "Brain Tumor MRI Dataset" (Nickparvar), held-out **`Testing/`
split, 1,600 images (400 per class)**. The Swin Transformer (Swin-T) was trained on the `Training/`
split, so `Testing/` is a fair held-out evaluation.
**Evaluated on the full image** (the Kaggle set ships no masks to crop with). The
deployed pipeline *does* crop to the U-Net bounding box when segmentation flags a
tumour (crop-then-classify); that path's accuracy delta is unmeasured here.

> **June 2026 — fine-tuned weights now deployed.** The stock hub model scored
> **80.4 %**; after a 6-epoch continue-train on the `Training/` split (Colab T4,
> `Colab PFE/colab_mri_vit_finetune.ipynb`), the deployed model scores
> **95.4 %**. Both result sets are kept below. The fine-tuned checkpoint lives in
> `backend/models_weights/vit_brain_tumor/` (the folder name is historical; the
> model is a Swin-T — base backbone `microsoft/swin-tiny-patch4-window7-224`,
> ~28 M params, ~110 MB on disk) (auto-detected by
> `get_mri_classifier()`); identical preprocessing and label mapping, verified
> locally with this same harness.

### Overall — current (fine-tuned, verified locally June 11 2026)

| Metric | Value |
|---|---|
| Accuracy | **95.4 %** (1527/1600) |
| Macro F1 | **0.954** |
| Mean confidence | 0.990 |

### Per-class — current (fine-tuned)

| Class | Precision | Recall | F1 | Support |
|-----------|----------:|-------:|---:|--------:|
| glioma     | 0.997 | 0.833 | 0.907 | 400 |
| meningioma | 0.888 | 0.990 | 0.936 | 400 |
| notumor    | 0.952 | 1.000 | 0.976 | 400 |
| pituitary  | 0.995 | 0.995 | 0.995 | 400 |

### Confusion matrix — current (rows = truth, cols = predicted)

| truth \ pred | glioma | meningioma | notumor | pituitary |
|---|---:|---:|---:|---:|
| **glioma**     | 333 |  48 |  19 |   0 |
| **meningioma** |   1 | 396 |   1 |   2 |
| **notumor**    |   0 |   0 | 400 |   0 |
| **pituitary**  |   0 |   2 |   0 | 398 |

**Interpretation (fine-tuned).** The pituitary confusion that dominated the stock
model is gone (recall 0.995); the remaining weakness is **glioma recall (0.83)** —
48 gliomas still read as meningioma, a clinically related distinction. Training
used only the `Training/` split with the platform's exact preprocessing and the
original label order, so the comparison to the 80.4 % baseline is apples-to-apples.

### Tumour-detection recall — the clinical "don't-miss" metric (safety gate)

4-class accuracy is the wrong lens for false-negative safety: confusing glioma
with meningioma is not a clinical miss (both are tumours → the patient is still
referred). The catastrophic false negative is a tumour labelled **`notumor`**.
Measured on the 1,600-image Testing split (`tools/eval_mri_recall.py`):

| Decision rule | Tumour-detection recall | Tumours missed (of 1,200) | Healthy scans flagged (of 400) |
|---|---:|---:|---:|
| Plain argmax (baseline) | 0.983 | 20 | 0 |
| notumor-confidence gate ≥ 0.90 | 0.993 | 9 | 0 |
| **notumor gate ≥ 0.99 (deployed default)** | **0.998** | **2** | 2 |
| notumor gate = 1.0 (absolute zero-miss) | 1.000 | 0 | 17 |

The deployed pipeline accepts a `notumor` verdict only when the Swin is ≥ 0.99
confident **and** the U-Net found no tissue; otherwise it raises a
`screening_flag` ("possible tumour — review"). This lifts tumour-detection recall
0.983 → 0.998 at a cost of ~2 false alarms per 400 healthy scans; the U-Net
cross-check can only raise it further. Set `NOTUMOR_MIN_CONFIDENCE = 1.0` in
`mri_pipeline.py` for literal zero misses at a ~4 %/scan over-flag rate.

### Baseline — stock hub model (pre-fine-tune, for the record)

| Metric | Value |
|---|---|
| Accuracy | 80.4 % (1286/1600) |
| Macro F1 | 0.794 |
| Mean confidence | 0.890 |

| Class | Precision | Recall | F1 | Support |
|-----------|----------:|-------:|---:|--------:|
| glioma     | 0.981 | 0.517 | 0.678 | 400 |
| meningioma | 0.856 | 0.698 | 0.769 | 400 |
| notumor    | 0.891 | 1.000 | 0.942 | 400 |
| pituitary  | 0.651 | 1.000 | 0.789 | 400 |

| truth \ pred | glioma | meningioma | notumor | pituitary |
|---|---:|---:|---:|---:|
| **glioma**     | 207 |  47 |  37 | 109 |
| **meningioma** |   4 | 279 |  12 | 105 |
| **notumor**    |   0 |   0 | 400 |   0 |
| **pituitary**  |   0 |   0 |   0 | 400 |

The stock model's weak point was **glioma (recall 0.52)** — 109 gliomas and 105
meningiomas were misclassified as pituitary. Its 80.4 % was far below the model
card's headline (~99 %) because it ran on the full image with the platform's
preprocessing; the fine-tune closed that gap under the same conditions.

## 3. MRI tumor segmentation (U-Net)

**Status: WORKING (fixed).** Previously the network appeared to saturate (marked
~100% of every image as tumour). Root cause was a **double-sigmoid bug**: the
`mateuszbuda/brain-segmentation-pytorch` U-Net applies sigmoid inside its
`forward()`, but the pipeline applied `torch.sigmoid()` again, squashing the
[0,1] probability map into [0.5, 0.73] so every pixel crossed the 0.5 threshold.
Removing the redundant sigmoid restored the model.

**Dataset:** LGG MRI Segmentation (mateuszbuda/lgg-mri-segmentation), 3,929 slices
(1,373 tumour-positive, 2,556 empty), with ground-truth masks.

| Metric | All slices | Tumour-positive slices |
|---|---:|---:|
| **Dice coefficient** | 0.827 | **0.852** |
| IoU (Jaccard) | 0.802 | 0.781 |
| Saturated predictions | 0 % | — |

Dice 0.85 on tumour slices is close to the source paper's ~0.89 mean DSC (the gap
is per-image vs per-volume intensity normalisation). Before the fix, Dice was
~0.02 (100 % saturated). Reproduce: `python tools/eval_mri_segmentation.py <LGG root>`.

---

## 4. Echocardiography — EF + LV segmentation (EchoNet-Dynamic)

Two pretrained models (Ouyang et al., *Nature* 2020):
**R(2+1)D-18** for ejection-fraction (EF) regression and **DeepLabV3-ResNet50**
for left-ventricle segmentation. Input is an echo video; EF is averaged over
sampled 32-frame clips and segmentation locates end-diastole/end-systole.

**Dataset:** EchoNet-Dynamic (Stanford AIMI), official **TEST** split. EF measured
on **400 videos** (the committed `tools/echo_ef_pairs.json` artifact); segmentation
Dice on 30 human-traced ED/ES frames (VolumeTracings).

### Ejection fraction (regression)

The headline is the **400-video** figure. An earlier 40-video subset gave a more
flattering MAE (3.19 %); it is shown alongside only for transparency — the
400-video number is the one to quote.

| Metric | **400 videos (headline)** | 40-video subset |
|---|---|---|
| **MAE** | **4.01 %** | 3.19 % |
| RMSE | 5.30 % | 4.01 % |
| **R²** | **0.831** | 0.860 |

Reproduce both rows from the saved pairs: `python -c "import json,numpy as np;d=json.load(open('tools/echo_ef_pairs.json'));t,p=np.array(d['true']),np.array(d['pred']);print('MAE',np.abs(t-p).mean())"`.

### LV segmentation

| Metric | Value |
|---|---|
| **Dice** | **0.897** (n = 30 traced ED/ES frames) |

### Reduced-EF detection recall (the clinical "don't-miss" metric)

EF is a regression, so the false-negative framing is: never miss a patient with
**reduced** ejection fraction. We treat the regressor as a screen at the clinical
cutoffs (EF < 50 % = reduced; EF < 40 % = HFrEF) and flag with a safety margin,
because the regressor's ~4–5 % error otherwise misses borderline cases. Measured
on 400 TEST videos (`tools/eval_echo_recall.py`):

| Cutoff | Flag rule | Recall | Precision | Missed |
|---|---|---:|---:|---:|
| EF < 50 % | flag EF<50 (no margin) | 0.783 | 0.878 | 18 / 83 |
| EF < 50 % | **flag EF<55 (+5 % margin, deployed)** | **0.952** | 0.675 | **4 / 83** |
| EF < 40 % | flag EF<40 (no margin) | 0.857 | 0.894 | 7 / 49 |
| EF < 40 % | flag EF<46 (+6 % margin) | 0.980 | 0.774 | 1 / 49 |

The pipeline flags `reduced_ef_screen` when EF < 55 % (a +5 % safety margin over
the 50 % cutoff), lifting reduced-EF detection recall 0.78 → **0.95** — at the
cost of precision 0.88 → 0.68 (more borderline-normal studies routed for review).
`REDUCED_EF_SCREEN_CUTOFF` in `echo_pipeline.py` tunes the margin.

Both match the published EchoNet-Dynamic performance (MAE ≈ 4 %, Dice ≈ 0.92),
confirming the pretrained models run correctly in this pipeline. Numbers are on
TEST-split subsets (CPU inference is slow, ~10–40 s/video); rerun without
`--limit` for the full 1,277-video figure. Reproduce:
`python tools/eval_echo.py <EchoNet-Dynamic root>`.

> Note: the EchoNet **weights** are public (GitHub release, no agreement); the
> **dataset** requires a free Stanford AIMI research-use agreement.

---

## 5. EEG — harmful-brain-activity screening (BIOT / IIIC, 6-class)

**Model.** BIOT — Biosignal Transformer (Yang et al., NeurIPS 2023). BIOT releases
only a self-supervised **encoder** (`EEG-PREST-16-channels`, pretrained on 5M MGH
resting-EEG samples), **not** an IIIC classification head. We attach BIOT's own
`ClassificationHead` and fine-tune **only that head** on real IIIC labels (encoder
frozen). The encoder loads with a strict, byte-exact key match (0 missing / 0
unexpected), confirming the vendored model code matches the released checkpoint.

**Task.** The IIIC (Ictal–Interictal–Injury Continuum) 6-class scheme: **SZ, LPD,
GPD, LRDA, GRDA, Other**. The pipeline classifies every 10 s segment and aggregates
to per-class proportions, a dominant pattern, and a harmful-activity flag (any
SZ/LPD/GPD).

**Preprocessing (replicated from BIOT exactly, in `apps/inference/eeg_preprocess.py`).**
16-channel longitudinal-bipolar montage in BIOT's order, resample to 200 Hz, 10 s =
2000-sample segments, per-channel 95th-percentile amplitude normalisation
`x / (q95(|x|) + 1e-8)`. The same module is used by training, evaluation, and
inference, guaranteeing train/inference parity.

**Dataset.** Kaggle **"HMS — Harmful Brain Activity Classification"** — the public
IIIC task whose 6 expert **vote** columns line up 1:1 with the BIOT IIIC classes.
Evaluation uses a **patient-disjoint** held-out split (no patient in both train and
test). HMS labels are soft (vote distributions), so we also report KL divergence —
the competition's own metric.

### Results (real — 1,451-EEG subset, frozen encoder)

The head was fine-tuned on a **1,451-EEG balanced subset** of HMS (8,697 labelled
10 s windows; **6,814 train / 1,883 test, split by patient** so no patient appears in
both). The encoder is frozen; only the 6-class head is trained. Evaluated with
`tools/eval_eeg.py` on the patient-disjoint test split (n = 1,883):

| Metric | Value | Reference |
|---|---|---|
| **Balanced accuracy** | **0.278** | 0.167 = 6-class chance |
| **Cohen's κ** | **0.147** | 0 = chance agreement |
| **Macro F1** | **0.265** | — |
| Weighted F1 | 0.323 | — |
| **KL divergence** (true votes ‖ pred) | **1.333** | lower is better |
| Raw accuracy | 0.315 | misleading under imbalance — reported last |

### Per-class (test split, n = 1,883)

| Class | Precision | Recall | F1 | Support |
|-------|----------:|-------:|---:|--------:|
| SZ (Seizure, *harmful*)        | 0.181 | 0.388 | 0.247 | 116 |
| LPD (Lat. periodic, *harmful*) | 0.343 | 0.284 | 0.311 | 328 |
| GPD (Gen. periodic, *harmful*) | 0.410 | 0.463 | **0.435** | 408 |
| LRDA (Lat. rhythmic delta)     | 0.311 | 0.239 | 0.270 | 473 |
| GRDA (Gen. rhythmic delta)     | 0.372 | 0.291 | 0.327 | 525 |
| Other / background             | 0.000 | 0.000 | 0.000 |  33 |

### 6×6 confusion matrix (rows = true, cols = predicted)

| true \ pred | SZ | LPD | GPD | LRDA | GRDA | Other |
|---|---:|---:|---:|---:|---:|---:|
| **SZ**    | 45 | 16 |  21 |  15 |  15 |  4 |
| **LPD**   | 41 | 93 |  73 |  70 |  25 | 26 |
| **GPD**   | 48 | 19 | 189 |  15 |  94 | 43 |
| **LRDA**  | 74 | 76 |  66 | 113 | 115 | 29 |
| **GRDA**  | 36 | 53 | 107 | 150 | 153 | 26 |
| **Other** |  5 | 14 |   5 |   0 |   9 |  0 |

**Honest reading.** These are **above chance** (κ = 0.15, balanced-acc 1.7× the 0.167
floor) but **modest**, and this 1,883-window evaluation is the **more reliable**
estimate — an earlier 396-EEG run scored 0.31 balanced-acc on only 303 test windows,
which was small-sample optimism. The key finding: **3.7× more data did not move the
headline** (it converged to ~0.28). That is the signature of a **frozen-encoder
ceiling** — a tiny linear head on fixed features plateaus regardless of data volume.
The generalized patterns (GPD F1 0.44, GRDA, LRDA) now classify best given their
larger support; the rare **Other** class (n = 33) collapses to zero, and **SZ**
precision is low — both symptoms of class imbalance the small head can't overcome.

**The real lever is unfreezing the encoder (full fine-tune), which needs a GPU.**
BIOT's published IIIC-range numbers (~0.5 balanced-acc) come from fine-tuning the
*whole* model, not just a head on frozen features. On CPU that is impractical; on a
free GPU (Colab/Kaggle) it is ~30–60 min. The harness is ready for more data; an
`--unfreeze` full-fine-tune mode is the documented next step.

### Screening recall — the false-negative metric (June 2026)

6-way *type* accuracy is the wrong lens for "don't miss a sick patient": what
matters for a screen is whether a window with **any** harmful IIIC pattern gets
routed to a neurologist, not which exact pattern is named. Collapsing the 6 classes
to **abnormal (any of the 5) vs Other** on the same n=1,883 split:

| Screen metric | Value |
|---|---|
| Abnormal-detection **recall** | **0.931** (128 / 1,850 harmful windows missed as 'Other') |
| Abnormal-detection precision | 0.981 |
| Benign specificity (Other correct) | ≈0.000 (0 / 33 — the head cannot identify benign) |
| **Seizure routed for review** (flagged as *some* IIIC pattern) | **112 / 116 = 0.966** ✓ |

**Honest reading.** The single most dangerous miss — a **seizure** read as benign —
is covered (routing recall 0.966 ≥ 0.95). The *general* abnormal screen (0.931)
sits just under 0.95 because the frozen-head model has essentially **no benign
specificity** (Other recall 0.000): it almost never confidently clears a window,
so it errs toward flagging — the safe direction, but it provides little filtering.
Reaching ≥0.95 *general* screen recall has two honest routes, both costly: route
every low-confidence `Other` as a flag (recall → ~1.0 but flags ~everything), or
**unfreeze the encoder on a GPU** to actually learn benign vs abnormal — the one
place GPU work is warranted here. The pipeline exposes this as `screen_positive`.
Reproduce: same command as below (the binary-screen block prints after the matrix).

Reproduce exactly:
```
python tools/train_eeg_head.py --hms-dir data/hms --limit 12000 --epochs 60 --weight-decay 3e-4 --seed 0
python tools/eval_eeg.py --hms-dir data/hms --weights backend/models_weights/biot/biot_iiic.pt --limit 12000 --seed 0
```
(The fine-tuned `biot_iiic.pt` is **not committed** — it is git-ignored. Until it is
present, `model_loader.get_eeg_model()` raises a clear `FileNotFoundError`, mirroring
the EchoNet "weights not bundled" pattern, so the endpoint fails honestly rather than
serving an untrained head.)

> Honest scope: this is **functional** screening for harmful brain activity — the
> complement to the structural MRI tumour analysis — **not** a tumour detector. IIIC
> is critical-care EEG from a **general critically-ill cohort**, not a tumour cohort;
> SZ/LPD are the focal/ictal patterns a tumour is *one* of several causes of.

---

## 6. Limitations (all evidence-based)

1. **No true multimodal integration.** MRI and ECG are analysed independently;
   the "combined interpretation" is rule-based template text. No neuro-cardiac
   correlation is modelled or measured.
2. **Train/test overlap — checked, no meaningful leakage.** ecglib was trained on a
   large unpublished corpus that *may* include PTB-XL, which could in principle make
   the fold-10 AUC optimistic. To rule this out, the frozen ensemble was evaluated on
   the **PTB-XL-independent Chapman-Shaoxing-Ningbo** database (PhysioNet
   `ecg-arrhythmia`) via `tools/eval_ecg_external.py`: **macro AUC 0.973** — essentially
   identical to the PTB-XL value (~0.98), so the model genuinely generalises and the
   AUC is **not** inflated by leakage. (Report-grade streamed sample of **n=1500**,
   `--stream 1500 --seed 42`, all records usable; every pathology now has real support —
   per-pathology AUC 0.90–0.99, e.g. SBRAD n=550/0.992, STACH n=239/0.989, AFIB n=76/0.904,
   LBBB n=20/0.986 — macro balanced-acc 0.913, mean recall 0.962. This supersedes the
   earlier n=150 indicative run, macro AUC 0.981. The June fine-tune is independently
   leakage-free anyway: it trained on PTB-XL folds 1–8 and tested on fold 10.)
3. **MRI segmentation and classification use different datasets** (LGG with masks
   for segmentation; Kaggle without masks for classification), so a single
   uploaded image is not validated end-to-end through both tasks.
4. **MRI classification** was evaluated on the full image; the now-working
   segmentation enables a crop-then-classify path, but its effect on Kaggle-style
   classification images is untested (different MRI modality from LGG).
5. **Threshold sensitivity** — F1 depends on per-pathology thresholds calibrated
   on PTB-XL; a new data source may require re-tuning.
6. **Noise / input sensitivity** — inputs must be proper 12-lead ~10 s ECGs;
   malformed inputs degrade results.
7. **Scalability** — inference is synchronous in the request thread (no queue);
   echo video inference is especially slow on CPU (~10–40 s/video).
8. **Echo numbers are on a TEST-split subset** (400 videos EF — the headline —
   plus 30 traced frames for Dice) for speed; rerun without `--limit` for the
   full 1,277-video figure. (An earlier 40-video subset gave a flattering 3.19 %.)
9. **EEG metrics are frozen-encoder, subset-trained.** The BIOT IIIC head was
   fine-tuned on a 1,451-EEG balanced subset (not the full 17 k-EEG HMS) with the
   encoder **frozen**, giving honest-but-modest numbers (balanced-acc 0.28, κ 0.15 on
   1,883 held-out windows — above chance, below BIOT's full-data ~0.5). More data did
   *not* raise the headline (frozen features are the ceiling); the real lever is a
   full fine-tune (unfreeze the encoder, needs a GPU — see §5). IIIC is also a
   **critical-care** cohort, not tumour-specific, so it screens function — it does not
   localise or diagnose a tumour.

## 7. Ethics notes (platform findings)

- **PHI access control (mitigated):** result images, uploads, and PDF reports are
  served through an **HMAC-signed, time-limited** `/media/` view
  (`backend/core/media.py`); the API never returns a raw `/media/` URL. Remaining
  limitation to discuss: a signed URL is **time-scoped, not per-identity** — anyone
  holding a valid (unexpired) URL can fetch it, so it is not a substitute for a full
  per-request authorization check.
- JWT stored in browser `localStorage`; no encryption at rest; no audit log.

## 8. Perspectives

- Validate MRI classifier on the full Kaggle set; fix or replace segmentation.
- Confirm ECG generalisation on an independent dataset.
- **Neuro-cardiac correlation study** (the project's central hypothesis): requires
  a paired brain-imaging + ECG cohort — the key future direction.
- Real-time ECG via wearable/connected devices; extension to other modalities.

---

*Generated for the PFE (Université Constantine 2). Numbers marked "preview"
must be replaced with full-fold results before submission.*
