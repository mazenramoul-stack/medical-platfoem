/**
 * Pure mapping from an ECG result envelope to a 3D-heart "highlight" descriptor.
 *
 * HONESTY: ecglib outputs per-pathology probabilities, not coordinates. We map
 * each *detected* finding to the heart structure it legitimately implicates —
 * the exact conduction element (SA node, AV node, bundle branch) or chamber
 * where the pathology arises. Sinus rate findings (STACH/SBRAD) localise to the
 * SA node, the sinus pacemaker in the upper right atrium.
 * Returns region ids + finding codes only — the component does the i18n labels,
 * keeping this function pure and unit-testable.
 */

import { maybePathology } from './diagnosis.js';

// Heart structures the 3D model can highlight (chambers, conduction nodes, and
// the two bundle branches of the His-Purkinje system).
export const HEART_REGION_IDS = ['lv', 'rv', 'la', 'ra', 'av-node', 'sa-node', 'rbb', 'lbb'];

// Detected pathology code -> the EXACT implicated structure(s). IRBBB/CRBBB are
// historical ecglib aliases for RBBB; mapped to the right bundle branch too.
const ECG_PATHOLOGY_MAP = {
  // Bundle-branch blocks localise to the conduction fascicle itself — NOT the
  // ventricular myocardium (that is PVC). The fascicle marker is tiny, so we
  // also softly glow the ventricle it serves (`context`) to make the affected
  // SIDE read clearly, without claiming the ventricle muscle is the lesion.
  RBBB: { regions: ['rbb'], context: ['rv'], rateOnly: false },
  IRBBB: { regions: ['rbb'], context: ['rv'], rateOnly: false },
  CRBBB: { regions: ['rbb'], context: ['rv'], rateOnly: false },
  LBBB: { regions: ['lbb'], context: ['lv'], rateOnly: false },
  PVC: { regions: ['lv', 'rv'], rateOnly: false },
  // AFIB arises in the atria, often near the pulmonary veins of the left atrium.
  AFIB: { regions: ['la', 'ra'], rateOnly: false },
  '1AVB': { regions: ['av-node'], rateOnly: false },
  // Sinus rate findings originate at the SA node (sinus pacemaker, upper RA).
  STACH: { regions: ['sa-node', 'ra'], rateOnly: false },
  SBRAD: { regions: ['sa-node', 'ra'], rateOnly: false },
};

function severityFor(probability) {
  if (probability >= 0.66) return 'high';
  if (probability >= 0.33) return 'medium';
  return 'low';
}

const EMPTY = (beatsPerMinute) => ({
  organ: 'heart',
  regions: [],
  contextRegions: [],
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

  // No confirmed detection, but a tentative "maybe" pathology (the class closest
  // to its threshold, above the normal likelihood) drives the same structural
  // highlight as a detected finding — so the 3D view tracks the "Maybe …" headline.
  let maybe = false;
  if (!primary) {
    const m = maybePathology(probs);
    if (m) { primary = m.code; best = m.probability; maybe = true; }
  }

  if (!primary) return EMPTY(beatsPerMinute);

  const entry = ECG_PATHOLOGY_MAP[primary];
  const severity = severityFor(best);
  const regions = entry ? entry.regions.map((id) => ({ id, severity })) : [];
  // Context = the chamber the implicated fascicle serves, glowed softly (low)
  // for orientation only — it is NOT listed as a lesion in the legend.
  const contextRegions = entry && entry.context
    ? entry.context.map((id) => ({ id, severity: 'low' }))
    : [];

  return {
    organ: 'heart',
    regions,
    contextRegions,
    findingCodes: [primary],
    beatsPerMinute,
    rateOnly: !!(entry && entry.rateOnly),
    normal: false,
    maybe,
  };
}
