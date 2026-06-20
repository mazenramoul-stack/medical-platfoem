import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock the service so no real HTTP happens; assert the explain wiring.
vi.mock('../../services/eegService.js', () => ({
  default: { explain: vi.fn() },
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import eegService from '../../services/eegService.js';
import EEGExplain from './EEGExplain.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { ThemeProvider } from '../../theme/ThemeContext.jsx';

const PER_CHANNEL = {
  'FP1-F7': 1, 'F7-T7': 0.8, 'T7-P7': 0.6, 'P7-O1': 0.4,
  'FP2-F8': 0.3, 'F8-T8': 0.3, 'T8-P8': 0.2, 'P8-O2': 0.2,
  'FP1-F3': 0.5, 'F3-C3': 0.4, 'C3-P3': 0.3, 'P3-O1': 0.2,
  'FP2-F4': 0.2, 'F4-C4': 0.2, 'C4-P4': 0.1, 'P4-O2': 0.1,
};

function renderPanel(props = {}) {
  return render(
    <ThemeProvider>
      <LanguageProvider>
        <EEGExplain id={9} {...props} />
      </LanguageProvider>
    </ThemeProvider>,
  );
}

describe('EEGExplain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Explain (SHAP) button', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: /Explain \(SHAP\)/i })).toBeInTheDocument();
  });

  it('calls eegService.explain and shows the returned SHAP image + top channels', async () => {
    eegService.explain.mockResolvedValue({
      status: 'success',
      shap_path: 'http://x/media/eeg/explanations/s_SZ.png?exp=1&sig=abc',
      predicted_class: 'SZ',
      target_class: 'SZ',
      probability: 0.74,
      class_probabilities: { SZ: 0.74, LPD: 0.1, GPD: 0.06, LRDA: 0.04, GRDA: 0.03, Other: 0.03 },
      per_channel_importance: PER_CHANNEL,
      top_channels: ['FP1-F7', 'F7-T7', 'FP1-F3'],
      segment_index: 0,
    });

    const onResult = vi.fn();
    renderPanel({ onResult });
    fireEvent.click(screen.getByRole('button', { name: /Explain \(SHAP\)/i }));

    await waitFor(() => {
      expect(eegService.explain).toHaveBeenCalledWith(9, undefined);
    });
    const img = await screen.findByAltText(/EEG SHAP saliency/i);
    expect(img).toHaveAttribute('src', expect.stringContaining('s_SZ.png'));
    expect(onResult).toHaveBeenCalled();
  });
});
