# PFE Report — Chapter Outline

A mapping from the academic thesis chapters to the concrete files and modules
of this codebase. Use this when writing your defence document: every section
below points to evidence you can cite or include as a screenshot.

---

## Chapter 1 — State of the Art

### 1.1 Introduction
Frame the public-health weight of non-communicable diseases (NCDs), with
reference to the WHO mortality figures and the supervisors' project brief
([sujet PDF](Derdour_Talbi_PFEPDF_251202_143435%20%282%29.pdf) attached to
this repository for context).

### 1.2 Brain Tumors and MRI
- Tumor types: glioma, meningioma, pituitary adenoma.
- MRI sequences: T1, T1-contrast, T2, FLAIR.
- Clinical workflow: radiologist segmentation, neurosurgical evaluation.
- Cite: Buda et al. (2019); Esteva et al. (2019).

### 1.3 Cardiac Pathologies and ECG
- The 12-lead ECG: leads, sampling rate, typical acquisition durations.
- Pathologies of interest: AFIB, AV blocks, bundle branch blocks, PVC.
- HRV as autonomic-tone biomarker (RMSSD, SDNN, pNN50).
- Cite: Wagner et al. (2020); Makowski et al. (2021).

### 1.4 Deep Learning in Medical Imaging
- CNNs and the U-Net architecture (Ronneberger et al., 2015).
- Vision Transformers (Dosovitskiy et al., 2021); Swin Transformer (Liu et al., 2021, ICCV).
- ResNet and DenseNet (He et al., 2016; Huang et al., 2017).

### 1.5 Deep Learning in ECG Analysis
- 1D-CNN architectures for time-series.
- Multi-label vs. multi-class formulations.
- Cite: Avetisyan et al. (2023).

### 1.6 Existing Clinical Decision Support Systems
- Commercial: GE Healthcare *Edison*, Aidoc, Zebra Medical.
- Open-source: MONAI, RadAI, ECG-Kit.
- Gap: single-modality silos; few platforms integrate brain + cardiac.

### 1.7 Conclusion
Position your contribution: not a new model, but a **multimodal integration
architecture** that aggregates pretrained models, classical signal processing,
and an auditable web interface.

---

## Chapter 2 — Methods and Tools

