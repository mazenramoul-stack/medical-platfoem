import { describe, it, expect } from 'vitest';

import { mapEegToHighlight } from './eegAnatomy.js';

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
});
