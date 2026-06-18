import { describe, it, expect } from 'vitest';

import { mapEcgToHighlight } from './ecgAnatomy.js';

// Build a result envelope with the given detected pathology codes.
const ecgWith = (detectedCodes, { bpm } = {}) => {
  const all = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC'];
  const result_pathology_probabilities = {};
  for (const code of all) {
    const detected = detectedCodes.includes(code);
    result_pathology_probabilities[code] = { probability: detected ? 0.9 : 0.02, detected };
  }
  return {
    result_pathology_probabilities,
    result_hrv_metrics: bpm == null ? {} : { heart_rate_bpm: bpm },
  };
};

const ids = (h) => h.regions.map((r) => r.id).sort();

describe('mapEcgToHighlight', () => {
  it('maps RBBB to the right ventricle (structural, not rate-only)', () => {
    const h = mapEcgToHighlight(ecgWith(['RBBB']));
    expect(ids(h)).toContain('rv');
    expect(h.rateOnly).toBe(false);
    expect(h.normal).toBe(false);
    expect(h.findingCodes).toContain('RBBB');
  });

  it('maps LBBB to the left ventricle', () => {
    expect(ids(mapEcgToHighlight(ecgWith(['LBBB'])))).toContain('lv');
  });

  it('maps PVC to both ventricles', () => {
    expect(ids(mapEcgToHighlight(ecgWith(['PVC'])))).toEqual(['lv', 'rv']);
  });

  it('maps AFIB to both atria', () => {
    expect(ids(mapEcgToHighlight(ecgWith(['AFIB'])))).toEqual(['la', 'ra']);
  });

  it('maps 1AVB to the AV node', () => {
    expect(ids(mapEcgToHighlight(ecgWith(['1AVB'])))).toContain('av-node');
  });

  it('treats STACH as a rate-only finding with NO localized structure', () => {
    const h = mapEcgToHighlight(ecgWith(['STACH']));
    expect(ids(h)).toEqual([]); // rate findings do not pinpoint a site
    expect(h.rateOnly).toBe(true);
    expect(h.normal).toBe(false);
    expect(h.findingCodes).toContain('STACH');
  });

  it('treats SBRAD as a rate-only finding with no structure', () => {
    const h = mapEcgToHighlight(ecgWith(['SBRAD']));
    expect(h.rateOnly).toBe(true);
    expect(ids(h)).toEqual([]);
  });

  it('returns no regions and normal=true when nothing is detected', () => {
    const h = mapEcgToHighlight(ecgWith([]));
    expect(h.regions).toEqual([]);
    expect(h.normal).toBe(true);
    expect(h.rateOnly).toBe(false);
  });

  it('highlights only the PRIMARY (highest-probability) detected finding', () => {
    const ecg = {
      result_pathology_probabilities: {
        RBBB: { probability: 0.95, detected: true },
        AFIB: { probability: 0.70, detected: true },
        STACH: { probability: 0.80, detected: true },
        LBBB: { probability: 0.02, detected: false },
      },
    };
    const h = mapEcgToHighlight(ecg);
    expect(h.findingCodes).toEqual(['RBBB']); // highest-probability detected
    expect(ids(h)).toEqual(['rv']);
    expect(h.rateOnly).toBe(false);
  });

  it('a rate primary stays rate-only even when a structural finding co-occurs lower', () => {
    // The screenshot case: Sinus Tachycardia is the headline; a secondary AFIB
    // flag from the liberal thresholds must NOT light up the atria.
    const ecg = {
      result_pathology_probabilities: {
        STACH: { probability: 0.92, detected: true },
        AFIB: { probability: 0.40, detected: true },
      },
    };
    const h = mapEcgToHighlight(ecg);
    expect(h.findingCodes).toEqual(['STACH']);
    expect(h.rateOnly).toBe(true);
    expect(ids(h)).toEqual([]); // no pinpoint
  });

  it('passes through the measured heart rate, rounded', () => {
    expect(mapEcgToHighlight(ecgWith(['RBBB'], { bpm: 78.4 })).beatsPerMinute).toBe(78);
    expect(mapEcgToHighlight(ecgWith(['RBBB'])).beatsPerMinute).toBe(null);
  });

  it('assigns a severity to each highlighted region', () => {
    const h = mapEcgToHighlight(ecgWith(['RBBB']));
    expect(['low', 'medium', 'high']).toContain(h.regions[0].severity);
  });

  it('is null-safe on a missing/empty envelope', () => {
    expect(mapEcgToHighlight(undefined).normal).toBe(true);
    expect(mapEcgToHighlight({}).regions).toEqual([]);
  });
});
