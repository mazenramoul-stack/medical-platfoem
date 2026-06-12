import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { buildMessages } from './locales/index.js';

const STORAGE_KEY = 'mp-lang';
const LanguageContext = createContext(null);

function initialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'fr') return saved;
  } catch {
    /* storage unavailable */
  }
  return 'en';
}

function lookup(obj, path) {
  return path.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), obj);
}

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* storage unavailable */
    }
  }, [lang]);

  const messages = useMemo(() => buildMessages(lang), [lang]);
  const fallback = useMemo(() => buildMessages('en'), []);

  const t = useCallback(
    (key, vars) => {
      let s = lookup(messages, key);
      if (s === undefined) s = lookup(fallback, key);
      if (s === undefined || typeof s === 'object') return key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
      }
      return s;
    },
    [messages, fallback],
  );

  const toggleLang = useCallback(() => setLang((l) => (l === 'en' ? 'fr' : 'en')), []);

  const value = useMemo(() => ({ lang, setLang, toggleLang, t }), [lang, toggleLang, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useI18n must be used within <LanguageProvider>');
  return ctx;
}
