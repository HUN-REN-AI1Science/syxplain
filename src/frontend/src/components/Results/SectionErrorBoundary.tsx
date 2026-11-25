/**
 * SectionErrorBoundary Component
 * Contains a rendering crash to one section of the results page, so a malformed part of a
 * stored run (e.g. an unexpected shape in the discovery report) never blanks the equations.
 */

import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Shown in the fallback, e.g. "The discovery report" */
  name?: string;
}

interface State {
  error: Error | null;
}

class SectionErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(`${this.props.name ?? 'Section'} failed to render:`, error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="bg-[rgba(245,158,11,0.06)] border border-[rgba(245,158,11,0.2)] rounded-xl p-4 text-sm text-secondary"
        >
          <i className="pi pi-exclamation-triangle text-amber-500 mr-2" aria-hidden="true"></i>
          {this.props.name ?? 'This section'} could not be displayed. The rest of the results are
          unaffected.
        </div>
      );
    }
    return this.props.children;
  }
}

export default SectionErrorBoundary;
