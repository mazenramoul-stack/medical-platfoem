import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';

import { fetchPatients } from '../store/slices/patientsSlice.js';

export function usePatients({ autoLoad = true } = {}) {
  const dispatch = useDispatch();
  const { items, loading, error, selected } = useSelector((s) => s.patients);
  useEffect(() => {
    // Always refetch on mount so the list reflects the CURRENT user (and picks
    // up any new assignments) without a page reload. The cached `items` stay
    // visible while loading — fetchPatients.pending doesn't clear them — so
    // there's no flash to empty.
    if (autoLoad) {
      dispatch(fetchPatients());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad]);
  return { patients: items, loading, error, selected, refresh: () => dispatch(fetchPatients()) };
}

export default usePatients;
