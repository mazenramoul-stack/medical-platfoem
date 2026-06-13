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

  // --- segmentation-driven path (maskInfo supplied) ---
  it('a present mask localizes a focus marker (no whole-brain glow)', () => {
    const h = mapMriToHighlight(
      { result_tumor_detected: true, result_tumor_type: 'glioma' },
      { present: true, x: 0.4, y: -0.2 },
    );
    expect(h.regions).toEqual([]); // no whole-cerebrum glow
    expect(h.focus).toMatchObject({ x: 0.4, y: -0.2 });
    expect(h.findingCodes).toEqual(['glioma']);
    expect(h.normal).toBe(false);
  });

  it('an empty mask means no tumour — even if the classifier flagged one', () => {
    const h = mapMriToHighlight(
      { result_tumor_detected: true, result_tumor_type: 'glioma' },
      { present: false },
    );
    expect(h.normal).toBe(true);
    expect(h.focus).toBeUndefined();
  });

  it('a present mask with no known type falls back to a generic tumour code', () => {
    const h = mapMriToHighlight({ result_tumor_type: '' }, { present: true, x: 0, y: 0 });
    expect(h.findingCodes).toEqual(['tumor']);
    expect(h.focus).toBeDefined();
  });
});
