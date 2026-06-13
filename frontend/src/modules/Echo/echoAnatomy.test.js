import { describe, it, expect } from 'vitest';

import { mapEchoToHighlight } from './echoAnatomy.js';

const ids = (h) => h.regions.map((r) => r.id);

describe('mapEchoToHighlight', () => {
  it('reduced EF highlights the left ventricle at high severity', () => {
    const h = mapEchoToHighlight({ result_ef: 30, result_ef_category: 'Reduced' });
    expect(h.organ).toBe('heart');
    expect(ids(h)).toEqual(['lv']);
    expect(h.regions[0].severity).toBe('high');
    expect(h.findingCodes).toEqual(['EF_REDUCED']);
    expect(h.normal).toBe(false);
  });

  it('mildly reduced EF highlights the LV at medium severity', () => {
    const h = mapEchoToHighlight({ result_ef: 45, result_ef_category: 'Mildly reduced' });
    expect(ids(h)).toEqual(['lv']);
    expect(h.regions[0].severity).toBe('medium');
    expect(h.findingCodes).toEqual(['EF_MILD']);
  });

  it('normal EF produces no highlight', () => {
    const h = mapEchoToHighlight({ result_ef: 62, result_ef_category: 'Normal' });
    expect(h.regions).toEqual([]);
    expect(h.normal).toBe(true);
  });

  it('falls back to the EF value when category is missing', () => {
    expect(mapEchoToHighlight({ result_ef: 32 }).regions[0].severity).toBe('high');
    expect(mapEchoToHighlight({ result_ef: 46 }).regions[0].severity).toBe('medium');
    expect(mapEchoToHighlight({ result_ef: 60 }).normal).toBe(true);
  });

  it('is null-safe', () => {
    expect(mapEchoToHighlight(undefined).normal).toBe(true);
    expect(mapEchoToHighlight({}).regions).toEqual([]);
  });
});
