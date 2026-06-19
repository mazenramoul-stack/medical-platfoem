import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import EFGauge from './EFGauge.jsx';

function renderGauge(props) {
  return render(
    <LanguageProvider>
      <EFGauge {...props} />
    </LanguageProvider>,
  );
}

describe('EFGauge', () => {
  it('renders the three clinical bands and boundary ticks', () => {
    renderGauge({ ef: 58.2, category: 'Normal', color: '#00ffcc' });
    expect(screen.getByText('Reduced')).toBeInTheDocument();
    expect(screen.getByText('Mildly reduced')).toBeInTheDocument();
    expect(screen.getByText('Normal')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('shows a marker label at the EF value', () => {
    renderGauge({ ef: 58.2, category: 'Normal', color: '#00ffcc' });
    expect(screen.getByText('58.2%')).toBeInTheDocument();
  });

  it('omits the marker label when EF is missing', () => {
    renderGauge({ ef: null, category: null, color: '#888888' });
    expect(screen.queryByText(/\d%/)).toBeNull();
  });
});
