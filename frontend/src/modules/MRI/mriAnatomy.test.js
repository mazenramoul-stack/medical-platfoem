import { describe, it, expect } from 'vitest';

import { mapMriToHighlight } from './mriAnatomy.js';

describe('mapMriToHighlight', () => {
  it('a detected tumour produces no brain colouring (finding code only)', () => {
    const h = mapMriToHighlight({ result_tumor_detected: true, result_tumor_type: 'glioma', result_confidence: 0.9 });
    expect(h.organ).toBe('brain');
    expect(h.regions).toEqual([]);
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

  it('is null-safe', () => {
    expect(mapMriToHighlight(undefined).normal).toBe(true);
    expect(mapMriToHighlight({}).regions).toEqual([]);
  });

  // --- segmentation-driven path (maskInfo supplied) ---
  it('a present mask produces no brain colouring or point marker', () => {
    const h = mapMriToHighlight(
      { result_tumor_detected: true, result_tumor_type: 'glioma' },
      { present: true, x: 0.4, y: -0.2 },
    );
    expect(h.regions).toEqual([]); // no whole-brain glow
    expect(h.focus).toBeUndefined(); // no projected point on the generic brain
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
    expect(h.regions).toEqual([]);
  });

  it('emits gradcamFocus (only) when a Grad-CAM peak is supplied', () => {
    const h = mapMriToHighlight(
      { result_tumor_detected: true, result_tumor_type: 'glioma', result_confidence: 0.9 },
      null,
      { x: 0.2, y: -0.1 },
    );
    expect(h.gradcamFocus).toEqual({ x: 0.2, y: -0.1, severity: 'high' });
    expect(h.regions).toEqual([]); // still no whole-brain colouring
  });
});
