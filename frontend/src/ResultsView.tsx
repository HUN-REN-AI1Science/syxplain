import React, { useEffect, useState, useRef } from 'react';
import api from './api';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { ProgressBar } from 'primereact/progressbar';
import { Toast } from 'primereact/toast';
import RunSettingsPanel from './RunSettingsPanel';
import EquationResultsView from './EquationResultsView';
import jsPDF from 'jspdf';

interface ResultsViewProps {
  runId: string;
  fromHistory?: boolean;
}

interface ProgressPhase {
  name: string;
  label: string;
  progress_end: number;
  increment_rate: number;
}

const ResultsView: React.FC<ResultsViewProps> = ({ runId, fromHistory = false }) => {
  const [status, setStatus] = useState<string>('pending');
  const [backendProgress, setBackendProgress] = useState<number>(0);
  const [displayProgress, setDisplayProgress] = useState<number>(0);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressPhases, setProgressPhases] = useState<ProgressPhase[]>([]);
  const [exportingPdf, setExportingPdf] = useState(false);
  const toast = useRef<Toast>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Fetch progress config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await api.get('/progress-config');
        setProgressPhases(response.data.phases || []);
      } catch (e) {
        console.error('Failed to fetch progress config:', e);
      }
    };
    fetchConfig();
  }, []);

  // Smooth progress interpolation - slowly increment display progress
  useEffect(() => {
    if (status === 'completed' || status === 'failed' || status === 'timeout') {
      setDisplayProgress(status === 'completed' ? 100 : backendProgress);
      return;
    }

    // Find the current and next phase based on backend progress
    const getCurrentPhaseInfo = (backendProg: number) => {
      if (progressPhases.length === 0) {
        // Fallback defaults if config not loaded
        return { maxProgress: Math.min(backendProg + 5, 98), incrementRate: 0.2 };
      }

      // Find the phase that just ended (backend progress >= progress_end)
      let currentPhase: ProgressPhase | null = null;
      let nextPhase: ProgressPhase | null = null;

      for (let i = 0; i < progressPhases.length; i++) {
        if (backendProg >= progressPhases[i].progress_end) {
          currentPhase = progressPhases[i];
          nextPhase = progressPhases[i + 1] || null;
        }
      }

      // Max progress is the next phase's progress_end - 1, or 98 if at the end
      const maxProgress = nextPhase ? nextPhase.progress_end - 1 : 98;
      const incrementRate = currentPhase?.increment_rate || 0.2;

      return { maxProgress, incrementRate };
    };

    const intervalId = setInterval(() => {
      setDisplayProgress(current => {
        const { maxProgress, incrementRate } = getCurrentPhaseInfo(backendProgress);

        // If backend jumped ahead significantly, catch up faster
        if (backendProgress > current + 5) {
          return Math.min(current + 2, backendProgress);
        }

        // If we've reached the max for current phase, hold there
        if (current >= maxProgress) {
          return current;
        }

        // Normal slow increment towards max
        return Math.min(current + incrementRate, maxProgress);
      });
    }, 500);

    return () => clearInterval(intervalId);
  }, [backendProgress, status, progressPhases]);

  // Poll backend for actual progress
  useEffect(() => {
    if (!runId) return;

    let intervalId: NodeJS.Timeout;

    const poll = async () => {
      try {
        const response = await api.get(`/runs/${runId}`);
        setStatus(response.data.status);
        setBackendProgress(response.data.progress || 0);

        if (response.data.status === 'completed') {
          setResult(response.data.results.pysr_explanations);
          setBackendProgress(100);
          clearInterval(intervalId);
        } else if (response.data.status === 'failed' || response.data.status === 'timeout') {
          setError(response.data.error || (response.data.status === 'timeout' ? 'Analysis timed out' : 'Unknown error'));
          clearInterval(intervalId);
        }
      } catch (e) {
        console.error(e);
      }
    };

    poll();
    intervalId = setInterval(poll, 2000);

    return () => clearInterval(intervalId);
  }, [runId]);


  const handleExportPdf = async () => {
    if (!result) return;

    setExportingPdf(true);
    try {
      const parsedData = JSON.parse(result);
      const { equations, summary, recommendation } = parsedData;

      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });

      const pageWidth = pdf.internal.pageSize.getWidth();
      const margin = 15;
      const contentWidth = pageWidth - 2 * margin;
      let y = 20;

      // Helper to add text with word wrap
      const addText = (text: string, fontSize: number, isBold = false, color = [0, 0, 0]) => {
        pdf.setFontSize(fontSize);
        pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
        pdf.setTextColor(color[0], color[1], color[2]);
        const lines = pdf.splitTextToSize(text, contentWidth);
        lines.forEach((line: string) => {
          if (y > 280) {
            pdf.addPage();
            y = 20;
          }
          pdf.text(line, margin, y);
          y += fontSize * 0.4;
        });
        y += 2;
      };

      // Title
      addText('Syxplain Analysis Results', 18, true);
      addText(`Run ID: ${runId}`, 10, false, [100, 100, 100]);
      addText(`Generated: ${new Date().toLocaleString()}`, 10, false, [100, 100, 100]);
      y += 5;

      // Recommendation
      if (recommendation && recommendation.equation_id > 0) {
        addText('RECOMMENDED EQUATION', 14, true, [22, 163, 74]);
        const recEq = equations?.find((eq: { id: number }) => eq.id === recommendation.equation_id);
        if (recEq) {
          addText(`Equation ${recEq.id}`, 12, true);
          addText(recEq.equation, 10, false, [50, 50, 50]);
          y += 2;
        }
        if (recommendation.rationale?.length > 0) {
          addText('Rationale:', 10, true);
          recommendation.rationale.forEach((reason: string) => {
            addText(`• ${reason}`, 9);
          });
        }
        y += 5;
      }

      // All Equations
      if (equations?.length > 0) {
        addText('ALL EQUATIONS', 14, true);
        y += 2;

        equations.forEach((eq: { id: number; equation: string; loss: number; complexity: number; overview: string; term_explanations?: { term: string; explanation: string }[] }) => {
          if (y > 250) {
            pdf.addPage();
            y = 20;
          }

          addText(`Equation ${eq.id}`, 12, true, [59, 130, 246]);
          addText(`Loss: ${eq.loss.toFixed(4)} | Complexity: ${eq.complexity}`, 9, false, [100, 100, 100]);
          addText(eq.equation, 9, false, [30, 30, 30]);
          y += 2;
          addText(eq.overview, 9);

          if (eq.term_explanations && eq.term_explanations.length > 0) {
            addText('Term Breakdown:', 9, true);
            eq.term_explanations.forEach((term: { term: string; explanation: string }) => {
              addText(`  ${term.term}`, 8, false, [100, 60, 150]);
              addText(`    ${term.explanation}`, 8);
            });
          }
          y += 5;
        });
      }

      // Summary
      if (summary) {
        if (y > 240) {
          pdf.addPage();
          y = 20;
        }
        addText('ANALYSIS SUMMARY', 14, true);
        y += 2;

        if (summary.key_drivers?.length > 0) {
          addText('Key Drivers: ' + summary.key_drivers.join(', '), 10);
        }
        if (summary.secondary_drivers?.length > 0) {
          addText('Secondary Drivers: ' + summary.secondary_drivers.join(', '), 10);
        }
        if (summary.findings) {
          y += 2;
          addText('Findings:', 10, true);
          addText(summary.findings, 9);
        }
      }

      pdf.save(`syxplain_results_${runId.slice(0, 8)}.pdf`);
      toast.current?.show({ severity: 'success', summary: 'Export Complete', detail: 'PDF saved successfully' });
    } catch (e) {
      console.error('PDF export failed:', e);
      toast.current?.show({ severity: 'error', summary: 'Export Failed', detail: 'Failed to generate PDF' });
    } finally {
      setExportingPdf(false);
    }
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-slate-100 gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Analysis Results</h2>
          <p className="text-sm text-slate-500">
            {runId ? (
              <>Run ID: <span className="font-mono">{runId.slice(0, 8)}...</span></>
            ) : (
              <>Starting analysis...</>
            )}
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          {!runId || status === 'pending' || status === 'running' ? (
            <Message severity="info" text="Processing Data..." className="w-full md:w-auto" />
          ) : status === 'completed' ? (
              <Message severity="success" text="Completed" className="w-full md:w-auto" />
          ) : (
                <Message severity="error" text="Failed" className="w-full md:w-auto" />
          )}
        </div>
      </div>

      {/* Run Settings Panel - shown only when navigating from history */}
      {fromHistory && (
        <RunSettingsPanel runId={runId} />
      )}

      <div>
        {error && (
          <div className="mb-6">
            <Message severity="error" text={`Analysis Failed: ${error}`} className="w-full" />
          </div>
        )}

        {(!runId || status === 'pending' || status === 'running') && !error && (
          <div className="text-center py-20">
            <div className="max-w-md mx-auto mb-6">
              <ProgressBar value={displayProgress} showValue={false} style={{ height: '8px' }} className="mb-2" />
              <p className="text-lg font-semibold text-blue-600">{Math.floor(displayProgress)}% complete</p>
            </div>
            <h3 className="text-xl font-semibold text-slate-800 mt-4 mb-2">AI is analyzing your data</h3>
            <p className="text-slate-500 max-w-md mx-auto mb-4">
              This process involves symbolic regression and LLM reasoning. It might take a few minutes depending on the dataset size.
            </p>
            <p className="text-slate-600 text-sm max-w-md mx-auto">
              You can safely leave this page. Your results will be available in the <span className="font-semibold">History</span> menu once completed.
            </p>
          </div>
        )}

        {result && (
          <div className="space-y-8 animate-fade-in">
            {(() => {
              try {
                const parsedData = JSON.parse(result);
                return (
                  <>
                    <div ref={resultsRef}>
                      <EquationResultsView data={parsedData} />
                    </div>
                    <div className="flex flex-wrap gap-4 pt-6 mt-6 border-t border-slate-200">
                      <Button
                        label={exportingPdf ? "Exporting..." : "Export to PDF"}
                        icon={exportingPdf ? "pi pi-spin pi-spinner" : "pi pi-file-pdf"}
                        onClick={handleExportPdf}
                        disabled={exportingPdf}
                        size="large"
                        className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-6 py-3 shadow-md"
                      />
                    </div>
                  </>
                );
              } catch {
                // Fallback for legacy markdown format - show deprecation message with download option
                return (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
                    <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
                      <i className="pi pi-history text-amber-600 text-2xl"></i>
                    </div>
                    <h3 className="text-xl font-bold text-slate-800 mb-2">Legacy Run Format</h3>
                    <p className="text-slate-600 max-w-md mx-auto mb-6">
                      This analysis was generated using an older format that is no longer displayed in the application.
                      You can download the original results as a Markdown file.
                    </p>
                    <Button
                      label="Download Results (Markdown)"
                      icon="pi pi-download"
                      size="large"
                      className="!bg-blue-600 hover:!bg-blue-700 !border-blue-600 !text-white font-semibold px-6 py-3 shadow-lg"
                      onClick={() => {
                        // Create a blob and download directly since it's stored in the result
                        const blob = new Blob([result], { type: 'text/markdown' });
                        const url = window.URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.setAttribute('download', 'pysr_explanations.md');
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        window.URL.revokeObjectURL(url);
                      }}
                    />
                  </div>
                );
              }
            })()}
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsView;
