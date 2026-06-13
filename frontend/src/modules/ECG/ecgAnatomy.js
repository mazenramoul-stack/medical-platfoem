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

const SEVERITY_RANK = { none: 0, low: 1, medium: 2, high: 3 };

function severityFor(probability) {
  if (probability >= 0.66) return 'high';
  if (probability >= 0.33) return 'medium';
  return 'low';
}

const EMPTY = (beatsPerMinute) => ({
  organ: 'heart',
  regions: [],
  findingCodes: [],
  beatsPerMinute,
  rateOnly: false,
  normal: true,
});

export function mapEcgToHighlight(ecg) {
  const probs = (ecg && ecg.result_pathology_probabilities) || {};
  const rawBpm = ecg && ecg.result_hrv_metrics ? ecg.result_hrv_metrics.heart_rate_bpm : undefined;
  const beatsPerMinute = typeof rawBpm === 'number' && rawBpm > 0 ? Math.round(rawBpm) : null;

  const detected = Object.entries(probs)
    .filter(([, r]) => r && r.detected)
    .map(([code, r]) => ({ code, probability: typeof r.probability === 'number' ? r.probability : 0 }));

  if (detected.length === 0) return EMPTY(beatsPerMinute);

  const bySeverity = new Map(); // region id -> highest severity seen
  const findingCodes = [];
  let anyStructural = false;
  let anyRate = false;

  for (const { code, probability } of detected) {
    findingCodes.push(code);
    const entry = ECG_PATHOLOGY_MAP[code];
    if (!entry) continue;
    if (entry.rateOnly) anyRate = true;
    else anyStructural = true;
    const severity = severityFor(probability);
    for (const id of entry.regions) {
      const prev = bySeverity.get(id);
      if (!prev || SEVERITY_RANK[severity] > SEVERITY_RANK[prev]) bySeverity.set(id, severity);
    }
  }

  const regions = [...bySeverity.entries()].map(([id, severity]) => ({ id, severity }));

  return {
    organ: 'heart',
    regions,
    findingCodes,
    beatsPerMinute,
    // a rate finding with no co-occurring structural finding → no localized site
    rateOnly: anyRate && !anyStructural,
    normal: false,
  };
}
