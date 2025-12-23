/**
 * LoadingSpinner Component
 * Reusable loading indicator
 */

import React from 'react';
import { ProgressSpinner } from 'primereact/progressspinner';

interface LoadingSpinnerProps {
  /** Size in pixels */
  size?: number;
  /** Optional message to display below spinner */
  message?: string;
  /** Additional CSS classes */
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 50,
  message,
  className = '',
}) => (
  <div className={`flex flex-col items-center justify-center ${className}`}>
    <ProgressSpinner style={{ width: `${size}px`, height: `${size}px` }} />
    {message && (
      <p className="mt-4 text-slate-500">{message}</p>
    )}
  </div>
);

export default LoadingSpinner;
