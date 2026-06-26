import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Loader2, Lock, Mail } from 'lucide-react';
import toast from 'react-hot-toast';

import AmbientBackground from '../../components/fx/AmbientBackground.jsx';
import Scene3D from '../../components/three/Scene3D.jsx';
import Brain3D from '../../components/three/Brain3D.jsx';
import Heart3D from '../../components/three/Heart3D.jsx';
import ThemeLangControls from '../../components/UI/ThemeLangControls.jsx';
import { clearError, login } from '../../store/slices/authSlice.js';
import { isValidEmail } from '../../utils/validators.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

export default function Login() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useI18n();
  const { colors } = useTokens();
  const { loading, error, isAuthenticated } = useSelector((s) => s.auth);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState({ email: false, password: false });

  useEffect(() => {
    if (isAuthenticated) {
      const redirectTo = location.state?.from?.pathname || '/';
      navigate(redirectTo, { replace: true });
    }
  }, [isAuthenticated, navigate, location.state]);

  useEffect(() => () => dispatch(clearError()), [dispatch]);

  const emailError = touched.email && !isValidEmail(email) ? t('auth.login.emailInvalid') : null;
  const passwordError = touched.password && password.length < 6 ? t('auth.login.passwordMin') : null;
  const canSubmit = isValidEmail(email) && password.length >= 6 && !loading;

  const onSubmit = async (e) => {
    e.preventDefault();
    setTouched({ email: true, password: true });
    if (!canSubmit) return;
    try {
      await dispatch(login({ email, password })).unwrap();
      toast.success(t('auth.login.welcomeBack'));
    } catch (msg) {
      toast.error(String(msg || t('auth.login.loginFailed')));
    }
  };

  const inputCls = (bad) =>
    'w-full pl-9 pr-3 py-2.5 rounded-lg text-sm bg-paneldeep text-hi focus:outline-none focus:ring-2 focus:ring-neuro/70 transition '
    + (bad ? 'border border-cardio' : 'border border-edge');

  const chips = [
    [t('auth.login.chipBrain'), colors.neuro],
    [t('auth.login.chipHeart'), colors.cardio],
    [t('auth.login.chipRealtime'), colors.violet],
  ];

  return (
    <div className="min-h-screen relative overflow-hidden bg-surface">
      <AmbientBackground />
      <ThemeLangControls className="absolute top-4 right-4 z-20" />

      <div className="relative z-10 min-h-screen grid lg:grid-cols-2">
        {/* ---- 3D hero ---- */}
        <div className="hidden lg:flex flex-col justify-center px-12 xl:px-20">
          <div className="font-mono text-[11px] tracking-[0.4em] text-neuro uppercase mb-3">
            {t('auth.login.brandTag')}
          </div>
          <h1 className="font-mono font-bold text-hi leading-none mb-4"
              style={{ fontSize: 'clamp(40px,5vw,72px)', letterSpacing: '-0.02em' }}>
            NEURA<span className="text-neuro">CARD</span>
          </h1>
          <p className="text-mid max-w-md leading-relaxed mb-2">
            {t('auth.login.heroDescription')}
          </p>

          <Scene3D accent={colors.neuro} height={380} camera={{ position: [0, 0, 5.4], fov: 45 }}>
            <group position={[-1.35, 0.15, 0]} scale={0.82}><Brain3D accent={colors.neuro} /></group>
            <group position={[1.45, -0.1, 0]} scale={0.7}><Heart3D accent={colors.cardio} /></group>
          </Scene3D>

          <div className="flex gap-8 mt-2">
            {chips.map(([label, c]) => (
              <div key={label} className="font-mono text-[10px] tracking-[0.3em]" style={{ color: c }}>{label}</div>
            ))}
          </div>
        </div>

        {/* ---- form ---- */}
        <div className="flex items-center justify-center px-4 py-10">
          <div className="w-full max-w-md animate-fade-up">
            {/* compact mobile hero */}
            <div className="lg:hidden mb-6">
              <Scene3D accent={colors.neuro} height={200} camera={{ position: [0, 0, 4.6], fov: 45 }}>
                <Brain3D accent={colors.neuro} scale={0.9} />
              </Scene3D>
              <h1 className="font-mono font-bold text-hi text-3xl text-center mt-2">
                NEURA<span className="text-neuro">CARD</span>
              </h1>
            </div>

            <div className="holo-panel p-7" style={{ boxShadow: '0 0 50px var(--glow-soft)' }}>
              <img src="/neuracard-logo.png" alt="NeuraCard" className="w-20 h-20 mx-auto mb-4 object-contain" />
              <h2 className="text-lg font-mono font-bold text-hi mb-1 tracking-wide">{t('auth.login.accessTerminal')}</h2>
              <p className="text-xs text-low mb-6">{t('auth.login.subtitle')}</p>
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-xs font-medium text-mid mb-1.5 tracking-wide uppercase">
                    {t('auth.login.email')}
                  </label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                    <input
                      id="email" type="email" value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      onBlur={() => setTouched((prev) => ({ ...prev, email: true }))}
                      autoComplete="username"
                      className={inputCls(emailError)}
                      placeholder="doctor@example.com"
                    />
                  </div>
                  {emailError && <p className="text-xs text-cardio mt-1">{emailError}</p>}
                </div>
                <div>
                  <label htmlFor="password" className="block text-xs font-medium text-mid mb-1.5 tracking-wide uppercase">
                    {t('auth.login.password')}
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-low pointer-events-none" />
                    <input
                      id="password" type="password" value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onBlur={() => setTouched((prev) => ({ ...prev, password: true }))}
                      autoComplete="current-password"
                      className={inputCls(passwordError)}
                    />
                  </div>
                  {passwordError && <p className="text-xs text-cardio mt-1">{passwordError}</p>}
                </div>

                {error && (
                  <div className="text-sm text-cardio bg-red-50 border border-edge rounded-md px-3 py-2">{error}</div>
                )}

                <button
                  type="submit" disabled={loading}
                  className="w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-ink transition disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ background: 'linear-gradient(135deg, var(--neuro), var(--violet))', boxShadow: '0 0 24px var(--glow-strong)' }}
                >
                  {loading && <Loader2 size={16} className="animate-spin" />}
                  {loading ? t('auth.login.authenticating') : t('auth.login.signIn')}
                </button>
              </form>

              <p className="text-sm text-low text-center mt-6">
                {t('auth.login.noAccount')}{' '}
                <Link to="/register" className="text-neuro font-medium hover:underline">{t('auth.login.register')}</Link>
              </p>
            </div>

            <p className="text-[11px] text-center text-low mt-6 tracking-wide">
              Université Abdelhamid Mehri – Constantine 2 · 2025 / 2026
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
