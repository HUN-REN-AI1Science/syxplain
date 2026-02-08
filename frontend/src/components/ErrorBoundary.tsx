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
    // Update state so next render shows fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log error to console for debugging
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
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            padding: '2rem',
            backgroundColor: '#f8f9fa',
          }}
        >
          <Card
            style={{
              maxWidth: '600px',
              width: '100%',
              textAlign: 'center',
            }}
          >
            <div style={{ marginBottom: '1.5rem' }}>
              <i
                className="pi pi-exclamation-triangle"
                style={{
                  fontSize: '4rem',
                  color: '#f59e0b',
                  marginBottom: '1rem',
                  display: 'block',
                }}
              />
              <h2 style={{ margin: '0 0 0.5rem 0', color: '#1f2937' }}>Something went wrong</h2>
              <p style={{ color: '#6b7280', margin: 0 }}>
                We're sorry, but something unexpected happened. Please try again or reload the page.
              </p>
            </div>

            <div
              style={{
                display: 'flex',
                gap: '1rem',
                justifyContent: 'center',
                marginBottom: isDevelopment ? '1.5rem' : 0,
              }}
            >
              <Button
                label="Try Again"
                icon="pi pi-refresh"
                onClick={this.handleReset}
                className="p-button-outlined"
              />
              <Button label="Reload Page" icon="pi pi-replay" onClick={this.handleReload} />
            </div>

            {/* Show stack trace in development mode */}
            {isDevelopment && this.state.error && (
              <div
                style={{
                  marginTop: '1rem',
                  padding: '1rem',
                  backgroundColor: '#fef2f2',
                  borderRadius: '0.5rem',
                  textAlign: 'left',
                  overflow: 'auto',
                }}
              >
                <h4 style={{ margin: '0 0 0.5rem 0', color: '#dc2626' }}>
                  Error Details (Development Only)
                </h4>
                <pre
                  style={{
                    margin: 0,
                    fontSize: '0.75rem',
                    color: '#991b1b',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
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
