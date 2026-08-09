import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-[#060911] text-white">
          <div className="max-w-md rounded-2xl border border-red-500/30 bg-red-950/20 p-8 text-center">
            <AlertTriangle className="mx-auto mb-4 h-10 w-10 text-red-400" />
            <h2 className="mb-2 text-lg font-bold text-red-300">Something went wrong</h2>
            <p className="mb-4 text-sm text-slate-400">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="rounded-xl bg-red-600/30 px-4 py-2 text-sm font-medium text-red-200 hover:bg-red-600/50 transition"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
