# Independent ECG Evaluation (PTB-XL leakage check)

This is the documented, reproducible procedure to test the ECG models on a dataset
**independent of PTB-XL** — the clean answer to "is the ~0.98 AUC optimistic because
ecglib might have trained on PTB-XL?"

It does **not** retrain anything. The ecglib weights are frozen; this measures the
existing, deployed models on new data. Script: [`eval_ecg_external.py`](eval_ecg_external.py).

---

## Why

`VALIDATION.md` reports ECG numbers on PTB-XL fold 10. But ecglib's training corpus
(500k+ records) is not published and **may include PTB-XL**, so that "held-out" set
might not be truly unseen. Testing on the **Chapman-Shaoxing-Ningbo** database
(PhysioNet `ecg-arrhythmia`, independent of PTB-XL, SNOMED-CT labelled) removes that
doubt. The number to quote is **macro AUC** — it is threshold-independent.

---

## Prerequisites

- Backend venv activated, with the ML stack installed (`pip install -r backend/requirements.txt`).
  Confirmed present in this repo: `torch`, `ecglib`, `wfdb`.
- Internet access to `physionet.org` (for streaming mode).

```powershell
cd backend
.\venv\Scripts\Activate.ps1
cd ..
```

---

## Option A — Disk-safe streaming sample (works on a full drive)

Streams records from PhysioNet one at a time and discards each immediately. Peak
disk use ≈ one record in RAM (~150 KB). **This is the only option that runs with
your current ~117 MB free.**

```powershell
# Indicative number on a 400-record sample:
python tools/eval_ecg_external.py --stream 400 --seed 42
```

- `--seed` makes the sample reproducible (same 400 records every run).
- Start small (`--stream 100`) to confirm connectivity, then scale up.
- CPU inference is slow; 400 records may take 10-30 min. Streaming adds network time.

**Reading the result:** look at the `support` column per pathology. AUC on a pathology
with <30 positives in the sample is noisy — stream more records (e.g. `--stream 1500`)
to firm up the rare ones (`LBBB`, `1AVB` are usually rare).

---

## Option B — Full local evaluation (report-grade, needs disk)

Once you free several GB on E: (or use another drive), download the dataset and run
against the full set for the strongest number.

```powershell
# ~2-3 GB. Download to a drive with space:
wget -r -N -c -np https://physionet.org/files/ecg-arrhythmia/1.0.0/
# then:
python tools/eval_ecg_external.py --local path/to/physionet.org/files/ecg-arrhythmia/1.0.0
```

(`get_record_list` / direct WFDB read both work; the script auto-resamples any record
that isn't 12x5000.)

---

## ⚠️ Verify the label map before quoting any number

The script maps SNOMED-CT diagnosis codes to ecglib's 7 pathologies in
`SNOMED_TO_ECGLIB` (top of `eval_ecg_external.py`). These are the standard
PhysioNet/CinC-2021 codes, but **code sets drift between dataset versions**. Before
trusting the metrics:

1. Open the dataset's `ConditionNames_SNOMED-CT.csv`.
2. Confirm each code in `SNOMED_TO_ECGLIB` still means what the comment says.
3. ecglib's `RBBB`/`LBBB` are *general* (complete OR incomplete), so both SNOMED
   variants intentionally map to the same ecglib code.

A wrong code silently mislabels a whole pathology — this is the one manual check that
matters.

---

## How to report it (honest framing for the thesis)

> To rule out PTB-XL train/test overlap, the frozen ecglib ensemble was evaluated on
> an independent dataset (Chapman-Shaoxing-Ningbo, PhysioNet `ecg-arrhythmia`),
> SNOMED-CT mapped to the 7 modelled pathologies. On *N* records the model reached
> macro AUC **X.XXX** at the deployed per-pathology thresholds. AUC is
> threshold-independent, so this measures genuine generalisation beyond PTB-XL.

- If the AUC stays high (≈0.95+), the PTB-XL number is **vindicated** — no meaningful leakage.
- If it drops noticeably, you've **honestly quantified** the optimism — itself a
  legitimate, defensible finding (you found and measured the limitation).

Either outcome is good science. Fill in *N* and *X.XXX* from the run output.
