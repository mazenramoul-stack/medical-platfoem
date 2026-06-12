import { Link } from 'react-router-dom';

import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const GENDERS = ['M', 'F', 'O'];

export default function PatientCard({ patient }) {
  const { t } = useI18n();
  const gender = GENDERS.includes(patient.gender) ? t(`patients.gender.${patient.gender}`) : patient.gender;
  return (
    <Link
      to={`/patients/${patient.id}`}
      className="block bg-card rounded-xl shadow-sm border border-gray-200 p-5 hover:border-primary transition"
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-gray-900">{patient.full_name}</h3>
        <span className="text-xs text-gray-500">#{patient.id}</span>
      </div>
      <div className="text-sm text-gray-600 space-y-1">
        <div>{t('patients.fields.age')}: <span className="text-gray-900 font-medium">{patient.age}</span></div>
        <div>{t('patients.fields.gender')}: <span className="text-gray-900 font-medium">{gender}</span></div>
        {patient.created_at && (
          <div className="text-xs text-gray-500">{t('patients.card.added', { time: formatRelative(patient.created_at) })}</div>
        )}
      </div>
    </Link>
  );
}
