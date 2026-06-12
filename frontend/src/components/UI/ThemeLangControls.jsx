import { Moon, Sun } from 'lucide-react';

import { useTheme } from '../../theme/ThemeContext.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const LANGS = ['en', 'fr'];

/** Compact theme (sun/moon) + language (EN/FR) switcher, used in the navbar
 *  and floated on the auth pages. */
export default function ThemeLangControls({ className = '' }) {
  const { isDark, toggleTheme } = useTheme();
  const { lang, setLang, t } = useI18n();

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={t('nav.toggleTheme')}
        title={t('nav.toggleTheme')}
        className="p-1.5 rounded-lg border border-edge text-low hover:text-hi hover:border-neuro transition-colors"
      >
        {isDark ? <Sun size={16} /> : <Moon size={16} />}
      </button>
      <div
        className="flex rounded-lg border border-edge overflow-hidden font-mono text-[10px] tracking-wider"
        role="group"
        aria-label={t('nav.language')}
      >
        {LANGS.map((l) => (
          <button
            key={l}
            type="button"
            onClick={() => setLang(l)}
            aria-pressed={lang === l}
            className={
              'px-2 py-1.5 uppercase transition-colors '
              + (lang === l ? 'bg-neuro text-ink font-bold' : 'text-low hover:text-hi')
            }
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}
