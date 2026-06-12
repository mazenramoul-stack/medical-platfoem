// One namespace file per domain; each exports { en: {...}, fr: {...} } with
// identical key trees. t('mri.upload.title') resolves to mri.js → <lang>.upload.title.

import auth from './auth.js';
import common from './common.js';
import dashboard from './dashboard.js';
import ecg from './ecg.js';
import echo from './echo.js';
import eeg from './eeg.js';
import mri from './mri.js';
import nav from './nav.js';
import patients from './patients.js';
import reports from './reports.js';
import ui from './ui.js';

const NAMESPACES = { auth, common, dashboard, ecg, echo, eeg, mri, nav, patients, reports, ui };

export function buildMessages(lang) {
  const out = {};
  for (const [ns, dict] of Object.entries(NAMESPACES)) {
    out[ns] = dict[lang] || dict.en || {};
  }
  return out;
}
