# Test Samples

Demo inputs for the four models. Filenames carry the ground-truth label (the model's own prediction is in the table below).


## MRI — REAL labeled brain-tumor images (data/brain-tumor-mri)

| File | Ground truth | Model prediction |
|---|---|---|
| mri_01_glioma.jpg | glioma | meningioma (61%) |
| mri_02_glioma.jpg | glioma | glioma (100%) |
| mri_03_glioma.jpg | glioma | glioma (100%) |
| mri_04_meningioma.jpg | meningioma | meningioma (100%) |
| mri_05_meningioma.jpg | meningioma | meningioma (100%) |
| mri_06_meningioma.jpg | meningioma | meningioma (100%) |
| mri_07_pituitary.jpg | pituitary | pituitary (100%) |
| mri_08_pituitary.jpg | pituitary | pituitary (100%) |
| mri_09_notumor.jpg | notumor | no_tumor (100%) |
| mri_10_notumor.jpg | notumor | no_tumor (100%) |
| mri_11_glioma_70pct.jpg | glioma | glioma (70%) |
| mri_12_glioma_51pct.jpg | glioma | glioma (51%) |
| mri_13_glioma_75pct.jpg | glioma | glioma (75%) |
| mri_14_glioma_75pct.jpg | glioma | glioma (75%) |
| mri_15_glioma_54pct.jpg | glioma | glioma (54%) |

## ECG — REAL 12-lead CSVs, Chapman-Shaoxing-Ningbo (PhysioNet, independent of PTB-XL = unseen by the model)

| File | Ground truth | Model prediction |
|---|---|---|
| ecg_01_AFIB.csv | AFIB | Atrial Fibrillation (100%) |
| ecg_02_1AVB.csv | 1AVB | 1st Degree AV Block (98%) |
| ecg_03_STACH.csv | STACH | Sinus Tachycardia (99%) |
| ecg_04_STACH.csv | STACH | Sinus Tachycardia (99%) |
| ecg_05_SBRAD.csv | SBRAD | Normal Sinus Rhythm (66%) |
| ecg_06_SBRAD.csv | SBRAD | Normal Sinus Rhythm (46%) |
| ecg_07_RBBB.csv | RBBB | Right Bundle Branch Block (95%) |
| ecg_08_LBBB.csv | LBBB | Atrial Fibrillation (100%) |
| ecg_09_PVC.csv | PVC | Normal Sinus Rhythm (5%) |
| ecg_10_Normal.csv | Normal | Normal Sinus Rhythm (92%) |

## EEG — REAL labeled .edf from Kaggle-HMS (expert-consensus label)

| File | Ground truth | Model prediction |
|---|---|---|
| eeg_01_Seizure.edf | Seizure | SZ (harmful=True) |
| eeg_02_Seizure.edf | Seizure | GPD (harmful=True) |
| eeg_03_LateralizedPeriodicDischarges.edf | Lateralized Periodic Discharges | SZ (harmful=True) |
| eeg_04_LateralizedPeriodicDischarges.edf | Lateralized Periodic Discharges | LPD (harmful=True) |
| eeg_05_GeneralizedPeriodicDischarges.edf | Generalized Periodic Discharges | GPD (harmful=True) |
| eeg_06_GeneralizedPeriodicDischarges.edf | Generalized Periodic Discharges | GPD (harmful=True) |
| eeg_07_LateralizedRhythmicDeltaActivity.edf | Lateralized Rhythmic Delta Activity | LRDA (harmful=False) |
| eeg_08_LateralizedRhythmicDeltaActivity.edf | Lateralized Rhythmic Delta Activity | SZ (harmful=True) |
| eeg_09_GeneralizedRhythmicDeltaActivity.edf | Generalized Rhythmic Delta Activity | LRDA (harmful=False) |
| eeg_10_GeneralizedRhythmicDeltaActivity.edf | Generalized Rhythmic Delta Activity | LRDA (harmful=False) |

## Echo — SYNTHETIC cine clips (pipeline demo only — EF is NOT clinically meaningful; no public A4C echo set is freely downloadable)

| File | Ground truth | Model prediction |
|---|---|---|
| echo_01_synthetic.mp4 | synthetic | EF 37.784202575683594% (Reduced (HFrEF)) |
| echo_02_synthetic.mp4 | synthetic | EF 52.19525909423828% (Normal) |
| echo_03_synthetic.mp4 | synthetic | EF 60.599002838134766% (Normal) |
| echo_04_synthetic.mp4 | synthetic | EF 65.46852111816406% (Normal) |
| echo_05_synthetic.mp4 | synthetic | EF 67.61801147460938% (Normal) |
| echo_06_synthetic.mp4 | synthetic | EF 70.00071716308594% (Normal) |
| echo_07_synthetic.mp4 | synthetic | EF 71.93423461914062% (Normal) |
| echo_08_synthetic.mp4 | synthetic | EF 72.00162506103516% (Normal) |
| echo_09_synthetic.mp4 | synthetic | EF 71.06957244873047% (Normal) |
| echo_10_synthetic.mp4 | synthetic | EF 70.31402587890625% (Normal) |
