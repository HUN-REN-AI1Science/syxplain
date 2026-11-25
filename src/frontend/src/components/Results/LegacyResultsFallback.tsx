/**
 * LegacyResultsFallback Component
 * Displays fallback UI for legacy markdown format results with download option
 */

import React from 'react';
import { Button } from 'primereact/button';

interface LegacyResultsFallbackProps {
  /** The markdown content to download */
  markdownContent: string;
  /** Optional custom filename (without extension) */
  filename?: string;
}

export const LegacyResultsFallback: React.FC<LegacyResultsFallbackProps> = ({
  markdownContent,
  filename = 'pysr_explanations',
}) => {
  const handleDownload = () => {
    const blob = new Blob([markdownContent], { type: 'text/markdown' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${filename}.md`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-surface-alt border border-[var(--color-border)] rounded-xl p-8 text-center">
      <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <i className="pi pi-history text-amber-600 text-2xl" />
      </div>
      <h3 className="font-heading text-xl font-bold text-primary mb-2">Legacy Run Format</h3>
      <p className="text-secondary max-w-md mx-auto mb-6">
        This analysis was generated using an older format that is no longer displayed in the
        application. You can download the original results as a Markdown file.
      </p>
      <Button
        label="Download Results (Markdown)"
        icon="pi pi-download"
        size="large"
        className="!bg-brand-500 hover:!bg-brand-600 !border-brand-500 !text-white font-semibold px-6 py-3 shadow-lg"
        onClick={handleDownload}
      />
    </div>
  );
};

export default LegacyResultsFallback;
