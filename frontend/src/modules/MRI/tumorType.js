/**
 * Canonicalize a brain-tumour class label so the frontend dictionaries and i18n
 * keys match regardless of whether the backend emitted the HuggingFace
 * '_tumor'-suffixed form (e.g. 'glioma_tumor' — the deployed Swin config's
 * id2label) or the bare form ('glioma').
 *
 * Mirrors the backend `_normalize_tumor_label` in apps/inference/mri_pipeline.py:
 *   'glioma_tumor'       -> 'glioma'
 *   'meningioma_tumor'   -> 'meningioma'
 *   'pituitary_tumor'    -> 'pituitary'
 *   'no_tumor'/'notumor' -> preserved as-is (the UI keys on both spellings)
 * Bare or unknown labels pass through lower-cased and trimmed.
 *
 * @param {string|null|undefined} raw - the raw `result_tumor_type` from the API.
 * @returns {string} the canonical label key.
 */
export function normalizeTumorType(raw) {
  const t = String(raw ?? '').toLowerCase().trim();
  if (t === 'no_tumor' || t === 'notumor') return t;
  return t.endsWith('_tumor') ? t.slice(0, -'_tumor'.length) : t;
}
