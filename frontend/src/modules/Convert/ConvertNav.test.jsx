import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';

import authReducer from '../../store/slices/authSlice.js';
import patientsReducer from '../../store/slices/patientsSlice.js';
import Sidebar from '../../components/Layout/Sidebar.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { ThemeProvider } from '../../theme/ThemeContext.jsx';

function renderSidebar(role) {
  const store = configureStore({
    reducer: { auth: authReducer, patients: patientsReducer },
    preloadedState: {
      auth: {
        user: { full_name: 'T User', email: 't@x.com', role },
        token: 'tok',
        isAuthenticated: true,
        loading: false,
        error: null,
      },
    },
  });
  return render(
    <Provider store={store}>
      <MemoryRouter>
        <ThemeProvider>
          <LanguageProvider>
            <Sidebar />
          </LanguageProvider>
        </ThemeProvider>
      </MemoryRouter>
    </Provider>,
  );
}

describe('Convert data nav gating', () => {
  it('shows the Convert data link for a technician', () => {
    renderSidebar('technician');
    expect(screen.getByText('Convert data')).toBeInTheDocument();
  });

  it('hides the Convert data link for a doctor', () => {
    renderSidebar('doctor');
    expect(screen.queryByText('Convert data')).toBeNull();
  });
});
