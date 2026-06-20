import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock the service so no real HTTP happens; assert the explain wiring.
vi.mock('../../services/echoService.js', () => ({
  default: { explain: vi.fn() },
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import echoService from '../../services/echoService.js';
import EchoExplain from './EchoExplain.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { ThemeProvider } from '../../theme/ThemeContext.jsx';

function renderPanel(props = {}) {
  return render(
    <ThemeProvider>
      <LanguageProvider>
        <EchoExplain id={8} {...props} />
      </LanguageProvider>
    </ThemeProvider>,
  );
}

describe('EchoExplain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Explain (SHAP) button', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: /Explain \(SHAP\)/i })).toBeInTheDocument();
  });

  it('calls echoService.explain and shows the returned SHAP image + frame importance', async () => {
    echoService.explain.mockResolvedValue({
      status: 'success',
      shap_path: 'http://x/media/echo/explanations/s_ef.png?exp=1&sig=abc',
      ef: 54.9,
      target: 'ef',
      frame_importance: [0.1, 0.9, 0.5, 0.3],
      top_frames: [
        { clip_index: 1, video_frame: 2, importance: 0.9 },
        { clip_index: 2, video_frame: 4, importance: 0.5 },
        { clip_index: 3, video_frame: 6, importance: 0.3 },
      ],
      n_frames: 4,
    });

    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /Explain \(SHAP\)/i }));

    await waitFor(() => {
      expect(echoService.explain).toHaveBeenCalledWith(8);
    });
    const img = await screen.findByAltText(/Echo SHAP saliency/i);
    expect(img).toHaveAttribute('src', expect.stringContaining('s_ef.png'));
  });
});
