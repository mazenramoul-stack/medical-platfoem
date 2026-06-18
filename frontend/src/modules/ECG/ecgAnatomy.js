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
  findingCodes: [],
  beatsPerMinute,
  rateOnly: false,
  normal: true,
});

export function mapEcgToHighlight(ecg) {
  const probs = (ecg && ecg.result_pathology_probabilities) || {};
  const rawBpm = ecg && ecg.result_hrv_metrics ? ecg.result_hrv_metrics.heart_rate_bpm : undefined;
  const beatsPerMinute = typeof rawBpm === 'number' && rawBpm > 0 ? Math.round(rawBpm) : null;

  // The heart reflects the PRIMARY diagnosis — the highest-probability *detected*
  // pathology, exactly as the backend picks the headline diagnosis. The
  // thresholds can flag several pathologies at once (especially in the optional
  // recall-first mode); highlighting all of them is noisy and can contradict the
  // single diagnosis the doctor sees in the header.
  let primary = null;
  let best = -1;
  for (const [code, r] of Object.entries(probs)) {
    if (r && r.detected && typeof r.probability === 'number' && r.probability > best) {
      best = r.probability;
      primary = code;
    }
  }

  if (!primary) return EMPTY(beatsPerMinute);

  const entry = ECG_PATHOLOGY_MAP[primary];
  const severity = severityFor(best);
  const regions = entry ? entry.regions.map((id) => ({ id, severity })) : [];

  return {
    organ: 'heart',
    regions,
    findingCodes: [primary],
    beatsPerMinute,
    rateOnly: !!(entry && entry.rateOnly),
    normal: false,
  };
}
