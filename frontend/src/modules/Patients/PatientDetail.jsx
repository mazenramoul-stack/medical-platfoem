import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Activity, ArrowLeft, Brain, FileText, Heart, HeartPulse, Pencil, Plus } from 'lucide-react';
import toast from 'react-hot-toast';

import Modal from '../../components/UI/Modal.jsx';
import patientService from '../../services/patientService.js';
import ecgService from '../../services/ecgService.js';
import echoService from '../../services/echoService.js';
import eegService from '../../services/eegService.js';
import mriService from '../../services/mriService.js';
import reportService from '../../services/reportService.js';
import { formatDate } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

import MRIUpload from '../MRI/MRIUpload.jsx';
import MRIHistory from '../MRI/MRIHistory.jsx';
import ECGUpload from '../ECG/ECGUpload.jsx';
import ECGHistory from '../ECG/ECGHistory.jsx';
import EchoUpload from '../Echo/EchoUpload.jsx';
import EchoHistory from '../Echo/EchoHistory.jsx';
import EEGUpload from '../EEG/EEGUpload.jsx';
import EEGHistory from '../EEG/EEGHistory.jsx';
import ReportList from '../Reports/ReportList.jsx';
import ReportGenerator from '../Reports/ReportGenerator.jsx';

const GENDERS = ['M', 'F', 'O'];
const TABS = [
  { id: 'mri',     icon: Brain },
  { id: 'ecg',     icon: Heart },
  { id: 'echo',    icon: HeartPulse },
  { id: 'eeg',     icon: Activity },
  { id: 'reports', icon: FileText },
];

const TAB_COUNT = (tid, lists) => ({
  mri: lists.mri.length, ecg: lists.ecg.length, echo: lists.echo.length, eeg: lists.eeg.length, reports: lists.reports.length,
}[tid] ?? 0);

