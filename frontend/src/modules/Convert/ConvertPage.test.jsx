import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock the service so no real HTTP happens and we can assert the submit wiring.
vi.mock('../../services/conversionService.js', () => ({
  default: { convert: vi.fn() },
  downloadBlob: vi.fn(),
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import conversionService, { downloadBlob } from '../../services/conversionService.js';
import ConvertPage from './ConvertPage.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { ThemeProvider } from '../../theme/ThemeContext.jsx';

function renderPage() {
  return render(
    <ThemeProvider>
      <LanguageProvider>
        <ConvertPage />
      </LanguageProvider>
    </ThemeProvider>,
  );
}

describe('ConvertPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the four modality tabs', () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'MRI' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ECG' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Echo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'EEG' })).toBeInTheDocument();
  });

  it('sends the selected file to the conversion service and downloads the result', async () => {
    conversionService.convert.mockResolvedValue({
      blob: new Blob(['png-bytes']),
      filename: 'scan_converted.png',
    });
    const { container } = renderPage();

    const input = container.querySelector('input[type="file"]');
    const file = new File(['dummy'], 'scan.dcm', { type: 'application/dicom' });
    fireEvent.change(input, { target: { files: [file] } });

    fireEvent.click(screen.getByRole('button', { name: /Convert & download/i }));

    await waitFor(() => {
      expect(conversionService.convert).toHaveBeenCalledWith('mri', file, expect.any(Object));
    });
    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'scan_converted.png');
    });
  });

  it('does not call the service when no file is selected', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /Convert & download/i }));
    expect(conversionService.convert).not.toHaveBeenCalled();
  });
});
