# Theme + i18n conventions (light/dark + EN/FR)

How theming and internationalization work in this frontend, and the exact rules
for converting a component. Written June 2026 when light mode and FR were added.

## Theme system

- `darkMode: 'class'` — `ThemeProvider` (`src/theme/ThemeContext.jsx`) toggles
  `dark` on `<html>` and persists to `localStorage('mp-theme')`. Default: dark.
- All theme colors are CSS variables defined in `src/index.css`:
  `:root` holds the **light** palette, `.dark` holds the **dark-neon** palette.
- Tailwind custom colors (`bg-panel`, `text-neuro`, `border-edge`, …) resolve to
  those variables and therefore flip automatically. Alpha modifiers
  (`ring-neuro/70`) keep working — colors are defined from `--rgb-*` channel triplets.
- The legacy "dark shim" that remapped light utilities (`bg-white`,
  `text-gray-600`…) is now scoped under `.dark`, so the stock light utilities
  ARE the light theme. **Leave `bg-white` / `text-gray-*` / `bg-gray-*` /
  `border-gray-*` classes alone** — they render correctly in both themes.

### CSS variables (use in inline `style={{}}` and plain CSS)

| Variable | Light | Dark | Use for |
|---|---|---|---|
| `var(--bg)` | `#f4f6fb` | `#07070f` | page background (replaces inline `#07070f`) |
| `var(--panel)` | `#ffffff` | `#111122` | cards/panels (replaces `#111122`) |
| `var(--paneldeep)` | `#eef1f8` | `#0a0a0f` | inset surfaces (replaces `#0a0a0f`, `#0d0d18`) |
| `var(--edge)` | `#dde3ef` | `#1e1e2e` | borders (replaces `#1e1e2e`, `#16162a`, `#26263a`) |
| `var(--ink)` | `#ffffff` | `#07070f` | text on accent-gradient buttons |
| `var(--text-hi)` | `#0f172a` | `#f4f4fa` | high-emphasis text |
| `var(--text-mid)` | `#475569` | `#b9b9d0` | secondary text (replaces `#9a9ab5`) |
| `var(--text-low)` | `#5b6477` | `#8a8aa8` | tertiary text (replaces `#7c7c98`, `#61617a`) |
| `var(--neuro)` | `#0d9488` | `#00ffcc` | MRI/primary accent (replaces `#00ffcc`) |
| `var(--violet)` | `#7c3aed` | `#a855f7` | EEG accent (replaces `#a855f7`) |
| `var(--cardio)` | `#e11d48` | `#f43f5e` | ECG/heart accent (replaces `#f43f5e`) |
| `var(--amber)` | `#d97706` | `#fbbf24` | Echo accent (replaces `#fbbf24`) |
| `var(--blue)` | `#2563eb` | `#60a5fa` | Patients accent (replaces `#60a5fa`) |
| `var(--neuro-fg)` etc. | deep shades | bright pastels | **text/icons on tinted chips/badges** (`--violet-fg`, `--cardio-fg`, `--amber-fg`, `--blue-fg`) |
| `var(--glow-strong)`, `var(--glow-soft)` | faint teal | neon teal | glow shadows |

Channel triplets `--rgb-<name>` exist for every color above; use them for
translucent tints in inline styles: `background: 'rgb(var(--rgb-neuro) / 0.12)'`.

### Conversion rules for a component

1. **Inline hex → variables.** Replace every hardcoded theme hex in `style={{}}`
   per the table above (`'1px solid #1e1e2e'` → `'1px solid var(--edge)'`).
2. **Grey text depends on the file's era.** Decide per file:
   - *Light-era files* (use `bg-white` cards, `text-gray-900` headings, no neon
     hex): leave ALL `text-gray-*` / `bg-gray-*` classes alone — the `.dark`
     shim themes them.
   - *Dark-era flagship files* (use `holo-panel`/`glass`, `text-white`, inline
     neon hex): their `text-gray-400/500/600` were picked against a dark
     background and are too faint on white. Replace: `text-gray-400` →
     `text-mid`, `text-gray-500`/`text-gray-600` → `text-low` (both resolve to
     readable values in each theme).