export default function PatientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [patient, setPatient] = useState(null);
  const [mriList, setMriList] = useState([]);
  const [ecgList, setEcgList] = useState([]);
  const [echoList, setEchoList] = useState([]);
  const [eegList, setEegList] = useState([]);
  const [reportsList, setReportsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('mri');
  const [modal, setModal] = useState(null); // 'mri' | 'ecg' | 'echo' | 'eeg' | 'report' | null

  const refresh = useCallback(async () => {
    try {
      const [p, m, e, ec, eg, r] = await Promise.all([
        patientService.getById(id),
        mriService.getByPatient(id),
        ecgService.getByPatient(id),
        echoService.getByPatient(id),
        eegService.getByPatient(id),
        reportService.getByPatient(id),
      ]);
      setPatient(p); setMriList(m); setEcgList(e); setEchoList(ec); setEegList(eg); setReportsList(r);
    } catch (err) {
      toast.error(err.response?.data?.detail || t('patients.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  const deleteHandler = (service, deletedKey) => async (itemId) => {
    try {
      await service.delete(itemId);
      toast.success(t(`patients.detail.deleted.${deletedKey}`));
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('patients.deleteFailed'));
    }
  };
  const onMriDelete = deleteHandler(mriService, 'mri');
  const onEcgDelete = deleteHandler(ecgService, 'ecg');
  const onEchoDelete = deleteHandler(echoService, 'echo');
  const onEegDelete = deleteHandler(eegService, 'eeg');
  const onReportDelete = deleteHandler(reportService, 'report');

  if (loading) return <div className="py-12 text-center text-sm text-gray-500">{t('patients.loadingPatient')}</div>;
  if (!patient) return <div className="py-12 text-center text-sm text-gray-500">{t('patients.detail.notFound')}</div>;

  const gender = GENDERS.includes(patient.gender) ? t(`patients.gender.${patient.gender}`) : patient.gender;

  return (
    <div className="space-y-6">
      <div>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 mb-3"
        >
          <ArrowLeft size={16} /> {t('common.back')}
        </button>

        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-gray-900">{patient.full_name}</h1>
              <p className="text-sm text-gray-500">{t('patients.detail.patientNumber', { id: patient.id })}</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 mt-4 text-sm">
                <div><div className="text-xs text-gray-500">{t('patients.fields.age')}</div><div className="text-gray-900 font-medium">{patient.age}</div></div>
                <div><div className="text-xs text-gray-500">{t('patients.fields.gender')}</div><div className="text-gray-900 font-medium">{gender}</div></div>
                <div><div className="text-xs text-gray-500">{t('patients.detail.doctors')}</div><div className="text-gray-900 font-medium">{patient.doctors && patient.doctors.length > 0 ? patient.doctors.map((d) => d.full_name).join(', ') : t('patients.detail.noDoctors')}</div></div>
                <div><div className="text-xs text-gray-500">{t('patients.detail.added')}</div><div className="text-gray-900 font-medium">{formatDate(patient.created_at)}</div></div>
              </div>
              {patient.medical_history && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <div className="text-xs text-gray-500 mb-1">{t('patients.fields.medicalHistory')}</div>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{patient.medical_history}</p>
                </div>
              )}
            </div>
            <Link
              to={`/patients/${id}/edit`}
              className="inline-flex items-center gap-2 text-sm text-gray-700 border border-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-50"
            >
              <Pencil size={14} /> {t('common.edit')}
            </Link>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setModal('mri')}
          className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
        >
          <Plus size={16} /> {t('patients.detail.newMri')}
        </button>
        <button
          type="button"
          onClick={() => setModal('ecg')}
          className="inline-flex items-center gap-2 bg-danger text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
        >
          <Plus size={16} /> {t('patients.detail.newEcg')}
        </button>
        <button
          type="button"
          onClick={() => setModal('echo')}
          className="inline-flex items-center gap-2 bg-warning text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
        >
          <Plus size={16} /> {t('patients.detail.newEcho')}
        </button>
        <button
          type="button"
          onClick={() => setModal('eeg')}
          className="inline-flex items-center gap-2 text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
          style={{ background: 'var(--violet)' }}
        >
          <Plus size={16} /> {t('patients.detail.newEeg')}
        </button>
        <button
          type="button"
          onClick={() => setModal('report')}
          className="inline-flex items-center gap-2 bg-success text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
        >
          <Plus size={16} /> {t('patients.detail.generateReport')}
        </button>
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="flex border-b border-gray-200 overflow-x-auto">
          {TABS.map(({ id: tid, icon: Icon }) => (
            <button
              key={tid}
              type="button"
              onClick={() => setTab(tid)}
              className={
                'inline-flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition '
                + (tab === tid ? 'border-primary text-primary' : 'border-transparent text-gray-600 hover:text-gray-900')
              }
            >
              <Icon size={16} />
              {t(`patients.detail.tabs.${tid}`)}
              <span className={'inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full text-[10px] font-semibold ' + (tab === tid ? 'bg-primary text-ink' : 'bg-gray-200 text-gray-700')}>
                {TAB_COUNT(tid, { mri: mriList, ecg: ecgList, echo: echoList, eeg: eegList, reports: reportsList })}
              </span>
            </button>
          ))}
        </div>
        <div className="p-5">
          {tab === 'mri'     && <MRIHistory items={mriList} onDelete={onMriDelete} />}
          {tab === 'ecg'     && <ECGHistory items={ecgList} onDelete={onEcgDelete} />}
          {tab === 'echo'    && <EchoHistory items={echoList} onDelete={onEchoDelete} />}
          {tab === 'eeg'     && <EEGHistory items={eegList} onDelete={onEegDelete} />}
          {tab === 'reports' && <ReportList items={reportsList} onDelete={onReportDelete} />}
        </div>
      </div>

      <Modal
        open={modal === 'mri'}
        onClose={() => setModal(null)}
        title={t('patients.detail.uploadMriTitle')}
      >
        <MRIUpload
          patient={patient}
          onComplete={() => { setModal(null); refresh(); }}
        />
      </Modal>
      <Modal
        open={modal === 'ecg'}
        onClose={() => setModal(null)}
        title={t('patients.detail.uploadEcgTitle')}
      >
        <ECGUpload
          patient={patient}
          onComplete={() => { setModal(null); refresh(); }}
        />
      </Modal>
      <Modal
        open={modal === 'echo'}
        onClose={() => setModal(null)}
        title={t('patients.detail.uploadEchoTitle')}
      >
        <EchoUpload
          patient={patient}
          onComplete={() => { setModal(null); refresh(); }}
        />
      </Modal>
      <Modal
        open={modal === 'eeg'}
        onClose={() => setModal(null)}
        title={t('patients.detail.uploadEegTitle')}
      >
        <EEGUpload
          patient={patient}
          onComplete={() => { setModal(null); refresh(); }}
        />
      </Modal>
      <Modal
        open={modal === 'report'}
        onClose={() => setModal(null)}
        title={t('patients.detail.generateReportTitle')}
      >
        <ReportGenerator
          patient={patient}
          mriOptions={mriList.filter((m) => m.status === 'completed')}
          ecgOptions={ecgList.filter((e) => e.status === 'completed')}
          echoOptions={echoList.filter((e) => e.status === 'completed')}
          eegOptions={eegList.filter((e) => e.status === 'completed')}
          onComplete={() => { setModal(null); refresh(); }}
        />
      </Modal>
    </div>
  );
}
