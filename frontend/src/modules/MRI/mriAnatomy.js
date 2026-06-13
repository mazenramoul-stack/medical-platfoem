/**
 * Pure mapping from an MRI result envelope to a 3D-brain highlight descriptor.
 *
 * HONESTY: the U-Net mask is a 2D per-slice segmentation (no 3D coordinate), and
 * the Swin classifier gives a tumour TYPE, not a 3D location. So the 3D brain only
 * indicates that a tumour was detected (cerebrum), and the panel caption points to
 * the 2D scan/overlay for the actual location. No lobe/region is invented.
 */
export function mapMriToHighlight(mri) {
  const type = String((mri && mri.result_tumor_type) || '').toLowerCase();
  const detected = !!(mri && mri.result_tumor_detected);
  const isTumor = detected && type && type !== 'notumor' && type !== 'no_tumor';

  if (!isTumor) return { organ: 'brain', regions: [], findingCodes: [], normal: true };

  const conf = mri && typeof mri.result_confidence === 'number' ? mri.result_confidence : 1;
  const severity = conf >= 0.66 ? 'high' : 'medium';
  return {
    organ: 'brain',
    regions: [{ id: 'cerebrum', severity }],
    findingCodes: [type],
    normal: false,
  };
}
