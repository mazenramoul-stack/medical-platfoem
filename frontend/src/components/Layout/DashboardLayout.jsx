import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import { Outlet } from 'react-router-dom';

import { useI18n } from '../../i18n/LanguageContext.jsx';
import AmbientBackground from '../fx/AmbientBackground.jsx';
import Navbar from './Navbar.jsx';
import Sidebar from './Sidebar.jsx';

export default function DashboardLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useI18n();
  return (
    <div className="min-h-screen flex bg-surface relative">
      <AmbientBackground />
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0 relative" style={{ zIndex: 1 }}>
        <Navbar onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 p-4 sm:p-6 overflow-auto">
          <Outlet />
        </main>
        <footer
          role="note"
          aria-label={t('common.disclaimerLabel')}
          className="border-t border-black/10 bg-surface px-4 py-2 text-[11px] leading-snug opacity-80 flex items-start gap-2"
        >
          <AlertTriangle size={14} className="text-warning mt-px shrink-0" aria-hidden="true" />
          <span>
            <strong className="font-semibold">{t('common.disclaimerLabel')}:</strong>{' '}
            {t('common.disclaimer')}
          </span>
        </footer>
      </div>
    </div>
  );
}
