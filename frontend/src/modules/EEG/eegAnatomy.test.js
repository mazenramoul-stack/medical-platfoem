import { describe, it, expect } from 'vitest';

import { mapEegToHighlight, channelXY } from './eegAnatomy.js';

const ids = (h) => h.regions.map((r) => r.id);

describe('mapEegToHighlight', () => {
  it('generalized patterns highlight the whole cerebrum (both hemispheres)', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'GPD' });
    expect(h.organ).toBe('brain');
    expect(ids(h)).toEqual(['cerebrum']);
    expect(h.findingCodes).toEqual(['GPD']);
    expect(h.normal).toBe(false);
  });

  it('seizure activity highlights the cerebrum at high severity', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'SZ' });
    expect(ids(h)).toEqual(['cerebrum']);
    expect(h.regions[0].severity).toBe('high');
  });

  it('lateralized patterns highlight one hemisphere (side not localized)', () => {
    const lpd = mapEegToHighlight({ result_dominant_pattern: 'LPD' });
    expect(ids(lpd)).toEqual(['left']);
    expect(lpd.findingCodes).toEqual(['LPD']);
    const lrda = mapEegToHighlight({ result_dominant_pattern: 'LRDA' });
    expect(ids(lrda)).toEqual(['left']);
    expect(lrda.regions[0].severity).toBe('medium');
  });

  it('rhythmic generalized delta is medium severity', () => {
    expect(mapEegToHighlight({ result_dominant_pattern: 'GRDA' }).regions[0].severity).toBe('medium');
  });

  it('Other / missing produces no highlight', () => {
    expect(mapEegToHighlight({ result_dominant_pattern: 'Other' }).normal).toBe(true);
    expect(mapEegToHighlight({}).normal).toBe(true);
    expect(mapEegToHighlight(undefined).normal).toBe(true);
  });

  it('ignores a SHAP arg missing top_channels (stays label-only)', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'LPD' }, { per_channel_importance: {} });
    expect(ids(h)).toEqual(['left']);
    expect(h.gradcamFocus).toBeUndefined();
  });
});

describe('mapEegToHighlight (SHAP-enriched)', () => {
  const shap = (top, target = 'LPD') => ({
    per_channel_importance: { [top[0]]: 1 },
    top_channels: top,
    target_class: target,
  });

  it('picks the RIGHT hemisphere when top channels lean right (side the label cannot give)', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'LPD' }, shap(['P4-O2', 'C4-P4', 'F4-C4']));
    expect(ids(h)).toEqual(['right']);
    expect(h.gradcamFocus).toBeDefined();
    expect(h.gradcamFocus.x).toBeGreaterThan(0); // right side of the brain panel
    expect(h.normal).toBe(false);
  });

  it('picks the LEFT hemisphere when top channels lean left', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'LPD' }, shap(['FP1-F7', 'F7-T7', 'T7-P7']));
    expect(ids(h)).toEqual(['left']);
    expect(h.gradcamFocus.x).toBeLessThan(0);
  });

  it('still emits a marker for an explained class with no mapped region (e.g. Other)', () => {
    const h = mapEegToHighlight({ result_dominant_pattern: 'Other' }, shap(['FP1-F7'], 'Other'));
    expect(h.regions).toEqual([]);
    expect(h.gradcamFocus).toBeDefined();
    expect(h.normal).toBe(false);
  });
});

describe('channelXY', () => {
  it('returns the midpoint of a valid bipolar channel', () => {
    const xy = channelXY('FP1-F7');
    expect(xy[0]).toBeCloseTo(0.3, 6);
    expect(xy[1]).toBeCloseTo(0.21, 6);
  });
  it('returns null for an unknown / empty channel', () => {
    expect(channelXY('XX-YY')).toBeNull();
    expect(channelXY('')).toBeNull();
  });
});
