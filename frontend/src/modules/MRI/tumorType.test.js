import { describe, it, expect } from 'vitest';

import { normalizeTumorType } from './tumorType.js';

describe('normalizeTumorType', () => {
  it("strips the '_tumor' suffix the Swin config emits", () => {
    expect(normalizeTumorType('glioma_tumor')).toBe('glioma');
    expect(normalizeTumorType('meningioma_tumor')).toBe('meningioma');
    expect(normalizeTumorType('pituitary_tumor')).toBe('pituitary');
  });

  it('preserves the no-tumour labels in both spellings', () => {
    expect(normalizeTumorType('no_tumor')).toBe('no_tumor');
    expect(normalizeTumorType('notumor')).toBe('notumor');
  });

  it('passes bare labels through (idempotent)', () => {
    expect(normalizeTumorType('glioma')).toBe('glioma');
    expect(normalizeTumorType(normalizeTumorType('glioma_tumor'))).toBe('glioma');
  });

  it('lower-cases and trims', () => {
    expect(normalizeTumorType('  Glioma_Tumor ')).toBe('glioma');
    expect(normalizeTumorType('MENINGIOMA')).toBe('meningioma');
  });

  it('handles null / undefined / empty without throwing', () => {
    expect(normalizeTumorType(null)).toBe('');
    expect(normalizeTumorType(undefined)).toBe('');
    expect(normalizeTumorType('')).toBe('');
  });
});
