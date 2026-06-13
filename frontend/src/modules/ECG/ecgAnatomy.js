/**
 * Pure mapping from an ECG result envelope to a 3D-heart "highlight" descriptor.
 *
 * HONESTY: ecglib outputs per-pathology probabilities, not coordinates. We map
 * each *detected* finding to the heart structure it legitimately implicates
 * (conduction pathway / chamber). Rate findings (STACH/SBRAD) are flagged
 * `rateOnly` so the UI can state they are NOT localized to a myocardial wall.
 * Returns region ids + finding codes only — the component does the i18n labels,
 * keeping this function pure and unit-testable.
 */

// Heart structures the 3D model can highlight.
export const HEART_REGION_IDS = ['lv', 'rv', 'la', 'ra', 'av-node', 'sa-node'];

// Detected pathology code -> implicated structure(s) + whether it is a rate
// finding (rhythm/rate, no wall localization). IRBBB/CRBBB are historical
// ecglib aliases for RBBB; mapped to the same structure for robustness.
const ECG_PATHOLOGY_MAP = {
  RBBB: { regions: ['rv'], rateOnly: false },
  IRBBB: { regions: ['rv'], rateOnly: false },
  CRBBB: { regions: ['rv'], rateOnly: false },
  LBBB: { regions: ['lv'], rateOnly: false },
  PVC: { regions: ['lv', 'rv'], rateOnly: false },
  AFIB: { regions: ['la', 'ra'], rateOnly: false },
  '1AVB': { regions: ['av-node'], rateOnly: false },
  // Rate findings have NO localized site — they contribute no structural region.
  // The UI shows the whole heart "examined" (no pinpoint) for these.
  STACH: { regions: [], rateOnly: true },
  SBRAD: { regions: [], rateOnly: true },
};

function severityFor(probability) {
  if (probability >= 0.66) return 'high';
  if (probability >= 0.33) return 'medium';
  return 'low';
}

const EMPTY = (beatsPerMinute) => ({
  organ: 'heart',
  regions: [],
  findings: [],
  findingCodes: [],
  beatsPerMinute,
  rateOnly: false,
  normal: true,
});

export function mapEcgToHighlight(ecg) {
  const probs = (ecg && ecg.result_pathology_probabilities) || {};
  const rawBpm = ecg && ecg.result_hrv_metrics ? ecg.result_hrv_metrics.heart_rate_bpm : undefined;
  const beatsPerMinute = typeof rawBpm === 'number' && rawBpm > 0 ? Math.round(rawBpm) : null;

  // Show every DETECTED finding, ranked by probability. Each carries its
  // probability so the UI can grade the highlight colour by confidence
  // (a low-probability flag glows faintly, a high one strongly).
  const detected = Object.entries(probs)
    .filter(([, r]) => r && r.detected)
    .map(([code, r]) => ({ code, probability: typeof r.probability === 'number' ? r.probability : 0 }))
    .sort((a, b) => b.probability - a.probability);

  if (detected.length === 0) return EMPTY(beatsPerMinute);

  const findings = detected.map(({ code, probability }) => ({
    code,
    probability,
    severity: severityFor(probability),
    rateOnly: !!(ECG_PATHOLOGY_MAP[code] && ECG_PATHOLOGY_MAP[code].rateOnly),
  }));

  // Structural findings glow their structure; on a shared structure the
  // highest-probability finding wins. Rate findings contribute no region.
  const byRegion = new Map();
  for (const f of findings) {
    const entry = ECG_PATHOLOGY_MAP[f.code];
    if (!entry || entry.rateOnly) continue;
    for (const id of entry.regions) {
      const prev = byRegion.get(id);
      if (!prev || f.probability > prev.probability) {
        byRegion.set(id, { severity: f.severity, probability: f.probability });
      }
    }
  }
  const regions = [...byRegion.entries()].map(([id, v]) => ({ id, severity: v.severity, probability: v.probability }));

  return {
    organ: 'heart',
    regions,
    findings,
    findingCodes: findings.map((f) => f.code),
    beatsPerMinute,
    // only rate findings detected (no structural site) → whole-heart, no pinpoint
    rateOnly: regions.length === 0,
    normal: false,
  };
}
