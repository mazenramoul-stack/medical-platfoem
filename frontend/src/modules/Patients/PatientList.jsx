import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { ChevronLeft, ChevronRight, Pencil, Plus, Search, Trash2, Users } from 'lucide-react';
import toast from 'react-hot-toast';

import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import Loader from '../../components/UI/Loader.jsx';
import { usePatients } from '../../hooks/usePatients.js';
import { useAuth } from '../../hooks/useAuth.js';
import { deletePatient } from '../../store/slices/patientsSlice.js';
import { formatDateShort } from '../../utils/formatters.js';
import { GENDERS } from '../../utils/constants.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const PAGE_SIZE = 10;

function initials(name) {
  return (name || '').split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase();
}

export default function PatientList() {
  const { patients, loading, error } = usePatients();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { t } = useI18n();
  const { user } = useAuth();
  // Only the technician (back-office) needs to see which doctor(s) a patient is
  // assigned to — a doctor's own list is, by definition, all assigned to them.
  const isTechnician = user?.role === 'technician';
  const [search, setSearch] = useState('');
  const [genderFilter, setGenderFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pendingDelete, setPendingDelete] = useState(null);

  const genderLabel = (g) => (['M', 'F', 'O'].includes(g) ? t(`patients.gender.${g}`) : g);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return patients.filter((p) => {
      if (s && !p.full_name.toLowerCase().includes(s)) return false;
      if (genderFilter && p.gender !== genderFilter) return false;
      return true;
    });
  }, [patients, search, genderFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const onDelete = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    setPendingDelete(null);
    try {
      await dispatch(deletePatient(id)).unwrap();
      toast.success(t('patients.list.deleted'));
    } catch (msg) {
      toast.error(String(msg || t('patients.deleteFailed')));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-col sm:flex-row gap-2 flex-1 min-w-0">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder={t('patients.list.searchPlaceholder')}
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <select
            value={genderFilter}
            onChange={(e) => { setGenderFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">{t('patients.list.allGenders')}</option>
            {GENDERS.map((g) => <option key={g.value} value={g.value}>{t(`patients.gender.${g.value}`)}</option>)}
          </select>
        </div>
        <Link
          to="/patients/new"
          className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
        >
          <Plus size={16} /> {t('patients.list.newPatient')}
        </Link>
      </div>

      {error && (
        <div className="text-sm text-danger bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {loading && <Loader label={t('patients.list.loading')} className="py-12" />}

      {!loading && filtered.length === 0 && (
        <EmptyState
          icon={Users}
          title={patients.length === 0 ? t('patients.list.emptyTitle') : t('patients.list.noMatchTitle')}
          description={patients.length === 0
            ? t('patients.list.emptyDescription')
            : t('patients.list.noMatchDescription')}
          action={patients.length === 0 ? (
            <Link to="/patients/new" className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm">
              <Plus size={16} /> {t('patients.list.newPatient')}
            </Link>
          ) : null}
        />
      )}

      {!loading && filtered.length > 0 && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left">{t('common.patient')}</th>
                  <th className="px-4 py-3 text-left">{t('patients.fields.age')}</th>
                  <th className="px-4 py-3 text-left">{t('patients.fields.gender')}</th>
                  {isTechnician && <th className="px-4 py-3 text-left">{t('patients.list.doctors')}</th>}
                  <th className="px-4 py-3 text-left">{t('patients.list.created')}</th>
                  <th className="px-4 py-3 text-right">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate(`/patients/${p.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-blue-100 text-primary flex items-center justify-center text-xs font-semibold">
                          {initials(p.full_name)}
                        </div>
                        <div>
                          <div className="font-medium text-gray-900">{p.full_name}</div>
                          <div className="text-xs text-gray-500">#{p.id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{p.age}</td>
                    <td className="px-4 py-3 text-gray-700">{genderLabel(p.gender)}</td>
                    {isTechnician && (
                      <td className="px-4 py-3">
                        {p.doctors && p.doctors.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {p.doctors.map((d) => (
                              <span
                                key={d.id}
                                className="inline-block px-2 py-0.5 rounded-full bg-blue-50 text-primary text-xs"
                              >
                                {d.full_name}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-400">{t('patients.list.noDoctors')}</span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-3 text-gray-700">{formatDateShort(p.created_at)}</td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Link
                          to={`/patients/${p.id}/edit`}
                          className="p-1.5 rounded text-gray-500 hover:text-primary hover:bg-blue-50"
                          aria-label={t('common.edit')}
                        >
                          <Pencil size={16} />
                        </Link>
                        <button
                          type="button"
                          onClick={() => setPendingDelete(p)}
                          className="p-1.5 rounded text-gray-500 hover:text-danger hover:bg-red-50"
                          aria-label={t('common.delete')}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm">
              <span className="text-gray-600">
                {t('common.page', { page: safePage, total: totalPages })} · {t('patients.list.count', { count: filtered.length })}
              </span>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label={t('common.previous')}
                  className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  type="button"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label={t('common.next')}
                  className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={onDelete}
        title={t('patients.list.deleteTitle')}
        description={t('patients.list.deleteDescription', { name: pendingDelete?.full_name ?? '' })}
        confirmLabel={t('common.delete')}
      />
    </div>
  );
}
