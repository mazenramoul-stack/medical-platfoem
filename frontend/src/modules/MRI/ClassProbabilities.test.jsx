import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import ClassProbabilities from './ClassProbabilities.jsx';

function renderCP(probabilities) {
  return render(
    <LanguageProvider>
      <ClassProbabilities probabilities={probabilities} />
    </LanguageProvider>,
  );
}

// Body rows only (drop the <thead> row).
function dataRows() {
  return screen.getAllByRole('row').slice(1);
}

describe('ClassProbabilities', () => {
  it('renders nothing when probabilities are absent', () => {
    const { container } = renderCP(null);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows all 4 classes with localized names, sorted high→low', () => {
    renderCP({ glioma: 0.05, meningioma: 0.15, pituitary: 0.78, notumor: 0.02 });

    expect(screen.getByText('Glioma')).toBeInTheDocument();
    expect(screen.getByText('Meningioma')).toBeInTheDocument();
    expect(screen.getByText('Pituitary')).toBeInTheDocument();
    expect(screen.getByText('No tumour')).toBeInTheDocument();

    const rows = dataRows();
    expect(within(rows[0]).getByText('Pituitary')).toBeInTheDocument();
    expect(within(rows[0]).getByText('78.0%')).toBeInTheDocument();
    expect(within(rows[3]).getByText('No tumour')).toBeInTheDocument();
    expect(within(rows[3]).getByText('2.0%')).toBeInTheDocument();
  });

  it('marks only the argmax class as predicted', () => {
    renderCP({ glioma: 0.7, meningioma: 0.1, pituitary: 0.1, notumor: 0.1 });

    const rows = dataRows();
    expect(within(rows[0]).getByText('Glioma')).toBeInTheDocument();
    expect(within(rows[0]).getByText('✓')).toBeInTheDocument();
    // every other row shows the em-dash placeholder, not a check
    expect(within(rows[1]).getByText('—')).toBeInTheDocument();
    expect(within(rows[2]).getByText('—')).toBeInTheDocument();
    expect(within(rows[3]).getByText('—')).toBeInTheDocument();
  });

  it('normalizes HuggingFace _tumor-suffixed labels', () => {
    renderCP({ glioma_tumor: 0.6, meningioma_tumor: 0.4 });
    expect(screen.getByText('Glioma')).toBeInTheDocument();
    expect(screen.getByText('Meningioma')).toBeInTheDocument();
  });
});
