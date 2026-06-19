import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { ArrowLeft, Loader2, Save } from 'lucide-react';
import toast from 'react-hot-toast';

import patientService from '../../services/patientService.js';
import doctorService from '../../services/doctorService.js';
import { createPatient, updatePatient } from '../../store/slices/patientsSlice.js';
import { useAuth } from '../../hooks/useAuth.js';
import { GENDERS } from '../../utils/constants.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const EMPTY = { full_name: '', age: '', gender: 'M', medical_history: '' };

export default function PatientForm() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { t } = useI18n();
  const { user } = useAuth();
  // Only a technician chooses which doctor(s) a patient is assigned to (the
  // backend IsTechnician/serializer is the real gate; this is the matching UI).
  const isTechnician = user?.role === 'technician';

  const [form, setForm] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [doctors, setDoctors] = useState([]);
  const [doctorIds, setDoctorIds] = useState([]);
  const [loadingDoctors, setLoadingDoctors] = useState(false);

  useEffect(() => {
    if (!isEdit) return;
    let alive = true;
    setLoading(true);
    patientService.getById(id)
      .then((p) => { if (alive) {
        setForm({
          full_name: p.full_name,
          age: String(p.age),
          gender: p.gender,
          medical_history: p.medical_history || '',
        });
        setDoctorIds((p.doctors || []).map((d) => d.id));
      } })
      .catch((e) => toast.error(e.response?.data?.detail || t('patients.loadFailed')))
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id, isEdit, t]);

  useEffect(() => {
    if (!isTechnician) return undefined;
    let alive = true;
    setLoadingDoctors(true);
    doctorService.getAll()
      .then((list) => { if (alive) setDoctors(list); })
      .catch(() => { /* a doctor would 403 here; the section just stays empty */ })
      .finally(() => { if (alive) setLoadingDoctors(false); });
    return () => { alive = false; };
  }, [isTechnician]);

  const toggleDoctor = (docId) =>
    setDoctorIds((ids) => (ids.includes(docId) ? ids.filter((x) => x !== docId) : [...ids, docId]));

  const onChange = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const validate = () => {
    const e = {};
    if (!form.full_name.trim()) e.full_name = t('patients.form.errors.fullName');
    const age = Number(form.age);
    if (!form.age || Number.isNaN(age) || age < 0 || age > 150) e.age = t('patients.form.errors.age');
    if (!['M', 'F', 'O'].includes(form.gender)) e.gender = t('patients.form.errors.gender');
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const onSubmit = async (ev) => {
    ev.preventDefault();
    if (!validate()) return;
    const payload = {
      full_name: form.full_name.trim(),
      age: Number(form.age),
      gender: form.gender,
      medical_history: form.medical_history,
    };
    // Doctor assignment is technician-only; a doctor's patient is auto-assigned
    // to them server-side, so we never send doctor_ids for a doctor.
    if (isTechnician) payload.doctor_ids = doctorIds;
    setSaving(true);
    try {
      if (isEdit) {
        await dispatch(updatePatient({ id: Number(id), data: payload })).unwrap();
        toast.success(t('patients.form.updated'));
        navigate(`/patients/${id}`);
      } else {
        const created = await dispatch(createPatient(payload)).unwrap();
        toast.success(t('patients.form.created'));
        navigate(`/patients/${created.id}`);
      }
    } catch (msg) {
      toast.error(String(msg || t('patients.form.saveFailed')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 mb-3"
      >
        <ArrowLeft size={16} /> {t('common.back')}
      </button>

      <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
        <h1 className="text-xl font-semibold text-gray-900 mb-1">
          {isEdit ? t('patients.form.editTitle') : t('patients.form.newTitle')}
        </h1>
        <p className="text-sm text-gray-600 mb-6">
          {isEdit ? t('patients.form.editSubtitle') : t('patients.form.newSubtitle')}
        </p>

        {loading ? (
          <div className="py-10 text-center text-sm text-gray-500">{t('patients.loadingPatient')}</div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label htmlFor="patient-full-name" className="block text-sm font-medium text-gray-700 mb-1">{t('patients.fields.fullName')}</label>
              <input
                id="patient-full-name"
                type="text" value={form.full_name} onChange={onChange('full_name')}
                className={
                  'w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary '
                  + (errors.full_name ? 'border-danger' : 'border-gray-300')
                }
                placeholder={t('patients.form.namePlaceholder')}
              />
              {errors.full_name && <p className="text-xs text-danger mt-1">{errors.full_name}</p>}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="patient-age" className="block text-sm font-medium text-gray-700 mb-1">{t('patients.fields.age')}</label>
                <input
                  id="patient-age"
                  type="number" min={0} max={150} value={form.age} onChange={onChange('age')}
                  className={
                    'w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary '
                    + (errors.age ? 'border-danger' : 'border-gray-300')
                  }
                />
                {errors.age && <p className="text-xs text-danger mt-1">{errors.age}</p>}
              </div>
              <div>
                <label htmlFor="patient-gender" className="block text-sm font-medium text-gray-700 mb-1">{t('patients.fields.gender')}</label>
                <select
                  id="patient-gender"
                  value={form.gender} onChange={onChange('gender')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {GENDERS.map((g) => <option key={g.value} value={g.value}>{t(`patients.gender.${g.value}`)}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="patient-history" className="block text-sm font-medium text-gray-700 mb-1">{t('patients.fields.medicalHistory')}</label>
              <textarea
                id="patient-history"
                rows={5} value={form.medical_history} onChange={onChange('medical_history')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder={t('patients.form.historyPlaceholder')}
              />
            </div>

            {isTechnician && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('patients.form.assignDoctors')}
                </label>
                <p className="text-xs text-gray-500 mb-2">{t('patients.form.assignDoctorsHint')}</p>
                {loadingDoctors ? (
                  <div className="text-sm text-gray-500">{t('patients.form.loadingDoctors')}</div>
                ) : doctors.length === 0 ? (
                  <div className="text-sm text-gray-500">{t('patients.form.noDoctorsAvailable')}</div>
                ) : (
                  <div className="max-h-44 overflow-y-auto border border-gray-300 rounded-lg divide-y divide-gray-100">
                    {doctors.map((d) => (
                      <label
                        key={d.id}
                        className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-gray-50"
                      >
                        <input
                          type="checkbox"
                          checked={doctorIds.includes(d.id)}
                          onChange={() => toggleDoctor(d.id)}
                        />
                        <span className="text-gray-900">{d.full_name}</span>
                        {d.email && <span className="text-xs text-gray-500">{d.email}</span>}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="px-4 py-2 rounded-lg text-sm text-gray-700 hover:bg-gray-100"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                {saving ? t('patients.form.saving') : (isEdit ? t('patients.form.saveChanges') : t('patients.form.createPatient'))}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
