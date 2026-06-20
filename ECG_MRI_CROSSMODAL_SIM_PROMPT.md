# Build the cross-modal ECG↔MRI prediction model on SIMULATED linked data (proof-of-concept for the future paired-cohort system)

You are working in an existing monorepo: a multimodal medical-AI platform (Master's PFE —
brain MRI, 12-lead ECG, echocardiogram, EEG, combined PDF report). MRI (a Swin-T 4-class
brain-tumor classifier) and ECG (7 ecglib DenseNet-1D pathology classifiers) already work and
are validated on their native public benchmarks.

**The vision (state it; build toward it):** In future the platform will collect, over 1–2
years, many patients who each have ALL FOUR analyses (ECG, MRI, EEG, Echo). That same-patient
paired data will train a *cross-modal* model: given ONE modality, output the probability of
each class in the OTHER modalities. **For now, scope = ECG ↔ MRI only**, and — since no paired
data exists yet — you will **simulate linked ECG↔MRI data with a known, tunable coupling** and
show the model recovers it. This is a dry-run / proof-of-concept of the future system, exactly
as the supervisor suggested.

**Locked choices for this task:**
- **Fully synthetic feature vectors** (no real images/signals, no real encoders, no `data/`
  dependency) generated from a designed joint distribution.
- **Bidirectional**: ECG → P(MRI classes) AND MRI → P(ECG classes).
- **Deliverable = a `tools/` research pipeline + a thesis methodology document.** No changes to
  the live app, its API, DB, or contracts.

## Read this first — the honest framing (do NOT violate it)

This is the scientific spine; get it wrong and the chapter is indefensible.

1. **This validates the *machinery*, not a clinical finding.** Fully synthetic data with a
   *planted* ECG↔MRI coupling proves the architecture + training + evaluation pipeline can learn
   a cross-modal mapping and quantify it. It uses **no real patient data and no real encoders**,
   so it says **nothing** about whether real ECGs predict real brain-tumor classes.
2. **The coupling strength is a knob, λ ∈ [0, 1].** This is the heart of the rigor:
   - **λ = 0** (ECG and MRI independent) → every cross-modal predictor must score **≈ chance**
     (within CI). Built-in negative control proving no leakage / no artifact.
   - **λ > 0** → cross-modal accuracy/AUROC **rises monotonically** with λ. The **λ-sweep is the
     result you report**: "the pipeline recovers a planted coupling of strength λ as follows."
3. **No leakage by construction.** Each feature vector must depend **only on its own modality's
   label** (`x_mri ← y_mri`, `x_ecg ← y_ecg`). All cross-modal signal flows **only** through the
   label coupling `P_λ(y_mri, y_ecg)`. If `x_ecg` carried `y_mri` directly, "learning" would be
   meaningless — assert against this in a test.
4. **Make it a faithful stand-in for the real system + show the swap-in path.** Choose synthetic
   feature dimensions to mimic the real encoder embeddings (MRI ≈ Swin pooler width; ECG ≈ the
   DenseNet penultimate width), and document precisely how, when paired data arrives, the
   synthetic generator is replaced by real encoder embeddings while the train/eval code stays
   identical.
5. **Never oversell.** No language anywhere may imply a real clinical ECG↔brain link was found.
   Honest summary: "known synthetic coupling → recovered; λ=0 → chance; real coupling unknown
   until the paired cohort exists."

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — hard version constraints (Python 3.10/3.11,
   Django 3.2.25, djongo), the two contracts (doctor isolation + result envelope), test-runner
   behaviour, "looks like a bug but isn't" notes. Authoritative.
