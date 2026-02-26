/**
 * UploadProgressOverlay Component
 * Displays upload/processing progress overlay
 */

import React from 'react';
import { ProgressBar } from 'primereact/progressbar';

interface UploadProgressOverlayProps {
  uploading: boolean;
  processing: boolean;
}

export const UploadProgressOverlay: React.FC<UploadProgressOverlayProps> = ({
  uploading,
  processing,
}) => {
  if (!uploading && !processing) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center z-20">
      <div className="bg-surface/90 backdrop-blur-md p-8 rounded-2xl shadow-xl w-full max-w-md flex flex-col items-center animate-fade-in-up border border-[var(--color-border)]">
        <div className="w-full mb-4">
          <ProgressBar
            mode="indeterminate"
            style={{ height: '8px' }}
            className="w-full"
          />
        </div>
        <div className="flex items-center space-x-3">
          {processing ? (
            <i className="pi pi-cog pi-spin text-brand-500 text-xl" />
          ) : (
            <i className="pi pi-upload text-brand-500 text-xl" />
          )}
          <span className="text-primary font-semibold text-lg">
            {processing ? 'Processing file...' : 'Uploading...'}
          </span>
        </div>
        <p className="text-secondary text-sm mt-2">
          {processing ? 'Analyzing columns and structure' : 'Please wait while we upload your data'}
        </p>
      </div>
    </div>
  );
};

export default UploadProgressOverlay;