### 2.1 Platform Architecture Overview
Include the ASCII diagram from [README.md](../README.md#architecture). Three
layers: React → Django REST → MongoDB. Inference is a Python singleton that
the REST views call synchronously.

### 2.2 Data Acquisition and Preprocessing
- MRI: universal loader in [`apps/inference/utils.py`](backend/apps/inference/utils.py)
  supporting PNG/JPG/DICOM/NIfTI.
- ECG: 12-lead normalisation, bandpass 0.5–40 Hz, resample to 500 Hz, pad/trim
  to 10 s (see [`load_ecg_signal`](backend/apps/inference/utils.py)).

### 2.3 MRI Deep Learning Pipeline
Reference [`apps/inference/mri_pipeline.py`](backend/apps/inference/mri_pipeline.py).
#### 2.3.1 U-Net Segmentation
- `mateuszbuda/brain-segmentation-pytorch`, ~7.7 M params, in_channels=3.
- Sigmoid output → binary mask at threshold 0.5.
- Discuss your preprocessing choice and its known limitations.
#### 2.3.2 Swin Transformer Classification
- `Devarshi/Brain_Tumor_Classification` (Swin-T, base backbone `microsoft/swin-tiny-patch4-window7-224`), ~28 M params.
- 4-class output (glioma, meningioma, no_tumor, pituitary).
- ROI cropping based on the U-Net mask before classification.

### 2.4 ECG Deep Learning Pipeline
Reference [`apps/inference/ecg_pipeline.py`](backend/apps/inference/ecg_pipeline.py).
#### 2.4.1 DenseNet-1D-121
- 7 binary classifiers from `ecglib`, each pretrained on 500 k+ records.
- Input shape (1, 12, 5000) — 12 leads × 10 s @ 500 Hz.
#### 2.4.2 NeuroKit2 HRV
- R-peak detection on Lead II.
- Time-domain HRV (RMSSD, SDNN, pNN50).
- Rule-based bradycardia / tachycardia flags.

### 2.5 Backend (Django + MongoDB)
- Django 3.2 LTS, DRF, SimpleJWT.
- djongo over MongoDB; rationale for choosing Mongo (schema flexibility
  for nested HRV / probability dicts).
- Doctor-scoped queryset filtering pattern.
- Synchronous inference with `ThreadPoolExecutor` timeout
  ([`apps/inference/__init__.py`](backend/apps/inference/__init__.py)).

### 2.6 Frontend (React)
- Vite + React 19 + TailwindCSS + Redux Toolkit.
- Token storage in `localStorage`; axios interceptor.
- Drag-and-drop upload via `react-dropzone`, progress reporting via
  axios `onUploadProgress`.
- Combined report flow: end-to-end from PatientDetail to PDF download.

### 2.7 Development Environment
- OS: Windows 10/11.
- Python 3.10.7, Node.js 22.13.
- MongoDB Community 6+, local single-instance.
- Editor: VS Code.
- Version control: git.

---

## Chapter 3 — Results and Discussion

### 3.1 System Functionality
- Walk through Register → Login → Patient → MRI upload → ECG upload → Report.
- Cite the automated test suite: `python manage.py test tests.test_pipelines`
  passes 7/7 in ~18 s on the dev machine.

### 3.2 MRI Analysis Results (screenshots)
- `SCREENSHOTS/06_mri_result_overlay.png` — segmentation overlay
- `SCREENSHOTS/07_mri_result_classification.png` — Swin verdict + confidence
- Honest discussion of the U-Net mask-saturation bug as a **diagnosed-and-fixed
  engineering contribution**: it was a double-sigmoid (the model applies sigmoid
  internally; the pipeline applied it again), not a preprocessing flaw — fixing it
  restored Dice ~0.85 on LGG. Frame it as a debugging win, not an open limitation.

### 3.3 ECG Analysis Results (screenshots)
- `SCREENSHOTS/09_ecg_result_diagnosis.png` — primary diagnosis card
- `SCREENSHOTS/10_ecg_pathology_table.png` — per-pathology table with bars
- HRV reference-range visualisation.

### 3.4 Combined Reports
- `SCREENSHOTS/12_pdf_preview.png` — generated PDF
- Discussion of the combined-interpretation section's neuro-cardiac branch.

### 3.5 Performance Analysis
- Cold inference: MRI ~18 s, ECG ~52 s (first-call model download dominates).
- Warm inference: MRI ~1.2 s, ECG ~3.2 s (15–17× speedup from singleton cache).
- No GPU; all measurements on CPU.

### 3.6 Limitations
Reproduce the bullet list from README.md → Known Limitations. Be honest:
preprocessing mismatch, model disagreement, partial ecglib coverage,
non-clinical-grade outputs.

### 3.7 Ethics and Data Privacy
- Honest scope (a prototype, **not** GDPR-compliant): no consent capture,
  pseudonymisation, retention-expiry, or access audit log — noted as future
  work. No real patient data in the repo; all media uploads are gitignored.
- Doctor-scoped queryset enforced at the ORM layer.
- Disclaimer text reproduced in every generated PDF.

### 3.8 Future Work
- Replace U-Net with a BraTS-trained MONAI model (multi-sequence T1/FLAIR/T1c input,
  rather than the current single-image-broadcast-to-3-channels approximation).
- Asynchronous inference via Celery + Redis (deps already pinned).
- Calibrated confidence scoring against a held-out cohort.
- DICOM viewer in the browser (cornerstone deps already installed).
- Audit log for clinical traceability.

---

## Chapter 4 — Business Model Canvas

Refined from the supervisor-pitch conversation. Adapt the nine-block BMC to
match your actual scope.

### 4.1 Value Proposition
Non-invasive multimodal screening: unified MRI + ECG analysis with auditable
reports for under-resourced clinics that lack on-site radiologists or
cardiologists.

### 4.2 Customer Segments
- Hospitals and oncology departments in mid-sized Algerian cities.
- Telemedicine providers serving rural areas.
- Cardiac rehabilitation clinics.
- Research labs working on neuro-cardiac coupling.

### 4.3 Channels
Medical congresses, university partnerships (CRSTRA, Centre Pierre & Marie Curie
de Constantine), direct sales to hospital IT departments.

### 4.4 Customer Relationships
SaaS subscription with on-site deployment option. Update channel for newer
pretrained models without rebuilding the platform.

### 4.5 Revenue Streams
- Per-doctor subscription tier.
- Hospital-wide enterprise license.
- Cloud-hosted API for telemedicine partners (per-analysis billing).

### 4.6 Key Activities
R&D for new modalities, clinical validation studies, certifications
(CE-MDR Class IIa minimum for decision-support).

### 4.7 Key Resources
- Codebase + pretrained models.
- Clinical advisory board.
- Compliance and regulatory expertise.

### 4.8 Key Partners
University clinical departments, medical device manufacturers (ECG vendors),
cloud providers offering medical-grade compliance.

### 4.9 Cost Structure
Engineering, regulatory, server infrastructure, ongoing clinical validation.

### 4.10 SWOT
- **Strengths**: open architecture, low compute cost, multimodal.
- **Weaknesses**: pretrained models not clinically validated, no CE/FDA yet.
- **Opportunities**: under-served sub-Saharan and North African markets.
- **Threats**: established vendors, regulatory burden, data-residency constraints.

### 4.11 Development Roadmap
- **Phase 1 (MVP — this PFE)**: functional prototype on public datasets.
- **Phase 2**: pilot deployment at one teaching hospital, IRB approval.
- **Phase 3**: clinical validation study and CE-MDR submission.
- **Phase 4**: commercial launch.

---

## Defence Cheat Sheet

If asked "is this clinically valid?":
> "No — the contribution is the integration architecture. The pretrained models
> are off-the-shelf and have not been validated on a local clinical cohort.
> Confidence scores are not calibrated. Section 3.6 documents these limitations."

If asked "why MongoDB?":
> "Schema flexibility for nested JSON fields like HRV metrics and per-pathology
> probability dictionaries, which would otherwise require either separate
> relational tables or JSON columns. The trade-off is the djongo + Django
> version constraint, documented in section 2.5."

If asked "what would you change?":
> "First, replace the binary 0.5 segmentation threshold with calibrated
> probabilities and an 'uncertain' verdict, and feed the U-Net true multi-sequence
> MRI (T1/FLAIR/T1c) instead of one image broadcast to three channels. Second, move
> inference to Celery for non-blocking uploads. Third, secure media behind
> authenticated, doctor-scoped URLs."
>
> (Note: the earlier 'mask saturation' was a double-sigmoid bug, already fixed — the
> preprocessing is channel-wise z-score; don't present it as an open issue.)