2. Read these to copy the REAL class sets + embedding widths your synthetic data must mimic (so
   the sim is a faithful stand-in):
   - `backend/apps/inference/mri_pipeline.py` / `model_loader.py` — the **4 MRI classes**
     (glioma, meningioma, pituitary, notumor) and the Swin embedding width (`pooler_output`, ~768).
   - `backend/apps/inference/ecg_pipeline.py` / `model_loader.py` — the **7 ECG pathologies**
     (AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC) and the DenseNet-1D penultimate width.
   - `tools/bootstrap_cis.py` — bootstrap 95% CIs + permutation test (your stats template —
     reuse the approach, don't reinvent).
   - `maybe read/VALIDATION.md` — the honest measurement/reporting tone to match.
3. Note `tools/` conventions: scripts run from repo root, read/write caches in `tools/`, are
   reproducible. Mirror them.
4. Use the `superpowers` **test-driven-development** and **verification-before-completion**
   skills; verify with the Verification commands before claiming anything works.

## Hard constraints (do not violate)

- **Fully synthetic & self-contained**: no real images/signals, no `ModelLoader`, no `data/`
  dependency, no network. The whole thing runs in seconds on CPU.
- **No leakage**: features depend only on their own label (enforced + tested).
- **Reproducible**: one `--seed`; persist the synthetic dataset (`.npz`), the generation manifest
  (JSON: seed, λ, dims, class base rates, the coupling matrix), and all metrics (JSON) so runs
  reproduce to identical numbers.
- **No new heavy deps**: numpy + scipy (+ torch for the small head, already installed). Compute
  AUROC/accuracy/CIs/permutation with numpy/scipy (mirror `bootstrap_cis.py`). Use scikit-learn
  only if it is already a dependency.
- **`tools/` + docs only**: no DB model, no migration, no API endpoint, no change to the request
  path or the two contracts. (Surfacing this in the web app is explicitly out of scope —
  propose, don't build.)

## What to build

**Label model (locked — faithful-enough and clean):** MRI = **4-way categorical**; ECG =
**8-way categorical** (the 7 pathologies + "Normal"). Bidirectional cross-modal heads are then
clean softmaxes (predict 4 / predict 8). Note in the doc that the real platform ECG is
multi-label (7× sigmoid); categorical is the PoC simplification and the generator can be
extended to multi-label later.

### 1. Synthetic linked-data generator — `tools/sim_crossmodal_data.py`
Generative model (document it exactly in the doc):
- Build a coupling matrix `P_λ(y_ecg | y_mri)` of shape (4, 8) that interpolates:
  `P_λ = (1−λ)·marginal + λ·structured`, where `marginal` makes ECG independent of MRI (every
  row = the ECG base-rate vector) and `structured` is a fixed strong association (e.g. a
  deterministic-with-noise block/assignment map). So λ=0 ⇒ independence, λ=1 ⇒ strong
  dependence; mutual information increases with λ.
- Sample `y_mri ~ Categorical(π_mri)`, then `y_ecg ~ P_λ(·|y_mri)`.
- Generate features carrying ONLY their own label: `x_mri = Cmri[y_mri] + N(0, σ·I)` in
  R^{D_mri}, `x_ecg = Cecg[y_ecg] + N(0, σ·I)` in R^{D_ecg}, where `C*` are fixed per-class mean
  vectors and σ (an SNR knob) is set so unimodal classifiers are strong but not perfect (mimic
  ~95% MRI; realistic ECG). `D_mri`/`D_ecg` default to the real embedding widths.
- CLI: `--n --seed --lambda --snr --d-mri --d-ecg`. Output `tools/crossmodal_sim_<λ>.npz`
  (x_mri, x_ecg, y_mri, y_ecg, train/test split) + a JSON manifest.

### 2. Cross-modal model — `tools/crossmodal_model.py`
One small shared head class (linear or 1-hidden-layer MLP, torch). Instantiate as:
- `ECG→MRI` (in D_ecg → softmax 4) and `MRI→ECG` (in D_mri → softmax 8) — the cross-modal
  predictors;
- `MRI→MRI` and `ECG→ECG` unimodal sanity classifiers (must be strong → validates features are
  learnable).

### 3. Train — `tools/train_crossmodal.py`
Train all four heads for a given dataset/λ; save weights/metrics under `tools/`.

### 4. Evaluate — `tools/eval_crossmodal.py`
- **λ-sweep**: for λ ∈ {0.0, 0.1, …, 1.0}, train+eval both cross-modal directions; report
  accuracy + macro one-vs-rest AUROC with **bootstrap 95% CIs** (mirror `bootstrap_cis.py`).
- **Chance baseline**: predict the class base-rate; cross-modal scores are compared against it.
- **λ=0 negative control**: assert cross-modal ≈ chance (within CI).
- **Permutation test**: at each λ, shuffle the ECG↔MRI pairing and confirm the cross-modal
  signal collapses to chance (independent confirmation the signal is the planted coupling, not
  an artifact).
- Write `tools/crossmodal_metrics.json` + a human-readable results table + a **λ-sweep plot**
  (matplotlib Agg PNG under `tools/`).

### 5. Documentation — `maybe read/ECG_MRI_CROSSMODAL_SIM.md` (match where briefs live)
The vision (future 4-modality paired cohort; cross-modal prediction goal); the exact generative
model + coupling matrix; what the experiment proves and does NOT prove; the λ-sweep results
table + plot; the λ=0 control and permutation results; **the swap-in path** (replace the
synthetic generator with real encoder embeddings — `get_mri_classifier`/`get_ecg_models` pooled
features — once same-patient paired data is collected; the train/eval code is unchanged);
limitations; and exactly what paired data + study design a future clinical answer requires. Add
a cross-referenced section to `maybe read/VALIDATION.md` and a tools entry in `CLAUDE.md`.

## Verification (run these; report ACTUAL output before claiming done)

From repo root (venv active):
```
python tools/sim_crossmodal_data.py --n 6000 --seed 0 --lambda 0.6   # writes .npz + manifest
python tools/train_crossmodal.py   --data tools/crossmodal_sim_0.6.npz
python tools/eval_crossmodal.py    --sweep                            # λ-sweep + CIs + λ=0 control + permutation + plot
```
Backend sanity (you changed nothing on the request path — must stay green):
```
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run        # MUST be "No changes detected"
python manage.py test tests.test_doctor_isolation tests.test_health
```
Tests (fast — synthetic; put under `tools/` tests or `backend/tests/`):
- generator is **deterministic** for a fixed seed; manifest round-trips; coupling matrix rows
  sum to 1 and reduce to the marginal at λ=0.
- **no-leakage assertion**: with λ=0, a cross-modal classifier scores within CI of chance.
- **recovery**: cross-modal accuracy at λ=0.8 is materially above chance and above the λ=0.2
  score (monotonic trend).
- unimodal sanity classifiers score high (features are learnable).
- shapes/probabilities valid (softmax sums to 1, values in [0,1]).

## Definition of done

- A reproducible, fully-synthetic pipeline (`sim_crossmodal_data` → `train_crossmodal` →
  `eval_crossmodal`) that plants a tunable ECG↔MRI coupling and demonstrates **bidirectional**
  cross-modal recovery, with a **λ-sweep + bootstrap CIs + λ=0 negative control + permutation
  test**, all artifacts persisted and re-runnable to identical numbers.
- A methodology document that states the future vision, the generative model, the honest
  "machinery-not-clinical" framing, the λ-sweep results, and the concrete swap-in path to real
  encoder embeddings when paired data arrives.
- No contract broken; `manage.py check` clean; no migration; no oversold claims.
- Report what you verified with the **actual command output** (the λ-sweep table, the λ=0
  control, the permutation result).

## Suggested order
1. `sim_crossmodal_data.py` + determinism/leakage/coupling tests (TDD) → verify.
2. `crossmodal_model.py` + `train_crossmodal.py`; confirm unimodal sanity is high and λ=0
   cross-modal ≈ chance → verify.
3. `eval_crossmodal.py` λ-sweep + CIs + permutation + plot → verify monotonic recovery.
4. Write `ECG_MRI_CROSSMODAL_SIM.md` + VALIDATION.md section + CLAUDE.md tools entry.
5. Full verification sweep, then a final self-review against the honest-framing rules.

Let the **λ-sweep with the λ=0 control** — not any single accuracy number — be the result you
stand behind.
