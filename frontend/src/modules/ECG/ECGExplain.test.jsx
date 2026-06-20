import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock the service so no real HTTP happens; assert the explain wiring.
vi.mock('../../services/ecgService.js', () => ({
  default: { explain: vi.fn() },
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import ecgService from '../../services/ecgService.js';
import ECGExplain from './ECGExplain.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { ThemeProvider } from '../../theme/ThemeContext.jsx';

function renderPanel(props = {}) {
  return render(
    <ThemeProvider>
      <LanguageProvider>
        <ECGExplain id={7} {...props} />
      </LanguageProvider>
    </ThemeProvider>,
  );
}

describe('ECGExplain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Explain (SHAP) button', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: /Explain \(SHAP\)/i })).toBeInTheDocument();
  });

  it('calls ecgService.explain and shows the returned SHAP image + per-lead importance', async () => {
    ecgService.explain.mockResolvedValue({
      status: 'success',
      shap_path: 'http://x/media/ecg/explanations/s_AFIB.png?exp=1&sig=abc',
      pathology: 'AFIB',
      probability: 0.91,
      per_lead_importance: {
        I: 1, II: 0.5, III: 0.2, aVR: 0.1, aVL: 0.1, aVF: 0.1,
        V1: 0.3, V2: 0.2, V3: 0.2, V4: 0.1, V5: 0.1, V6: 0.1,
      },
      top_leads: ['I', 'II', 'V1'],
    });

    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /Explain \(SHAP\)/i }));

    await waitFor(() => {
      expect(ecgService.explain).toHaveBeenCalledWith(7, undefined);
    });
    const img = await screen.findByAltText(/ECG SHAP saliency/i);
    expect(img).toHaveAttribute('src', expect.stringContaining('s_AFIB.png'));
  });
});
