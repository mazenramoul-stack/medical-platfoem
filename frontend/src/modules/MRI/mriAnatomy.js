/**
 * Pure mapping from an MRI result (+ optional segmentation-mask analysis) to a
 * 3D-brain highlight descriptor.
 *
 * The generic 3D brain is NOT auto-coloured (no whole-cerebrum glow, no mask point):
 * that implies a precision the models don't have. Tumour PRESENCE drives only the
 * finding-code text. The ONE positioned marker is the optional, on-demand Grad-CAM peak
 * (`gradcamFocus`) — shown after the user clicks Explain. It marks where the *classifier*
 * looked; for fine spatial detail use the 2D Grad-CAM/SHAP overlays (on the actual scan).
 */
import { normalizeTumorType } from './tumorType.js';

export function mapMriToHighlight(mri, maskInfo = null, gradcamPeak = null) {
  const type = normalizeTumorType(mri && mri.result_tumor_type);
  const knownType = ['glioma', 'meningioma', 'pituitary'].includes(type) ? type : null;
  // Optional on-demand Grad-CAM peak (already projected to brain coords).
  const gradcamFocus = gradcamPeak
    ? { x: gradcamPeak.x, y: gradcamPeak.y, severity: 'high' }
    : undefined;

  // 1. Segmentation decides yes/no. No auto brain colouring on a "yes" — just the
  //    finding code (+ the Grad-CAM dot if an explanation was requested).
  if (maskInfo) {
    if (!maskInfo.present) return { organ: 'brain', regions: [], findingCodes: [], normal: true };
    return {
      organ: 'brain',
      regions: [],
      ...(gradcamFocus ? { gradcamFocus } : {}),
      findingCodes: [knownType || 'tumor'],
      normal: false,
    };
  }

  // 2. No mask analysed → classifier verdict. Still no auto colouring; finding code only.
  const detected = !!(mri && mri.result_tumor_detected);
  const isTumor = detected && type && type !== 'notumor' && type !== 'no_tumor';
  if (!isTumor) return { organ: 'brain', regions: [], findingCodes: [], normal: true };

  return {
    organ: 'brain',
    regions: [],
    ...(gradcamFocus ? { gradcamFocus } : {}),
    findingCodes: [type],
    normal: false,
  };
}
