import { Component } from 'react';

// Class component (documented exception) — hooks are unavailable, so it keeps
// a tiny built-in dictionary and reads the persisted language directly.
const STRINGS = {
  en: { title: 'Something went wrong', tryAgain: 'Try again' },
  fr: { title: 'Une erreur est survenue', tryAgain: 'Réessayer' },
};

function strings() {
  try {
    return STRINGS[localStorage.getItem('mp-lang')] || STRINGS.en;
  } catch {
    return STRINGS.en;
  }
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info);
  }
  render() {
    if (this.state.error) {
      const s = strings();
      return (
        <div className="min-h-screen flex items-center justify-center p-6">
          <div className="max-w-lg w-full bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h1 className="text-lg font-semibold text-danger mb-2">{s.title}</h1>
            <p className="text-sm text-gray-700 mb-4">{String(this.state.error.message || this.state.error)}</p>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 rounded-lg bg-primary text-ink text-sm hover:opacity-90"
            >
              {s.tryAgain}
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
