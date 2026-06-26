import { NavLink } from 'react-router-dom';
import { Brain, FileCog, FileText, Heart, HeartPulse, Home, LogOut, Users, Waves, X } from 'lucide-react';

import { useAuth } from '../../hooks/useAuth.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

const LINKS = [
  { to: '/',         labelKey: 'nav.dashboard', icon: Home,       end: true, accent: 'neuro' },
  { to: '/patients', labelKey: 'nav.patients',  icon: Users,      accent: 'blue' },
  { to: '/mri',      labelKey: 'nav.mri',       icon: Brain,      accent: 'neuro' },
  { to: '/ecg',      labelKey: 'nav.ecg',       icon: Heart,      accent: 'cardio' },
  { to: '/eeg',      labelKey: 'nav.eeg',       icon: Waves,      accent: 'violet' },
  { to: '/echo',     labelKey: 'nav.echo',      icon: HeartPulse, accent: 'amber' },
  { to: '/reports',  labelKey: 'nav.reports',   icon: FileText,   accent: 'neuro' },
];

// Technician-only entry (matches the IsTechnician-gated backend endpoint and the
// role-gated /convert route in App.jsx).
const TECHNICIAN_LINK = { to: '/convert', labelKey: 'nav.convert', icon: FileCog, accent: 'violet' };

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
  const { logout, user } = useAuth();
  const { t } = useI18n();
  const { colors } = useTokens();
  const links = user?.role === 'technician' ? [...LINKS, TECHNICIAN_LINK] : LINKS;
  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-30 lg:hidden" onClick={onClose} />
      )}
      <aside
        className={
          'fixed lg:static inset-y-0 left-0 z-40 w-60 flex flex-col shrink-0 relative '
          + 'transform transition-transform lg:transform-none glass '
          + (mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0')
        }
        style={{ borderRight: '1px solid var(--edge)', zIndex: 20 }}
      >
        {/* brand */}
        <div className="p-5 flex items-center justify-between" style={{ borderBottom: '1px solid var(--edge)' }}>
          <div className="flex items-center gap-3">
            <img
              src="/neuracard-logo.png"
              alt="NeuraCard"
              className="w-9 h-9 rounded-lg object-contain"
            />
            <div>
              <div className="font-mono font-semibold text-hi text-sm leading-tight tracking-wider">NEURACARD</div>
              <div className="text-[10px] text-low leading-tight tracking-[0.3em] uppercase">Constantine 2</div>
            </div>
          </div>
          <button
            type="button" onClick={onClose}
            className="lg:hidden text-low hover:text-hi p-1" aria-label={t('nav.closeMenu')}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {links.map(({ to, labelKey, icon: Icon, end, accent }) => {
            const accentHex = colors[accent];
            return (
              <NavLink
                key={to} to={to} end={end} onClick={onClose}
                className="group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
                style={({ isActive }) => ({
                  color: isActive ? colors.textHi : colors.textMid,
                  background: isActive ? `linear-gradient(90deg, ${accentHex}22, transparent)` : 'transparent',
                  boxShadow: isActive ? `inset 2px 0 0 ${accentHex}, 0 0 18px ${accentHex}18` : 'none',
                })}
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      size={18}
                      style={{
                        color: isActive ? accentHex : colors.textLow,
                        filter: isActive ? `drop-shadow(0 0 6px ${accentHex})` : 'none',
                        transition: 'color .2s, filter .2s',
                      }}
                    />
                    <span>{t(labelKey)}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="p-3" style={{ borderTop: '1px solid var(--edge)' }}>
          <div className="px-3 mb-1 text-[10px] text-low tracking-[0.3em] uppercase">{t('nav.signedInAs')}</div>
          <div className="px-3 mb-3 text-sm font-medium text-hi truncate">
            {user?.full_name || user?.email || t('common.unknown')}
          </div>
          <button
            type="button" onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all"
            style={{ color: 'var(--cardio)' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgb(var(--rgb-cardio) / 0.12)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <LogOut size={18} />
            <span>{t('nav.signOut')}</span>
          </button>
        </div>
      </aside>
    </>
  );
}
