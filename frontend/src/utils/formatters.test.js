import { describe, it, expect } from 'vitest';

import { formatPercent, formatBytes } from './formatters.js';

describe('formatPercent', () => {
  it('formats a fraction as a 2-dp percentage', () => {
    expect(formatPercent(0.954)).toBe('95.40%');
    expect(formatPercent(0)).toBe('0.00%');
    expect(formatPercent(1)).toBe('100.00%');
  });
  it('returns an em-dash for non-numbers', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(undefined)).toBe('—');
    expect(formatPercent('x')).toBe('—');
  });
});

describe('formatBytes', () => {
  it('scales to the right unit', () => {
    expect(formatBytes(0)).toBe('0.0 B');
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB');
  });
  it('returns an em-dash for non-numbers', () => {
    expect(formatBytes('x')).toBe('—');
    expect(formatBytes(null)).toBe('—');
  });
});
