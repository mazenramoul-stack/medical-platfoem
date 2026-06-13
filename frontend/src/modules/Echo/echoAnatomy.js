/**
 * Pure mapping from an Echo result envelope to a 3D-heart highlight descriptor.
 *
 * HONESTY: EchoNet outputs a GLOBAL left-ventricle ejection fraction (and an LV
 * segmentation), not regional wall motion. So the only structure we implicate is
 * the left ventricle, with severity from the EF category — never an anterior /
 * inferior / septal wall. The panel caption states this.
 */
export function mapEchoToHighlight(echo) {
  const cat = (echo && echo.result_ef_category) || '';
  const ef = echo && typeof echo.result_ef === 'number' ? echo.result_ef : null;

  let severity = null;
  let code = null;
  if (/^reduced/i.test(cat) || (cat === '' && ef != null && ef < 40)) {
    severity = 'high';
    code = 'EF_REDUCED';
  } else if (/^mild/i.test(cat) || (cat === '' && ef != null && ef < 50)) {
    severity = 'medium';
    code = 'EF_MILD';
  }

  if (!severity) {
    return { organ: 'heart', regions: [], findingCodes: [], beatsPerMinute: null, rateOnly: false, normal: true };
  }
  return {
    organ: 'heart',
    regions: [{ id: 'lv', severity }],
    findingCodes: [code],
    beatsPerMinute: null,
    rateOnly: false,
    normal: false,
  };
}
