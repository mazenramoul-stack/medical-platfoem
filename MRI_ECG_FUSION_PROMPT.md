# Build the MRI↔ECG multimodal-fusion methodology (architecture + virtual cohort + hypothesis test)

You are working in an existing monorepo: a multimodal medical-AI platform (Master's
PFE — brain MRI, 12-lead ECG, echocardiogram, EEG, with a combined PDF report).
Two pre-trained modalities already work end-to-end and are validated on their native
public benchmarks:

- **MRI** — a Swin-T 4-class brain-tumor classifier (glioma / meningioma / pituitary /
  notumor), ~95% on the Kaggle brain-tumor set; plus a U-Net segmenter.
- **ECG** — 7 ecglib DenseNet-1D-121 pathology classifiers (AFIB, 1AVB, STACH, SBRAD,
  RBBB, LBBB, PVC) on 12-lead signals.

Your job: deliver a **computational / methodological** contribution — a **fusion
architecture**, a **virtual multimodal cohort** built by transparent matching across the
two independent cohorts, and a **pre-registered hypothesis-testing protocol** for a
"brain–heart" interaction, evaluated on that virtual cohort with its limitations stated
explicitly. Work autonomously; verify as you go; only stop on a genuine blocker.

## Read this first — the honest framing (do NOT violate it)

This is the scientific core of the contribution, and getting the framing wrong makes the
whole thesis indefensible. Internalize it before writing code:

1. **There is no expected physiological coupling between brain-*tumor* MRI and *arrhythmia*
   ECG.** Unlike EEG brain-activity ↔ ECG heart-activity, a glioma and atrial fibrillation
   are not mechanistically linked. So the deliverable is **methodology**, framed as: "here is
   the fusion architecture and the hypothesis-testing protocol that *would* detect a brain–heart
   synergy *if one existed and if paired data were available*." It is **not** a claim of a real
   clinical synergy.
2. **The cohort is *virtual* (matched across separate datasets), not paired.** Any apparent
   "synergy" is therefore at high risk of being an **artifact of the matching procedure** (shared
   confounds, label base-rate correlations), not genuine cross-modal information.
3. **Therefore the protocol MUST include a negative control** (a shuffled / re-randomized
   MRI↔ECG pairing). A synergy signal is only credible if it **exceeds** what the shuffled
   control produces. Expect — and report honestly — that for these two unrelated conditions the
   result is a **null** (no synergy beyond the control). A correctly-reported null that
   *validates the negative-control methodology* is the success criterion, **not** a positive
   synergy number.
4. **Never oversell.** No language anywhere (code comments, docs, plots, report) may imply a
   discovered clinical brain–heart link. If a positive signal appears, treat it as suspect, hunt
   the confound, and report it as such.

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — architecture, **hard version constraints**
   (Python 3.10/3.11, Django 3.2.25, djongo, exact ecglib 1.0.1 pin), the two backend
   contracts (doctor isolation + result envelope), the test-runner behaviour, and the
   "looks like a bug but isn't" notes. Treat it as authoritative.
2. Read how each modality is loaded and run (this is what you reuse — do not retrain the
   encoders):
   - `backend/apps/inference/model_loader.py` — `get_mri_classifier()` returns
     `(processor, swin_model)` (HuggingFace Swin); `get_ecg_models()` returns a dict
     `{pathology_code: DenseNet-1D model}` (input `(1, 12, 5000)` @ 500 Hz, single sigmoid
     output `(1, 1)` per model). Note the lazy-singleton pattern and `get_device()`.
   - `backend/apps/inference/mri_pipeline.py` — `analyze_mri` / `explain_mri`; how images are
     loaded (`load_image_universal`) and the 4-class `class_probabilities`.
   - `backend/apps/inference/ecg_pipeline.py` — `analyze_ecg`; `load_ecg_signal` →
     `(12, 5000)` + quality dict; the bandpass+z-norm preprocessing; `_scalar_probability`;
     the 7 pathology codes and thresholds.
