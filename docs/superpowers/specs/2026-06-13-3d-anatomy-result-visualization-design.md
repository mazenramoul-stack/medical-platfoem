# 3D Anatomy Result Visualization — Design

**Date:** 2026-06-13
**Status:** Approved (design); ECG proof-of-concept in build.

## Goal

On each analysis result page (ECG, Echo, MRI, EEG), add an interactive 3D anatomy
panel (heart for ECG/Echo, brain for MRI/EEG) that **highlights the implicated
anatomical structure/region** for the model's finding — rotatable, zoomable, with
hover labels and a severity color scale — **always honestly captioned**.

## Honesty constraint (the core principle)

The models do **not** output exact coordinates. The honest localization ceiling
per modality (verified against the pipeline outputs):

| Modality | Organ | Honest ceiling | What we highlight |
|---|---|---|---|
| ECG  | Heart | region/side (conduction) | RBBB→right ventricle, LBBB→left, PVC→ventricles, AFIB→atria, 1AVB→AV node, STACH/SBRAD→SA node (rate, **no wall**) |
| Echo | Heart | structure only | left ventricle (global function); color by EF severity; **no wall segments** |
| MRI  | Brain | region/side | the **real 2D tumor mask** + tumor-type gross region (pituitary→central) |
| EEG  | Brain | region/side | lateralized→one hemisphere, generalized→both; **no per-electrode detail** |

Every render carries a caveat: *"Schematic highlight of the implicated structure —
not a registered localization. Decision-support only, not a diagnosis."* Rate-only
ECG findings (STACH/SBRAD) explicitly state they are not localized to a wall.

We only **remap existing model outputs**; no new model output is invented.

## Approach (chosen: A)

- **A — Shared `Anatomy3DPanel` + per-modality pure mapping functions.** One reusable
  panel; each modality has a pure `map<Modality>ToHighlight(result)` returning a
  highlight descriptor. The 3D models gain a `highlight` prop. Mapping functions are
  pure → unit-tested in Vitest. (Chosen.)
- B — bespoke per-page 3D panels (duplicates canvas wiring; rejected).
- C — 2D annotated SVG (lighter, PDF-friendly, less "wow") → folded in only as the
  WebGL-off fallback.

## Architecture

- **`frontend/src/components/three/Anatomy3DPanel.jsx`** (new) — wraps the existing
  `Scene3D` (canvas/lighting/orbit) + `Heart3D`/`Brain3D`; rotate+zoom on; hover→label;
  side legend; honesty caption. Props: `organ`, `accent`, `highlight`, `caption`.
- **`highlight` contract** (data↔3D interface):
  ```js
  { regions: [{ id: 'rv', severity: 'high'|'medium'|'low'|'none' }],
    beatsPerMinute: 78,        // ECG only — drives the real heartbeat rate
    findingCodes: ['RBBB'],    // for the component to i18n into captions
    rateOnly: false, normal: false }
  ```
- **`Heart3D` gains a `highlight` prop** — boosts emissive on existing meshes
  (LV lathe, RV bulge, atria) and drops a small glowing marker for the conduction
  nodes (SA/AV) that aren't meshes. Severity → color from `useTokens()`
  (low→accent, medium→warning, high→danger).
- **`frontend/src/modules/ECG/ecgAnatomy.js`** (new, pure) — `mapEcgToHighlight(ecg)`.
  Reads `result_pathology_probabilities` (per-code `{detected, probability}`) and
  `result_hrv_metrics.heart_rate_bpm`. Returns the descriptor. **Returns codes/region
  ids only — no i18n** (component does the labels), keeping it pure/testable.
- **Placement:** a new full-width "Anatomical view" card in `ECGResult.jsx`, directly
  under the primary-diagnosis panel. **Additive** — the ECG plot, HRV, heart-rate,
  flags, pathology table all stay.
- **i18n:** new `frontend/src/i18n/locales/anatomy3d.js` (EN/FR) — region names,
  finding captions, the caveat line, hover labels. Registered in `locales/index.js`.

## ECG region mapping (the clinical contract, tested)

| Finding | region ids | Honest note |
|---|---|---|
| RBBB | `rv` | right bundle / RV conduction — not a wall |
| LBBB | `lv` | left bundle / LV conduction — not a wall |
| PVC  | `lv`,`rv` (ventricles) | ectopic ventricular origin |
| AFIB | `la`,`ra` (atria) | atrial rhythm |
| 1AVB | `av-node` | nodal conduction delay |
| STACH / SBRAD | `sa-node` (+ bpm) | **rate finding — not localized to a wall** |
| none detected | _none_ | no localized conduction abnormality |

Multiple detected findings → union of regions; component lists all in the caption.
The 3D heart **beats at the patient's measured `heart_rate_bpm`** (real data).

## Testing

- Vitest unit tests for `mapEcgToHighlight` — one assertion per pathology (detected →
  expected region ids), rate-only flag for STACH/SBRAD, empty/normal case, bpm
  pass-through. Written **before** the implementation (TDD).
- `npm run lint` (0 errors) + `npm test` + `npm run build` must pass.
- Respects `prefers-reduced-motion` (models already do); WebGL-off → `Scene3D`
  fallback + the caption/caveat text (info preserved without the canvas).
- EN/FR key-tree parity in `anatomy3d.js`.

## Out of scope

- The PDF report (ReportLab, backend) stays 2D — the 3D panel is a web-only view.
- No new model outputs / no source localization / no wall-segment analysis.
- Echo, MRI, EEG panels come **after** the ECG PoC is reviewed and approved
  (same shared component + their own pure mapping functions).

## Rollout

1. **PoC:** ECG heart (this build) — full panel + mapping + tests + wiring, reviewed live.
2. After approval: replicate to Echo (LV + EF severity), MRI (2D mask + type region),
   EEG (hemisphere) via their own `map*ToHighlight` functions.
