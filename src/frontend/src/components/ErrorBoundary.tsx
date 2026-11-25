import { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary component that catches JavaScript errors in child components.
 *
 * Prevents the entire app from crashing when a component throws an error,
 * displaying a user-friendly error message instead.
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      const isDevelopment = import.meta.env.DEV;

      return (
        <div className="flex justify-center items-center min-h-screen p-8 bg-page">
          <Card className="max-w-[600px] w-full text-center">
            <div className="mb-6">
              <i className="pi pi-exclamation-triangle text-6xl text-accent-500 block mb-4" />
              <h2 className="font-heading text-xl font-bold text-primary mb-2">
                Something went wrong
              </h2>
              <p className="text-secondary">
                We're sorry, but something unexpected happened. Please try again or reload the page.
              </p>
            </div>

            <div className={`flex gap-4 justify-center ${isDevelopment ? 'mb-6' : ''}`}>
              <Button
                label="Try Again"
                icon="pi pi-refresh"
                onClick={this.handleReset}
                className="p-button-outlined"
              />
              <Button label="Reload Page" icon="pi pi-replay" onClick={this.handleReload} />
            </div>

            {isDevelopment && this.state.error && (
              <div className="mt-4 p-4 bg-red-50 rounded-lg text-left overflow-auto">
                <h4 className="font-heading font-semibold text-semantic-error mb-2">
                  Error Details (Development Only)
                </h4>
                <pre className="m-0 text-xs text-red-800 whitespace-pre-wrap break-words font-mono">
                  {this.state.error.toString()}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </div>
            )}
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