3. Read the existing evaluation + statistics harnesses you will mirror and reuse:
   - `tools/eval_mri_classifier.py` — how it iterates `data/brain-tumor-mri` and scores the Swin.
   - `tools/eval_ecg_classifier.py` — how it loads the ECG eval set (PTB-XL fold 10) and scores.
   - `tools/bootstrap_cis.py` — bootstrap 95% CIs + permutation test on cached predictions
     (this is your statistics template — **reuse its approach**, don't reinvent CIs/permutation).
   - `maybe read/VALIDATION.md` (§0–§5) — how every accuracy number was honestly measured and
     reported; match this rigor and tone.
4. **Inventory `data/` first.** Confirm exactly which datasets are present (`brain-tumor-mri`,
   `hms`, `samples`, and whether a PTB-XL/ECG eval set exists locally). Reuse the *exact* loaders
   the existing `eval_*.py` harnesses use. If a needed dataset is **absent**, print clear
   download/setup instructions and still build the full pipeline — **never fabricate numbers or
   a synthetic "cohort" presented as real data.**
5. Use the `superpowers` **brainstorming** (to lock the experimental design with the human if
   anything below is ambiguous), **test-driven-development**, and
   **verification-before-completion** skills. Verify every claim with the commands in the
   Verification section before asserting anything works.

## Hard constraints (do not violate)

- **Reuse the frozen pre-trained encoders** via `ModelLoader` — do **not** retrain or fine-tune
  the MRI Swin or the ECG DenseNets. Only the small fusion/probe heads are trained.
- **No new heavy dependencies.** torch, torchvision, transformers, ecglib, captum, numpy,
  scipy, matplotlib are installed. Compute AUROC / accuracy / bootstrap CIs / permutation tests
  with **numpy + scipy** (mirror `tools/bootstrap_cis.py`). Only use scikit-learn if it is
  *already* a declared dependency — check before importing.
- **Fully reproducible.** Fixed RNG seeds everywhere (matching, shuffling, train splits,
  bootstrap). Persist the virtual-cohort **manifest** (CSV/JSON: which MRI record matched which
  ECG record, plus the seed and matching rule) and all metrics as JSON so results are auditable
  and re-runnable to the same numbers.
- **CPU-runnable.** Encoders run on CPU (as in the app). Keep the fusion/probe heads small
  (linear / shallow MLP) so the whole experiment finishes in minutes on CPU. If you offer an
  optional GPU/Colab path, mirror the `Colab PFE/` convention and keep the local CPU path the
  default. Never trust Colab numbers unverified — re-verify locally.
- **Do not touch or break existing modality code or the two contracts** (doctor isolation,
  result envelope). This task is primarily a **`tools/` research pipeline + documentation**, not
  a change to the live request path. Add **no** DB model, **no** migration, and **no** new API
  endpoint unless the human explicitly asks to surface fusion in the web app (out of scope by
  default — propose it, don't build it).

## What to build

Locked design decisions (lock further details with the human via brainstorming only if
genuinely ambiguous):

### 1. Embeddings (frozen encoders → fixed-length vectors)
For each record, extract a fixed-length embedding from the frozen encoder:
- **MRI:** the Swin penultimate embedding (e.g. `swin(...).pooler_output`, ~768-d). Provide a
  robust fallback of the 4-class probability vector (4-d) and **document which you used**.
- **ECG:** the DenseNet penultimate features (via a forward hook before the final FC) **or**,
  as a robust low-dim fallback, the 7 per-pathology sigmoid probabilities (7-d). Document the
  choice.
Persist embeddings to disk (`.npy`/`.npz` under `tools/` caches, like the existing `*_preds.json`)
so training/eval re-read the cache instead of recomputing.

### 2. Virtual multimodal cohort (transparent matching)
`tools/build_virtual_cohort.py`: pair each MRI record with an ECG record under a **documented,
seeded** rule. Stratify by whatever shared metadata actually exists (age band / sex if present);
if none is available, use label-stratified or uniform random matching with a fixed seed — and
**say so plainly**. Output a manifest (`tools/fusion_cohort_manifest.csv` + a JSON sidecar with
seed, rule, counts, label base rates) and a train/test split. Each virtual subject carries
`(e_mri, e_ecg, y_mri, y_ecg)` where `y_mri` ∈ {4-class tumor label} and `y_ecg` ∈ {ECG label(s)}.

### 3. Fusion architecture
`tools/fusion_model.py`: a small, documented fusion head over `[e_mri ; e_ecg]` (concatenation +
shallow MLP, late fusion). Also implement the unimodal baselines (MRI-only head, ECG-only head)
and **cross-modal probes** (MRI embedding → predict ECG label; ECG embedding → predict MRI label)
sharing the same head class for fairness.

### 4. Pre-registered hypothesis-testing protocol
Write the hypothesis **before** running anything (in the methodology doc, dated):
- **H0 (expected to hold):** no brain–heart synergy — the cross-modal probe performs at chance,
  and fusion does not beat the best unimodal model **beyond** the shuffled-pairing control.
- **H1:** fusion beats the best single modality on the joint outcome by a margin that **exceeds**
  the shuffled-pairing negative-control distribution.

`tools/train_fusion.py` + `tools/eval_fusion.py`: on the held-out test split, compute for each
target (MRI label, ECG label, and a transparently-defined composite/joint label):
- unimodal baseline, fusion, cross-modal probe — AUROC (macro where multi-class) + accuracy;
- **the negative control:** repeat the entire fusion eval with the MRI↔ECG pairing **shuffled**
  (≥ the number of permutations used in `bootstrap_cis.py`);
- **statistics (mirror `bootstrap_cis.py`):** bootstrap 95% CIs on the key differences
  (fusion − best unimodal; matched-fusion − shuffled-fusion) and a permutation p-value for the
  synergy claim. Write everything to `tools/fusion_metrics.json` + a human-readable results table.

### 5. Documentation (the actual thesis deliverable)
`maybe read/MRI_ECG_FUSION.md` (or `docs/MRI-ECG-FUSION-BRIEF.md` — match where similar briefs
live): architecture diagram/description, cohort-construction rule + seed, the pre-registered
hypothesis, the protocol, the results table, **the honest limitations** (no expected physiological
coupling; virtual not paired; matching confounds; the negative control as the safeguard), and a
crisp statement of **exactly what paired (same-subject brain+heart) data and study design would be
required to obtain a definitive clinical answer in future work.** Add a short cross-referenced
section to `maybe read/VALIDATION.md` and update `CLAUDE.md`'s tools list with the new scripts.

## Verification (run these; report ACTUAL output before claiming done)

From the repo root (venv active), once `data/` is confirmed present:
```
python tools/build_virtual_cohort.py        # writes manifest + embedding caches (reproducible w/ seed)
python tools/train_fusion.py                 # trains unimodal + fusion + cross-modal heads
python tools/eval_fusion.py                  # metrics + bootstrap CIs + permutation + shuffled control
```
Backend sanity (must stay green — you changed nothing on the request path):
```
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run     # MUST be "No changes detected"
python manage.py test tests.test_doctor_isolation tests.test_health
```
Add tests under `tools/` (or `backend/tests/`, weight-free where possible):
- the matcher is **deterministic** for a fixed seed and the manifest round-trips;
- the fusion head trains and produces probabilities in `[0,1]` of the right shape;
- the **shuffled-pairing control** runs and the synergy statistic is computed against it;
- a tiny synthetic-embedding fixture exercises `train_fusion`/`eval_fusion` **without** loading the
  heavy encoders (fast, CI-friendly), with the full encoder path run locally.

## Definition of done

- A reproducible pipeline (`build_virtual_cohort` → `train_fusion` → `eval_fusion`) that, from the
  existing frozen MRI + ECG encoders, builds a seeded virtual cohort, trains a fusion architecture
  with unimodal baselines and cross-modal probes, and runs the hypothesis test **with the shuffled
  negative control and bootstrap/permutation statistics** — all artifacts (manifest, embeddings,
  metrics JSON) persisted and re-runnable to identical numbers.
- A methodology document that pre-registers the hypothesis, presents the results **honestly**
  (expected: null synergy beyond control), states the no-physiological-coupling and virtual-cohort
  limitations prominently, and specifies what paired data/design a future clinical answer requires.
- No existing contract broken; `manage.py check` clean; **no migration**; no oversold claims
  anywhere.
- Report what you verified with the **actual command output** (the metrics table and the
  matched-vs-shuffled comparison in particular).

## Suggested order

1. Inventory `data/`; reuse the exact loaders from `eval_mri_classifier.py` /
   `eval_ecg_classifier.py`. Build + cache embeddings → verify shapes.
2. `build_virtual_cohort.py` + a determinism test → verify the manifest round-trips.
3. `fusion_model.py` + `train_fusion.py` on a synthetic-embedding fixture (TDD) → verify.
4. `eval_fusion.py` with the shuffled negative control + bootstrap/permutation (mirror
   `bootstrap_cis.py`) → verify on the synthetic fixture, then on the real cohort.
5. Write `MRI_ECG_FUSION.md` + VALIDATION.md section + CLAUDE.md tools update.
6. Full verification sweep, then a final self-review against the honest-framing rules above.

Keep edits focused, reuse the existing loaders/eval/stats patterns precisely, and let the
**negative control and honest null reporting** — not a synergy number — be the result you stand behind.
