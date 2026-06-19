// Shared ECG headline-diagnosis logic, used by both the result page and the
// history list so they always agree.
//
// When the model flags a pathology (probability crosses its threshold) we trust
// the backend verdict. When NOTHING crosses threshold we don't blindly call it
// "Normal": if the strongest pathology probability outweighs the "normal"
// likelihood (p > 1 - p, i.e. p > 0.5), surface it as a tentative
// "Maybe <pathology>" instead — e.g. 1AVB at 79% (threshold 90%) becomes
// "Maybe 1st Degree AV Block" rather than "Normal Sinus Rhythm" at 21%. Only
// when normal genuinely beats every pathology (top p <= 0.5) is it Normal.
//
// @param {object} ecg - an ECG analysis record (detail or list item)
// @param {(key: string, vars?: object) => string} t - i18n translator
// @returns {{ label: string, confidence: number|null|undefined, state: 'abnormal'|'maybe'|'normal' }}
// The tentative "maybe" pathology, surfaced only when NOTHING crosses threshold.
// Picks the (below-threshold) class CLOSEST to its own threshold — the one the
// model is nearest to flagging — rather than the highest-probability class, and
// only if its probability outweighs the "Normal Sinus Rhythm" likelihood
// (1 - the strongest pathology probability). Returns { code, probability } or
// null. Single source of truth shared by the headline, the 3D anatomy mapper,
// and the per-pathology table highlight.
export function maybePathology(probs) {
  if (!probs || typeof probs !== 'object') return null;
  const entries = Object.entries(probs);
  if (!entries.length || entries.some(([, r]) => r && r.detected)) return null;
  // "Normal Sinus Rhythm" confidence = 1 - the strongest pathology signal.
  const maxProb = Math.max(...entries.map(([, r]) => r?.probability ?? 0));
  const normalConf = 1 - maxProb;
  // Candidate = the class with the smallest gap to its own detection threshold.
  let candidate = null;
  let smallestGap = Infinity;
  for (const [code, r] of entries) {
    const probability = r?.probability ?? 0;
    const threshold = typeof r?.threshold === 'number' ? r.threshold : 0.5;
    const gap = threshold - probability;
    if (gap < smallestGap) {
      smallestGap = gap;
      candidate = { code, probability };
    }
  }
  return candidate && candidate.probability > normalConf ? candidate : null;
}

export function deriveDiagnosis(ecg, t) {
  const base = {
    label: ecg.result_arrhythmia_type || '—',
    confidence: ecg.result_confidence,
    state: ecg.result_arrhythmia_detected ? 'abnormal' : 'normal',
  };
  if (ecg.result_arrhythmia_detected) return base;
  const maybe = maybePathology(ecg.result_pathology_probabilities);
  if (maybe) {
    const name = t(`ecg.pathologies.${maybe.code}`);
    const typeName = name === `ecg.pathologies.${maybe.code}` ? maybe.code : name;
    return { label: t('ecg.result.maybe', { type: typeName }), confidence: maybe.probability, state: 'maybe' };
  }
  return base;
}

// ECG diagnosis state -> shared Badge variant.
export const DIAG_VARIANT = { abnormal: 'danger', maybe: 'warning', normal: 'success' };
