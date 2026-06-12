import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';

import { fetchPatients } from '../store/slices/patientsSlice.js';

export function usePatients({ autoLoad = true } = {}) {
  const dispatch = useDispatch();
  const { items, loading, error, selected } = useSelector((s) => s.patients);
  useEffect(() => {
    if (autoLoad && items.length === 0 && !loading) {
      dispatch(fetchPatients());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad]);
  return { patients: items, loading, error, selected, refresh: () => dispatch(fetchPatients()) };
}

export default usePatients;
