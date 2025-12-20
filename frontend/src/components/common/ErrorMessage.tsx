/**
 * ErrorMessage Component
 * Standardized error display component
 */

import React from 'react';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';

interface ErrorMessageProps {
  /** Error message or title */
  message: string;
  /** Optional retry callback */
  onRetry?: () => void;
  /** Additional CSS classes */
  className?: string;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  message,
  onRetry,
  className = '',
}) => (
  <div className={`flex flex-col items-center ${className}`}>
    <Message severity="error" text={message} className="w-full" />
    {onRetry && (
      <Button
        label="Retry"
        icon="pi pi-refresh"
        className="p-button-outlined p-button-sm mt-3"
        onClick={onRetry}
      />
    )}
  </div>
);

export default ErrorMessage;
