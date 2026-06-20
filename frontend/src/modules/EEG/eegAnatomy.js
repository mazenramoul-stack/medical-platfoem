/**
 * Pure mapping from an EEG (BIOT/IIIC) result envelope to a 3D-brain highlight.
 *
 * HONESTY: the bare 6-class IIIC label only distinguishes GENERALIZED (both
 * hemispheres) from LATERALIZED (one hemisphere) — and for lateralized it does NOT
 * say which side. So without an explanation, generalized patterns glow the whole
 * cerebrum and lateralized patterns glow one (placeholder) hemisphere, with the
 * panel caption stating the side is not localized by the model.
 *
 * WITH a SHAP explanation (per-channel importance), we CAN do better: the top
 * channels are electrode-localized, so we (a) place an approximate "where the model
 * looked" marker (gradcamFocus) projected from the top channel's scalp position, and
 * (b) for lateralized patterns, pick the actual hemisphere from whether the top
 * channels lean left or right — side localization the bare label cannot give.
 * Resolution is the coarse 16-channel bipolar montage and the marker is an
 * approximate scalp projection, NOT a validated EEG source localization.
 *
 * Back-compat: when no SHAP result is supplied, behaviour is byte-identical to the
 * original label-only mapping (mirrors mapMriToHighlight with/without a Grad-CAM peak).
 */

const EEG_MAP = {
  SZ: { region: 'cerebrum', severity: 'high' },    // seizure
  GPD: { region: 'cerebrum', severity: 'high' },   // generalized periodic discharges
  GRDA: { region: 'cerebrum', severity: 'medium' }, // generalized rhythmic delta
  LPD: { region: 'left', severity: 'high' },        // lateralized periodic discharges
  LRDA: { region: 'left', severity: 'medium' },     // lateralized rhythmic delta
};

// Approximate 10-20 scalp positions (nose-up top view), normalised nx/ny in [0,1]
// where nx is left→right across the head image and ny is front→back. Used both for
// the 2D topomap and to project the top channel into the 3D brain panel. Coarse by
// construction — these are schematic, not measured coordinates.
export const ELECTRODE_XY = {
  FP1: [0.40, 0.12], FP2: [0.60, 0.12],
  F7: [0.20, 0.30], F3: [0.38, 0.30], F4: [0.62, 0.30], F8: [0.80, 0.30],
  T7: [0.12, 0.50], C3: [0.35, 0.50], C4: [0.65, 0.50], T8: [0.88, 0.50],
  P7: [0.20, 0.70], P3: [0.38, 0.70], P4: [0.62, 0.70], P8: [0.80, 0.70],
  O1: [0.40, 0.88], O2: [0.60, 0.88],
};

// Midpoint scalp coordinate of a bipolar channel like "FP1-F7" → [nx, ny] or null.
export function channelXY(name) {
  const parts = String(name || '').split('-');
  const a = ELECTRODE_XY[parts[0]];
  const b = ELECTRODE_XY[parts[1]];
  if (!a || !b) return null;
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

// Hemisphere of a single electrode from 10-20 numbering: odd = left (-1), even =
// right (+1), midline 'z' = 0.
function electrodeSide(e) {
  const m = String(e || '').match(/\d+/);
  if (!m) return 0;
  return parseInt(m[0], 10) % 2 === 1 ? -1 : 1;
}

// Net left/right lean of a bipolar channel (sum of its two electrodes' sides).
function channelLean(name) {
  const parts = String(name || '').split('-');
  return electrodeSide(parts[0]) + electrodeSide(parts[1]);
}

export function mapEegToHighlight(eeg, shap = null) {
  const dominant = (eeg && eeg.result_dominant_pattern) || '';
  const hasShap = !!(shap && shap.per_channel_importance &&
    Array.isArray(shap.top_channels) && shap.top_channels.length);

  // No explanation → original label-only behaviour (unchanged).
  if (!hasShap) {
    const entry = EEG_MAP[dominant];
    if (!entry) return { organ: 'brain', regions: [], findingCodes: [], normal: true };
    return {
      organ: 'brain',
      regions: [{ id: entry.region, severity: entry.severity }],
      findingCodes: [dominant],
      normal: false,
    };
  }

  // SHAP enrichment: reflect the EXPLAINED class + its electrodes.
  const pattern = shap.target_class || dominant;
  const entry = EEG_MAP[pattern];
  const top = shap.top_channels;
  const lean = top.reduce((s, ch) => s + channelLean(ch), 0);
  const xy = channelXY(top[0]);
  // Project the top channel's scalp position into brain-panel coords — same formula
  // the MRI Grad-CAM peak uses (centred, flipped Y, per-axis scales).
  const gradcamFocus = xy
    ? { x: (xy[0] - 0.5) * 1.7, y: (0.5 - xy[1]) * 1.3, severity: entry ? entry.severity : 'medium' }
    : undefined;

  let regions = [];
  let findingCodes = [];
  if (entry) {
    // Override the side for lateralized patterns using the SHAP hemisphere lean —
    // the genuine upgrade: the bare label can't say which side.
    let region = entry.region;
    if (region === 'left' || region === 'right') region = lean > 0 ? 'right' : 'left';
    regions = [{ id: region, severity: entry.severity }];
    findingCodes = [pattern];
  }

  return {
    organ: 'brain',
    regions,
    findingCodes,
    ...(gradcamFocus ? { gradcamFocus } : {}),
    normal: regions.length === 0 && !gradcamFocus,
  };
}
