# Thesis Screenshots

Place captures of the running platform here. The numbered list below matches
the order they should appear in the PFE report (Chapter 3 — Results).

## Checklist

| # | Filename | What to capture | Suggested section |
|---|---|---|---|
| 01 | `01_login.png`                       | Login page with the medical-blue gradient and Mail/Lock icon inputs | 3.1 |
| 02 | `02_dashboard.png`                   | Dashboard with the four StatsCards populated (after `seed_database.py`) | 3.1 |
| 03 | `03_patient_list.png`                | Patient list table — show 5 rows with the avatars and the search bar | 3.1 |
| 04 | `04_patient_detail.png`              | Patient detail with the three action buttons + tabbed history visible | 3.1 |
| 05 | `05_mri_upload.png`                  | MRI upload modal mid-drop or with the file preview thumbnail | 3.2 |
| 06 | `06_mri_result_overlay.png`          | MRI result page on the **Overlay** tab — red semi-transparent mask on the slice | 3.2 |
| 07 | `07_mri_result_classification.png`   | MRI result page right-column result card showing `tumor_type` + confidence bar | 3.2 |
| 08 | `08_ecg_upload.png`                  | ECG upload modal with the help text visible | 3.3 |
| 09 | `09_ecg_result_diagnosis.png`        | ECG result page diagnosis card (large) + confidence bar | 3.3 |
| 10 | `10_ecg_pathology_table.png`         | ECG result page pathology table with the horizontal probability bars | 3.3 |
| 11 | `11_report_generation.png`           | Report generator modal with MRI + ECG dropdowns populated | 3.4 |
| 12 | `12_pdf_preview.png`                 | The generated PDF rendered in the in-app viewer iframe (and/or a desktop PDF reader) | 3.4 |
| 13 | `13_architecture_diagram.png`        | Optional polished version of the README's ASCII architecture diagram (Excalidraw / draw.io) | 2.1 |

## How to capture

- Use Windows **Snipping Tool** (`Win+Shift+S`) for region grabs.
- Save as PNG at 1.5× or 2× scale for crisp print quality.
- Keep the browser zoomed to 100% so layout matches the design intent.
- Use the seed-database doctor (`doctor@test.com`) so screenshots feel populated
  rather than empty-state.

## Not in version control

This folder's PNGs should be **committed** when ready (they're the deliverable
for the thesis). The `.gitignore` lets them through — only the `media/` and
`samples/` data directories are filtered.
