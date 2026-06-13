// Vitest setup: registers @testing-library/jest-dom matchers (toBeInTheDocument, etc.)
// and clears localStorage between tests so auth state never leaks across cases.
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

afterEach(() => {
  localStorage.clear();
});
