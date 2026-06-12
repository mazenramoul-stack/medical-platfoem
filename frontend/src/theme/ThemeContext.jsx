import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { getAccents, getColors } from './tokens.js';

const STORAGE_KEY = 'mp-theme';
const ThemeContext = createContext(null);

function initialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* storage unavailable */
  }
  return 'dark'; // default keeps the original dark-neon look
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);

  const value = useMemo(
    () => ({
      theme,
      isDark: theme === 'dark',
      setTheme,
      toggleTheme,
      colors: getColors(theme),
      accents: getAccents(theme),
    }),
    [theme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within <ThemeProvider>');
  return ctx;
}

/**
 * Theme-resolved hex tokens for code that cannot read CSS variables:
 * three.js materials, canvas 2D, chart.js options, and `${accent}55`-style
 * alpha-suffixed template literals. Re-renders consumers on theme switch.
 */
export function useTokens() {
  return useTheme();
}
