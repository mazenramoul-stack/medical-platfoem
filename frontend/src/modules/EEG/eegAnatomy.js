/**
 * Pure mapping from an EEG (BIOT/IIIC) result envelope to a 3D-brain highlight.
 *
 * HONESTY: the 6-class IIIC output only distinguishes GENERALIZED (both
 * hemispheres) from LATERALIZED (one hemisphere) — and for lateralized it does
 * NOT say which side. So generalized patterns glow the whole cerebrum; lateralized
 * patterns glow one hemisphere as a schematic, with the panel caption stating the
 * side is not localized by the model. No per-electrode / lobe detail exists.
 */
const EEG_MAP = {
  SZ: { region: 'cerebrum', severity: 'high' },    // seizure
  GPD: { region: 'cerebrum', severity: 'high' },   // generalized periodic discharges
  GRDA: { region: 'cerebrum', severity: 'medium' }, // generalized rhythmic delta
  LPD: { region: 'left', severity: 'high' },        // lateralized periodic discharges
  LRDA: { region: 'left', severity: 'medium' },     // lateralized rhythmic delta
};

export function mapEegToHighlight(eeg) {
  const pattern = (eeg && eeg.result_dominant_pattern) || '';
  const entry = EEG_MAP[pattern];
  if (!entry) return { organ: 'brain', regions: [], findingCodes: [], normal: true };
  return {
    organ: 'brain',
    regions: [{ id: entry.region, severity: entry.severity }],
    findingCodes: [pattern],
    normal: false,
  };
}
