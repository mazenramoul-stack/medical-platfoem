import { useCallback, useState } from 'react';

/** Minimal hook for one-off API calls with loading/error state. */
export function useApi(apiCall) {
  const [state, setState] = useState({ loading: false, error: null, data: null });
  const run = useCallback(async (...args) => {
    setState({ loading: true, error: null, data: null });
    try {
      const data = await apiCall(...args);
      setState({ loading: false, error: null, data });
      return data;
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Request failed';
      setState({ loading: false, error: message, data: null });
      throw err;
    }
  }, [apiCall]);
  return { ...state, run };
}

export default useApi;