3. **`text-white` is contextual:**
   - On an accent/gradient background (buttons, filled badges, avatar chips):
     keep `text-white` only if the element keeps white text in light mode too —
     usually it should become `text-ink` (white in light, dark in dark? NO —
     `--ink` is white in light because light-mode accents are deep; `--ink` is
     near-black in dark because dark-mode accents are neon-bright). Rule of
     thumb: text sitting on an `${accent}` background → `text-ink`.
   - Headings/body text on the page or on panels → `text-hi`.
3. **Alpha-suffixed accent template literals** (`${accent}55`, `${accent}22`)
   keep working ONLY when `accent` is a hex string. Components must therefore
   take accents from `useTokens()` (below), never hardcode neon hex.
4. **Theme-dependent inline colors in JS** (canvas, three.js, chart.js, string
   concat): use the hook —

   ```jsx
   import { useTokens } from '../theme/ThemeContext.jsx';
   const { theme, colors, accents } = useTokens();
   // colors.bg/.panel/.edge/.textHi/.textMid/.textLow/.neuro/.violet/.cardio/.amber/.blue (hex)
   // accents.mri|ecg|eeg|echo|patients|reports = { color, soft, label }
   ```

   Components re-render on theme switch, so chart/canvas colors follow.
5. **Box-shadows with neon glow** (`0 0 24px rgba(0,255,200,…)`): use
   `var(--glow-strong)` / `var(--glow-soft)` or `rgb(var(--rgb-neuro) / 0.25)`.
6. `glass`, `holo-panel`, `neon-text`, `neon-divider`, `hover-glow` CSS classes
   are already theme-aware — keep using them, do not re-style.
7. **Charts (react-chartjs-2):** grid lines `colors.edge`, ticks/labels
   `colors.textMid`, dataset colors from `accents`/`colors`. Build the chart
   `options`/`data` inside the component body (or `useMemo` keyed on `theme`).

## i18n system

- `LanguageProvider` (`src/i18n/LanguageContext.jsx`), persisted to
  `localStorage('mp-lang')`, default `en`, sets `<html lang>`.
- Dictionaries: one namespace file per domain in `src/i18n/locales/`
  (`common.js`, `nav.js`, `auth.js`, `dashboard.js`, `patients.js`, `mri.js`,
  `ecg.js`, `eeg.js`, `echo.js`, `reports.js`, `ui.js`), each exporting
  `{ en: {...}, fr: {...} }` with **identical key trees** in both languages.
  `locales/index.js` namespaces them: key `mri.upload.title` → `mri.js` →
  `en.upload.title`.
- Usage:

  ```jsx
  import { useI18n } from '../i18n/LanguageContext.jsx';
  const { t, lang, setLang } = useI18n();
  t('patients.list.title')
  t('common.deleteConfirm', { name: patient.full_name })   // {name} interpolation
  ```

### i18n conversion rules

1. Every user-visible hardcoded string moves to the namespace file of the
   module (UI primitives → `ui.js`; cross-cutting words like Save/Cancel/Delete/
   Loading → `common.js`, which already has them — check before adding).
2. **Do not translate:** brand "NEURACARD", "Constantine 2", proper nouns of
   models/datasets (U-Net, ViT, EchoNet, BIOT, PTB-XL), units, pathology
   abbreviations (AFIB, LBBB…), file extensions, `aria` ids. Medical pathology
   *names* DO get French (`Glioma` → `Gliome`, `No tumour` → `Sans tumeur`).
3. French must be professional clinical French (vouvoiement). Use proper
   accents (é, è, à, ç) and French punctuation spacing is NOT required (keep
   simple `:` `!` `?`).
4. Dynamic strings: `t(key, { var })` with `{var}` placeholders — never
   concatenate translated fragments.
5. Strings born outside components (Redux slices, services, API errors): leave
   as-is — they surface through toasts with server text; do not refactor slices.
6. Dates: leave `date-fns` formats untouched in this pass.

## Hard don'ts for sweep agents

- Don't touch files outside your assigned set (+ your own locale file).
- Don't run git commands. Don't run `npm run build` (the orchestrator does).
  You MAY lint your own files: `npx eslint src/path/File.jsx` from `frontend/`.
- Don't change component props/APIs, routing, Redux logic, or data fetching.
- Don't "fix" `bg-white`/`text-gray-*` utility classes — the CSS layer themes them.
- Class components stay class components (`ErrorBoundary`).
