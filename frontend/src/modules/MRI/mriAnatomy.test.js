import { describe, it, expect } from 'vitest';

import { mapMriToHighlight } from './mriAnatomy.js';

const ids = (h) => h.regions.map((r) => r.id);

describe('mapMriToHighlight', () => {
  it('a detected tumour highlights the cerebrum (brain)', () => {
    const h = mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'glioma', result_confidence: 0.9 });
    expect(h.organ).toBe('brain');
    expect(ids(h)).toEqual(['cerebrum']);
    expect(h.findingCodes).toEqual(['glioma']);
    expect(h.normal).toBe(false);
  });

  it('carries the tumour type as the finding code', () => {
    expect(mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'pituitary', result_confidence: 0.8 }).findingCodes).toEqual(['pituitary']);
    expect(mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'Meningioma', result_confidence: 0.8 }).findingCodes).toEqual(['meningioma']);
  });

  it('notumor / no_tumor produce no highlight', () => {
    expect(mapMriToHighlight({ result_tumor_detected: false, result_tumor_type: 'notumor' }).normal).toBe(true);
    expect(mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'no_tumor' }).normal).toBe(true);
  });

  it('severity scales with classifier confidence', () => {
    expect(mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'glioma', result_confidence: 0.95 }).regions[0].severity).toBe('high');
    expect(mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'glioma', result_confidence: 0.5 }).regions[0].severity).toBe('medium');
  });

  it('is null-safe', () => {
    expect(mapMriToHighlight(undefined).normal).toBe(true);
    expect(mapMriToHighlight({}).regions).toEqual([]);
  });
});
