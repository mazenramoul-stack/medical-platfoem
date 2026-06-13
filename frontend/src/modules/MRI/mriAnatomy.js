/**
 * Pure mapping from an MRI result (+ optional segmentation-mask analysis) to a
 * 3D-brain highlight descriptor.
 *
 * Two paths, in order of honesty:
 *  1. SEGMENTATION available (`maskInfo` supplied): the U-Net mask decides yes/no
 *     and WHERE. `maskInfo.present` → a focus marker at the mask's location
 *     (`{x, y}` already in brain coords, projected from the 2D mask); `!present`
 *     → no tumour. This is the real localization the user asked for.
 *  2. No mask analysed (`maskInfo === null`, e.g. classify-only mode or the mask
 *     couldn't be read): fall back to the Swin classifier verdict and glow the
 *     whole cerebrum (no location available).
 *
 * HONESTY: the mask is a single 2D slice — `{x, y}` is its in-plane position
 * projected onto the brain; depth/slice level is unknown (panel caption says so).
 */
export function mapMriToHighlight(mri, maskInfo = null) {
  const type = String((mri && mri.result_tumor_type) || '').toLowerCase();
  const knownType = ['glioma', 'meningioma', 'pituitary'].includes(type) ? type : null;

  // 1. Segmentation drives the verdict + location.
  if (maskInfo) {
    if (!maskInfo.present) return { organ: 'brain', regions: [], findingCodes: [], normal: true };
    return {
      organ: 'brain',
      regions: [],
      focus: { x: maskInfo.x, y: maskInfo.y, severity: 'high' },
      findingCodes: [knownType || 'tumor'],
      normal: false,
    };
  }

  // 2. No mask analysed → classifier fallback (whole-cerebrum glow, no location).
  const detected = !!(mri && mri.result_tumor_detected);
  const isTumor = detected && type && type !== 'notumor' && type !== 'no_tumor';
  if (!isTumor) return { organ: 'brain', regions: [], findingCodes: [], normal: true };

  const conf = mri && typeof mri.result_confidence === 'number' ? mri.result_confidence : 1;
  const severity = conf >= 0.66 ? 'high' : 'medium';
  return { organ: 'brain', regions: [{ id: 'cerebrum', severity }], findingCodes: [type], normal: false };
}
