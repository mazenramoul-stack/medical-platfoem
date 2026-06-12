import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import App from './App.jsx';
import { store } from './store/store.js';
import { ThemeProvider } from './theme/ThemeContext.jsx';
import { LanguageProvider } from './i18n/LanguageContext.jsx';
import './index.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Provider store={store}>
      <ThemeProvider>
        <LanguageProvider>
          <BrowserRouter>
            <App />
            <Toaster
              position="top-right"
              toastOptions={{
                duration: 4000,
                style: {
                  background: 'var(--panel)',
                  color: 'var(--text-hi)',
                  border: '1px solid var(--edge)',
                },
              }}
            />
          </BrowserRouter>
        </LanguageProvider>
      </ThemeProvider>
    </Provider>
  </StrictMode>,
);
