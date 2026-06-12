import { useLocation } from 'react-router-dom';
import { Bell, Menu, User } from 'lucide-react';

import Badge from '../UI/Badge.jsx';
import ThemeLangControls from '../UI/ThemeLangControls.jsx';
import { useAuth } from '../../hooks/useAuth.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const TITLE_KEYS = {
  '/':          'nav.dashboard',
  '/patients':  'nav.patients',
  '/mri':       'nav.mri',
  '/ecg':       'nav.ecg',
  '/eeg':       'nav.eeg',
  '/echo':      'nav.echo',
  '/reports':   'nav.reports',
};

function titleKeyFor(pathname) {
  if (TITLE_KEYS[pathname]) return TITLE_KEYS[pathname];
  if (pathname.startsWith('/patients/new')) return 'nav.newPatient';
  if (pathname.endsWith('/edit'))            return 'nav.editPatient';
  if (pathname.startsWith('/patients/'))    return 'nav.patientDetail';
  if (pathname.startsWith('/mri/'))         return 'nav.mriResult';
  if (pathname.startsWith('/ecg/'))         return 'nav.ecgResult';
  if (pathname.startsWith('/eeg/'))         return 'nav.eegResult';
  if (pathname.startsWith('/echo/'))        return 'nav.echoResult';
  if (pathname.startsWith('/reports'))      return 'nav.reports';
  return 'nav.medicalAi';
}

export default function Navbar({ onMenuClick = () => {} }) {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { t } = useI18n();
  const title = t(titleKeyFor(pathname));
  return (
    <header
      className="h-14 glass flex items-center justify-between px-4 lg:px-6 shrink-0 relative"
      style={{ borderBottom: '1px solid var(--edge)', zIndex: 10 }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button" onClick={onMenuClick}
          className="lg:hidden text-low hover:text-hi p-1.5 rounded"
          aria-label={t('nav.openMenu')}
        >
          <Menu size={20} />
        </button>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--neuro)', boxShadow: '0 0 8px var(--neuro)' }} />
        <h1 className="text-base font-mono font-bold text-hi truncate tracking-wide">{title}</h1>
      </div>
      <div className="flex items-center gap-3 lg:gap-4">
        <ThemeLangControls className="hidden sm:flex" />
        <button
          type="button"
          className="text-low hover:text-neuro relative p-1.5 rounded transition-colors"
          title={t('nav.notifications')}
        >
          <Bell size={20} />
        </button>
        <div className="flex items-center gap-2">
          <div className="text-right hidden sm:block">
            <div className="text-sm font-medium text-hi leading-tight">{user?.full_name || '—'}</div>
            <div className="leading-tight"><Badge variant="primary">{user?.role || t('nav.doctor')}</Badge></div>
          </div>
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink"
            style={{ background: 'linear-gradient(135deg, var(--neuro), var(--violet))', boxShadow: '0 0 14px var(--glow-strong)' }}
          >
            <User size={18} />
          </div>
        </div>
      </div>
    </header>
  );
}
