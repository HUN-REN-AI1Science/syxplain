/**
 * Results components barrel export
 * Components specific to the results pages (ResultsView, PublicResultsView)
 */

// Loading & Progress
export { LoadingSpinner } from './LoadingSpinner';
export { AnalysisProgressView } from './AnalysisProgressView';

// Headers
export { ResultsHeader } from './ResultsHeader';
export type { ResultsStatus } from './ResultsHeader';
export { default as PublicHeader } from './PublicHeader';

// Result Display
export { ResultContent } from './ResultContent';
export {
  extractDiscovery,
  extractEquationResults,
  extractWarnings,
  hasDiscoveryData,
  hasExplanationError,
  isResultIncomplete,
} from './resultUtils';
export { ResultWarnings } from './ResultWarnings';
export { default as SectionErrorBoundary } from './SectionErrorBoundary';
export { LegacyResultsFallback } from './LegacyResultsFallback';

// Equation Results
export { default as EquationResultsView } from './EquationResults/EquationResultsView';

// Discovery agent
export { default as DiscoveryReportPanel } from './Discovery/DiscoveryReportPanel';
export { default as AgentActivityFeed } from './Discovery/AgentActivityFeed';

// Run Settings
export { default as RunSettingsPanel } from './RunSettings/RunSettingsPanel';
export { default as PublicRunSettingsPanel } from './RunSettings/PublicRunSettingsPanel';

// Dialogs
export { default as ShareDialog } from './ShareDialog';
