import { useDispatch, useSelector } from 'react-redux';

import { logout as logoutAction } from '../store/slices/authSlice.js';

export function useAuth() {
  const dispatch = useDispatch();
  const auth = useSelector((s) => s.auth);
  return {
    user: auth.user,
    token: auth.token,
    isAuthenticated: auth.isAuthenticated,
    loading: auth.loading,
    error: auth.error,
    logout: () => dispatch(logoutAction()),
  };
}

export default useAuth;
