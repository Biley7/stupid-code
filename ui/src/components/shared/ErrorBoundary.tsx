import { Component, Fragment, type ReactNode } from 'react';

export interface ErrorBoundaryProps {
  /** Region name used in the accessible name of the reset action, e.g. `Canvas`. */
  region: string;
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  resetKey: number;
}

/**
 * Catches render errors in a region. Shows a fixed message (never the error text)
 * and a reset action that remounts the children, which re-read the stores. No reload.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { hasError: false, resetKey: 0 };

  static getDerivedStateFromError(): Partial<ErrorBoundaryState> {
    return { hasError: true };
  }

  private reset = () => {
    this.setState((s) => ({ hasError: false, resetKey: s.resetKey + 1 }));
  };

  override render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="m-4 border border-crimson p-4 text-bone">
          <p className="mb-3">
            <span className="font-mono font-semibold text-signal">ERROR</span> This region failed to
            render.
          </p>
          <button
            type="button"
            onClick={this.reset}
            aria-label={`Reset ${this.props.region}`}
            className="border border-hairline px-3 py-1 text-sm hover:bg-obsidian"
          >
            Reset
          </button>
        </div>
      );
    }
    return <Fragment key={this.state.resetKey}>{this.props.children}</Fragment>;
  }
}
