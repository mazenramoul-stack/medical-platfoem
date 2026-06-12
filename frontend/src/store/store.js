import { configureStore } from '@reduxjs/toolkit';

import authReducer from './slices/authSlice.js';
import notificationsReducer from './slices/notificationsSlice.js';
import patientsReducer from './slices/patientsSlice.js';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    patients: patientsReducer,
    notifications: notificationsReducer,
  },
});
