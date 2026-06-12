export const isValidEmail = (v) =>
  typeof v === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

export const isStrongPassword = (v) =>
  typeof v === 'string' && v.length >= 8;

export const isPositiveInt = (v) => Number.isInteger(Number(v)) && Number(v) > 0;
