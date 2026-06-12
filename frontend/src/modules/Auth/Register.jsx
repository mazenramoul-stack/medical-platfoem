import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Activity, Lock, Loader2, Mail, User } from 'lucide-react';
import toast from 'react-hot-toast';

import AmbientBackground from '../../components/fx/AmbientBackground.jsx';
import ThemeLangControls from '../../components/UI/ThemeLangControls.jsx';
import { clearError, register } from '../../store/slices/authSlice.js';
import { ROLES } from '../../utils/constants.js';
import { isValidEmail } from '../../utils/validators.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function Register() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { loading, error, isAuthenticated } = useSelector((s) => s.auth);
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm: '',
    role: 'doctor',
  });

  useEffect(() => {
    if (isAuthenticated) navigate('/', { replace: true });
  }, [isAuthenticated, navigate]);
  useEffect(() => () => dispatch(clearError()), [dispatch]);

  const onChange = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const emailOk    = isValidEmail(form.email);
  const passwordOk = form.password.length >= 8;
  const matchOk    = form.password && form.password === form.confirm;
  const nameOk     = form.full_name.trim().length >= 2;
  const canSubmit  = emailOk && passwordOk && matchOk && nameOk && !loading;

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) {
      if (!nameOk)        toast.error(t('auth.register.nameRequired'));
      else if (!emailOk)  toast.error(t('auth.register.emailInvalid'));
      else if (!passwordOk) toast.error(t('auth.register.passwordMin'));
      else if (!matchOk)  toast.error(t('auth.register.passwordsNoMatch'));
      return;
    }
    try {
      const { full_name, email, password, role } = form;
      await dispatch(register({ full_name, email, password, role })).unwrap();
      toast.success(t('auth.register.accountCreated'));
    } catch (msg) {
      toast.error(String(msg || t('auth.register.registrationFailed')));
    }
  };

  const inputCls =
    'w-full pl-9 pr-3 py-2 rounded-lg text-sm bg-paneldeep text-hi border border-edge focus:outline-none focus:ring-2 focus:ring-neuro/70 transition';

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden bg-surface">
      <AmbientBackground />
      <ThemeLangControls className="absolute top-4 right-4 z-20" />
      <div className="w-full max-w-md relative z-10 animate-fade-up">
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl text-ink mb-4"
            style={{ background: 'linear-gradient(135deg, var(--neuro), var(--violet))', boxShadow: '0 0 28px var(--glow-strong)' }}
          >
            <Activity size={30} />
          </div>
          <h1 className="text-2xl font-mono font-bold text-hi">{t('auth.register.title')}</h1>
          <p className="text-sm text-mid mt-1">{t('auth.register.subtitle')}</p>
        </div>

        <div className="holo-panel p-7" style={{ boxShadow: '0 0 50px var(--glow-soft)' }}>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <div>
              <label htmlFor="reg-full-name" className="block text-sm font-medium text-mid mb-1">
                {t('auth.register.fullName')}
              </label>
              <div className="relative">
                <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                <input
                  id="reg-full-name" type="text" required value={form.full_name} onChange={onChange('full_name')}
                  autoComplete="name"
                  className={inputCls}
                  placeholder={t('auth.register.fullNamePlaceholder')}
                />
              </div>
            </div>
            <div>
              <label htmlFor="reg-email" className="block text-sm font-medium text-mid mb-1">
                {t('auth.register.email')}
              </label>
              <div className="relative">
                <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                <input
                  id="reg-email" type="email" required value={form.email} onChange={onChange('email')}
                  autoComplete="username"
                  className={inputCls}
                />
              </div>
            </div>
            <div>
              <label htmlFor="reg-password" className="block text-sm font-medium text-mid mb-1">
                {t('auth.register.password')}
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                <input
                  id="reg-password" type="password" required value={form.password} onChange={onChange('password')}
                  autoComplete="new-password"
                  className={inputCls}
                />
              </div>
              <p className="text-xs text-low mt-1">{t('auth.register.passwordHint')}</p>
            </div>
            <div>
              <label htmlFor="reg-confirm" className="block text-sm font-medium text-mid mb-1">
                {t('auth.register.confirmPassword')}
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                <input
                  id="reg-confirm" type="password" required value={form.confirm} onChange={onChange('confirm')}
                  autoComplete="new-password"
                  className={
                    'w-full pl-9 pr-3 py-2 rounded-lg text-sm bg-paneldeep text-hi border focus:outline-none focus:ring-2 focus:ring-neuro/70 transition '
                    + (form.confirm && !matchOk ? 'border-cardio' : 'border-edge')
                  }
                />
              </div>
              {form.confirm && !matchOk && (
                <p className="text-xs text-cardio mt-1">{t('auth.register.passwordsNoMatch')}</p>
              )}
            </div>
            <div>
              <label htmlFor="reg-role" className="block text-sm font-medium text-mid mb-1">
                {t('auth.register.role')}
              </label>
              <select
                id="reg-role" value={form.role} onChange={onChange('role')}
                className="w-full px-3 py-2 rounded-lg text-sm bg-paneldeep text-hi border border-edge focus:outline-none focus:ring-2 focus:ring-neuro/70"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{t(`auth.register.roles.${r.value}`)}</option>
                ))}
              </select>
            </div>

            {error && (
              <div className="text-sm text-cardio bg-red-50 border border-edge rounded-md px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 text-ink py-2.5 rounded-lg font-semibold transition disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg, var(--neuro), var(--violet))', boxShadow: '0 0 24px var(--glow-strong)' }}
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? t('auth.register.creatingAccount') : t('auth.register.createAccount')}
            </button>
          </form>

          <p className="text-sm text-low text-center mt-6">
            {t('auth.register.haveAccount')}{' '}
            <Link to="/login" className="text-neuro font-medium hover:underline">{t('auth.register.signIn')}</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
