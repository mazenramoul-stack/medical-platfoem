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
  it('maps RBBB to the right bundle branch (conduction, not the ventricle wall)', () => {
    const h = mapEcgToHighlight(ecgWith(['RBBB']));
    expect(ids(h)).toContain('rbb');
    expect(ids(h)).not.toContain('rv');
    expect(h.rateOnly).toBe(false);
    expect(h.normal).toBe(false);
    expect(h.findingCodes).toContain('RBBB');
  });

  it('maps LBBB to the left bundle branch', () => {
    const h = mapEcgToHighlight(ecgWith(['LBBB']));
    expect(ids(h)).toContain('lbb');
    expect(ids(h)).not.toContain('lv');
  });

  it('adds a low-severity context glow on the served ventricle for bundle-branch blocks', () => {
    const rbbb = mapEcgToHighlight(ecgWith(['RBBB']));
    expect(rbbb.contextRegions.map((r) => r.id)).toEqual(['rv']);
    expect(rbbb.contextRegions[0].severity).toBe('low');

    const lbbb = mapEcgToHighlight(ecgWith(['LBBB']));
    expect(lbbb.contextRegions.map((r) => r.id)).toEqual(['lv']);
    // The lesion itself stays the fascicle, not the ventricle wall.
    expect(ids(lbbb)).toEqual(['lbb']);
  });

  it('has no context regions for non-bundle-branch findings', () => {
    expect(mapEcgToHighlight(ecgWith(['1AVB'])).contextRegions).toEqual([]);
    expect(mapEcgToHighlight(ecgWith(['STACH'])).contextRegions).toEqual([]);
    expect(mapEcgToHighlight(ecgWith([])).contextRegions).toEqual([]);
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

  it('maps STACH to the SA node (sinus pacemaker, upper right atrium)', () => {
    const h = mapEcgToHighlight(ecgWith(['STACH']));
    expect(ids(h)).toEqual(['ra', 'sa-node']);
    expect(h.rateOnly).toBe(false);
    expect(h.normal).toBe(false);
    expect(h.findingCodes).toContain('STACH');
  });

  it('maps SBRAD to the SA node', () => {
    const h = mapEcgToHighlight(ecgWith(['SBRAD']));
    expect(h.rateOnly).toBe(false);
    expect(ids(h)).toEqual(['ra', 'sa-node']);
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
    expect(ids(h)).toEqual(['rbb']);
    expect(h.rateOnly).toBe(false);
  });

  it('highlights only the rate primary, not a co-occurring secondary finding', () => {
    // Sinus Tachycardia is the headline (highest probability); a secondary AFIB
    // flag from the liberal thresholds must NOT also light up the left atrium.
    const ecg = {
      result_pathology_probabilities: {
        STACH: { probability: 0.92, detected: true },
        AFIB: { probability: 0.40, detected: true },
      },
    };
    const h = mapEcgToHighlight(ecg);
    expect(h.findingCodes).toEqual(['STACH']);
    expect(ids(h)).toEqual(['ra', 'sa-node']); // SA node + right atrium only
    expect(ids(h)).not.toContain('la'); // AFIB's left atrium must not appear
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
