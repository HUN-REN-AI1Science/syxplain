/**
 * LegacyAnalysisModeCard Component
 * Shows the quick/deep mode of runs made before the single analysis mode; renders
 * nothing for current runs.
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import { analysisTypeDisplay, legacyAnalysisTypeLabel } from '@utils/formatting';

interface LegacyAnalysisModeCardProps {
  analysisType?: string | null;
}

export const LegacyAnalysisModeCard: React.FC<LegacyAnalysisModeCardProps> = ({ analysisType }) => {
  if (!legacyAnalysisTypeLabel(analysisType)) return null;
  const { label, icon, severity } = analysisTypeDisplay(analysisType);
  return (
    <div className="rounded-xl p-4 border bg-surface-alt border-[var(--color-border)]">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <i className={`pi ${icon} text-muted text-lg mr-3 flex-shrink-0`}></i>
          <div>
            <h4 className="font-bold text-primary">Analysis Mode</h4>
            <p className="text-sm text-secondary">Legacy analysis mode of this run</p>
          </div>
        </div>
        <Tag value={`${label} Analysis`} severity={severity} className="text-base px-3 py-1" />
      </div>
    </div>
  );
};
