import { describe, it, expect } from 'vitest';

import { mapEcgToHighlight } from './ecgAnatomy.js';

// Build a result envelope with the given detected pathology codes (each at the
// given probability, default 0.9). Non-listed codes are present but not detected.
const ecgWith = (detectedCodes, { bpm, prob = 0.9 } = {}) => {
  const all = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC'];
  const result_pathology_probabilities = {};
  for (const code of all) {
    const detected = detectedCodes.includes(code);
    result_pathology_probabilities[code] = { probability: detected ? prob : 0.02, detected };
  }
  return {
    result_pathology_probabilities,
    result_hrv_metrics: bpm == null ? {} : { heart_rate_bpm: bpm },
  };
};

const ids = (h) => h.regions.map((r) => r.id).sort();
const codes = (h) => h.findings.map((f) => f.code).sort();

describe('mapEcgToHighlight', () => {
  it('maps RBBB to the right ventricle (structural, not rate-only)', () => {
    const h = mapEcgToHighlight(ecgWith(['RBBB']));
    expect(ids(h)).toContain('rv');
    expect(h.rateOnly).toBe(false);
    expect(h.normal).toBe(false);
    expect(codes(h)).toContain('RBBB');
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

  it('treats STACH (only rate finding) as rate-only with no structure', () => {
    const h = mapEcgToHighlight(ecgWith(['STACH']));
    expect(ids(h)).toEqual([]);
    expect(h.rateOnly).toBe(true);
    expect(h.rateScore).toBeGreaterThan(0);
    expect(codes(h)).toContain('STACH');
  });

  it('treats SBRAD (only rate finding) as rate-only', () => {
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

  it('shows ALL detected structural findings, each scored by probability', () => {
    const ecg = {
      result_pathology_probabilities: {
        RBBB: { probability: 0.95, detected: true },
        AFIB: { probability: 0.70, detected: true },
        STACH: { probability: 0.80, detected: true }, // rate → no structure
        LBBB: { probability: 0.02, detected: false },
      },
    };
    const h = mapEcgToHighlight(ecg);
    expect(ids(h)).toEqual(['la', 'ra', 'rv']); // RBBB + AFIB structures (STACH none)
    expect(h.rateOnly).toBe(false);
    expect(codes(h)).toEqual(['AFIB', 'RBBB', 'STACH']);
    // green strength tracks probability: RBBB (0.95) brighter than AFIB (0.70)
    const rv = h.regions.find((r) => r.id === 'rv');
    const la = h.regions.find((r) => r.id === 'la');
    expect(rv.score).toBeGreaterThan(la.score);
  });

  it('a rate + structural mix shows the structure (not rate-only)', () => {
    const ecg = {
      result_pathology_probabilities: {
        SBRAD: { probability: 0.92, detected: true }, // headline rate finding
        RBBB: { probability: 0.40, detected: true },  // weaker structural
      },
    };
    const h = mapEcgToHighlight(ecg);
    expect(h.rateOnly).toBe(false);
    expect(ids(h)).toEqual(['rv']);
    expect(codes(h)).toEqual(['RBBB', 'SBRAD']);
  });

  it('region score reflects each finding probability (gradation)', () => {
    const ecg = {
      result_pathology_probabilities: {
        RBBB: { probability: 0.90, detected: true },
        LBBB: { probability: 0.40, detected: true },
      },
    };
    const h = mapEcgToHighlight(ecg);
    const rv = h.regions.find((r) => r.id === 'rv');
    const lv = h.regions.find((r) => r.id === 'lv');
    expect(rv.score).toBeCloseTo(0.90, 5);
    expect(lv.score).toBeCloseTo(0.40, 5);
    expect(rv.score).toBeGreaterThan(lv.score);
  });

  it('passes through the measured heart rate, rounded', () => {
    expect(mapEcgToHighlight(ecgWith(['RBBB'], { bpm: 78.4 })).beatsPerMinute).toBe(78);
    expect(mapEcgToHighlight(ecgWith(['RBBB'])).beatsPerMinute).toBe(null);
  });

  it('is null-safe on a missing/empty envelope', () => {
    expect(mapEcgToHighlight(undefined).normal).toBe(true);
    expect(mapEcgToHighlight({}).regions).toEqual([]);
  });
});
