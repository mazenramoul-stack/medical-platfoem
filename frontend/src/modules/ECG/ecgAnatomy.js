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
  beatsPerMinute,
  rateOnly: false,
  rateScore: null,
  normal: true,
});

export function mapEcgToHighlight(ecg) {
  const probs = (ecg && ecg.result_pathology_probabilities) || {};
  const rawBpm = ecg && ecg.result_hrv_metrics ? ecg.result_hrv_metrics.heart_rate_bpm : undefined;
  const beatsPerMinute = typeof rawBpm === 'number' && rawBpm > 0 ? Math.round(rawBpm) : null;

  // Every DETECTED pathology is shown, strongest first. Each structural finding
  // glows its structure with intensity ∝ its probability (high → strong green,
  // low → faint), so the colour strength mirrors the per-pathology confidence.
  // Rate findings (STACH/SBRAD) carry no structure — they're conveyed by the beat
  // rate + legend, and only paint the whole heart when nothing structural fired.
  const detected = Object.entries(probs)
    .filter(([, r]) => r && r.detected)
    .map(([code, r]) => ({ code, score: typeof r.probability === 'number' ? r.probability : 0 }))
    .sort((a, b) => b.score - a.score);

  if (detected.length === 0) return EMPTY(beatsPerMinute);

  const byScore = new Map(); // region id -> highest probability implicating it
  let anyStructural = false;
  let maxRate = 0;
  for (const { code, score } of detected) {
    const entry = ECG_PATHOLOGY_MAP[code];
    if (!entry) continue;
    if (entry.rateOnly) {
      maxRate = Math.max(maxRate, score);
      continue;
    }
    anyStructural = true;
    for (const id of entry.regions) byScore.set(id, Math.max(byScore.get(id) ?? 0, score));
  }

  const regions = [...byScore.entries()].map(([id, score]) => ({ id, score, severity: severityFor(score) }));

  return {
    organ: 'heart',
    regions,
    findings: detected,
    beatsPerMinute,
    rateOnly: !anyStructural, // only rate findings fired → whole-heart, no pinpoint
    rateScore: anyStructural ? null : (maxRate || 0.6),
    normal: false,
  };
}
