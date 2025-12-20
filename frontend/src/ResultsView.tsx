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
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 20; // Increased margin for scientific look
      const contentWidth = pageWidth - 2 * margin;
      let y = 30; // Start lower for header space

      // Brand colors - slightly desaturated for print/scientific look
      const brandBlue = [0, 72, 180];
      const brandGreen = [21, 128, 61];
      const lightGreen = [240, 253, 244];
      const lightGray = [250, 250, 250];

      // Helper to add page footer
      const addFooter = () => {
        const pageCount = pdf.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
          pdf.setPage(i);
          pdf.setFontSize(9);
          pdf.setTextColor(120, 120, 120);
          pdf.setFont('helvetica', 'normal');
          pdf.line(margin, pageHeight - 15, pageWidth - margin, pageHeight - 15); // Footer line
          pdf.text(`Page ${i} of ${pageCount}`, pageWidth / 2, pageHeight - 8, { align: 'center' });
          pdf.text('Syxplain Analysis', pageWidth - margin, pageHeight - 8, { align: 'right' });
        }
      };

      // Helper to draw section card background
      const drawSectionCard = (startY: number, height: number, accentColor: number[] = brandBlue as number[], bgColor: number[] = lightGray as number[]) => {
        // Background
        pdf.setFillColor(bgColor[0], bgColor[1], bgColor[2]);
        pdf.roundedRect(margin - 3, startY - 5, contentWidth + 6, height + 10, 2, 2, 'F');
        // Left accent strip
        pdf.setFillColor(accentColor[0], accentColor[1], accentColor[2]);
        pdf.rect(margin - 3, startY - 5, 1.5, height + 10, 'F');
      };

      // Helper to add text with word wrap and better spacing
      const addText = (text: string, fontSize: number, isBold = false, color = [0, 0, 0], align: 'left' | 'center' | 'right' | 'justify' = 'left') => {
        pdf.setFontSize(fontSize);
        pdf.setFont('times', isBold ? 'bold' : 'normal'); // Times New Roman for scientific look
        pdf.setTextColor(color[0], color[1], color[2]);

        const lineHeightFactor = 0.5; // Increased line height
        const lines = pdf.splitTextToSize(text, contentWidth - 2);

        lines.forEach((line: string) => {
          if (y > pageHeight - margin - 10) {
            pdf.addPage();
            y = 30;
          }
          pdf.text(line, margin, y, { align });
          y += fontSize * lineHeightFactor + 1; // Extra breathing room
        });
        y += 2; // Paragraph spacing
      };

      // ===== HEADER =====
      // Minimal scientific header
      pdf.setDrawColor(brandBlue[0], brandBlue[1], brandBlue[2]);
      pdf.setLineWidth(0.5);
      pdf.line(margin, 20, pageWidth - margin, 20);

      pdf.setFontSize(22);
      pdf.setFont('helvetica', 'bold');
      pdf.setTextColor(20, 20, 20);
      pdf.text('Analysis Report', margin, 16);

      pdf.setFontSize(10);
      pdf.setFont('helvetica', 'normal');
      pdf.setTextColor(80, 80, 80);
      pdf.text(`Run ID: ${runId?.slice(0, 8)}`, pageWidth - margin, 12, { align: 'right' });
      pdf.text(`${new Date().toLocaleDateString()}`, pageWidth - margin, 17, { align: 'right' });

      y = 35; // Start content below header

      // ===== SUMMARY SECTION =====
      if (summary) {
        // Section header
        pdf.setFontSize(14);
        pdf.setFont('helvetica', 'bold');
        pdf.setTextColor(brandBlue[0], brandBlue[1], brandBlue[2]);
        pdf.text('Analysis Summary', margin, y);
        pdf.setDrawColor(200, 200, 200);
        pdf.setLineWidth(0.2);
        pdf.line(margin, y + 2, pageWidth - margin, y + 2);

        y += 8;

        if (summary.key_drivers?.length > 0) {
          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(40, 40, 40);
          pdf.text('Primary Drivers:', margin, y);
          y += 5;

          const drivers = summary.key_drivers.join(', ');
          addText(drivers, 10, false, [20, 20, 20]);
          y += 3;
        }

        if (summary.secondary_drivers?.length > 0) {
          y += 3;
          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(40, 40, 40);
          pdf.text('Secondary Drivers:', margin, y);
          y += 5;

          const drivers = summary.secondary_drivers.join(', ');
          addText(drivers, 10, false, [60, 60, 60]);
          y += 3;
        }

        if (summary.findings) {
          y += 5;
          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(40, 40, 40);
          pdf.text('Key Findings:', margin, y);
          y += 5;
          addText(summary.findings, 10, false, [20, 20, 20], 'justify');
          y += 6;
        }
        y += 6; // Spacing after summary
      }

      // ===== RECOMMENDATION SECTION =====
      if (recommendation && recommendation.equation_id > 0) {
        const recStartY = y;
        const recEq = equations?.find((eq: { id: number }) => eq.id === recommendation.equation_id);

        // Estimate height
        // Estimate height dynamically based on wrapped text
        let recHeight = 35;
        if (recEq) {
          // Estimate equation height
          pdf.setFontSize(12);
          pdf.setFont('times', 'italic');
          const lines = pdf.splitTextToSize(recEq.equation, contentWidth - 10);
          recHeight += lines.length * 6 + 10;
        }

        // Calculate rationale height with wrapping
        if (recommendation.rationale?.length > 0) {
          pdf.setFontSize(10);
          pdf.setFont('times', 'normal');
          let rationaleHeight = 6; // Header 'Selection Rationale:'
          recommendation.rationale.forEach((reason: string) => {
            const lines = pdf.splitTextToSize(`• ${reason}`, contentWidth - 10);
            rationaleHeight += lines.length * 6;
          });
          recHeight += rationaleHeight;
        }

        drawSectionCard(recStartY, recHeight, brandGreen as number[], lightGreen as number[]);

        // Section title
        pdf.setFontSize(12);
        pdf.setFont('helvetica', 'bold');
        pdf.setTextColor(brandGreen[0], brandGreen[1], brandGreen[2]);
        pdf.text('RECOMMENDED MODEL', margin + 2, y);
        y += 8;

        if (recEq) {
          pdf.setFontSize(11);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(20, 20, 20);
          pdf.text(`Equation ${recEq.id}`, margin + 2, y);
          y += 6;

          pdf.setFontSize(12);
          pdf.setFont('times', 'italic');
          pdf.setTextColor(40, 40, 40);
          const eqLines = pdf.splitTextToSize(recEq.equation, contentWidth - 10);
          eqLines.forEach((line: string) => {
            pdf.text(line, margin + 5, y);
            y += 6;
          });
        }

        if (recommendation.rationale?.length > 0) {
          y += 3;
          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(60, 60, 60);
          pdf.text('Selection Rationale:', margin + 2, y);
          y += 5;

          recommendation.rationale.forEach((reason: string) => {
            pdf.setFontSize(10);
            pdf.setFont('times', 'normal'); // Scientific body text
            pdf.setTextColor(40, 40, 40);
            const rLines = pdf.splitTextToSize(`• ${reason}`, contentWidth - 10);
            rLines.forEach((line: string) => {
              pdf.text(line, margin + 5, y);
              y += 5;
            });
          });
        }
        y += 10; // Increased section spacing
      }

      // ===== ALL EQUATIONS =====
      if (equations?.length > 0) {
        pdf.addPage();
        y = 30;
        // Section header
        pdf.setFontSize(14);
        pdf.setFont('helvetica', 'bold');
        pdf.setTextColor(brandBlue[0], brandBlue[1], brandBlue[2]);
        pdf.text('Detailed Equation Analysis', margin, y);

        // Horizontal rule
        pdf.setDrawColor(200, 200, 200);
        pdf.setLineWidth(0.2);
        pdf.line(margin, y + 2, pageWidth - margin, y + 2);

        y += 12;

        equations.forEach((eq: {
          id: number;
          equation: string;
          loss: number;
          complexity: number;
          overview: string;
          term_explanations?: { term: string; explanation: string }[];
          citations?: string[];
          scatter_data?: { measured: number[]; predicted: number[] };
        }, idx: number) => {
          if (y > 240) {
            pdf.addPage();
            y = 20;
          }



          // Equation number and metrics line
          pdf.setFillColor(brandBlue[0], brandBlue[1], brandBlue[2]);
          pdf.roundedRect(margin, y - 4, 10, 8, 2, 2, 'F');
          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'bold');
          pdf.setTextColor(255, 255, 255);
          pdf.text(String(eq.id), margin + 5, y + 1.5, { align: 'center' });

          pdf.setFontSize(12);
          pdf.setTextColor(20, 20, 20);
          pdf.text(`Equation Model ${eq.id}`, margin + 14, y + 1);

          // Metrics styled as text instead of badges for scientific clean look
          pdf.setFontSize(9);
          pdf.setFont('helvetica', 'normal');
          pdf.setTextColor(80, 80, 80);
          const metrics = `Loss: ${eq.loss.toFixed(4)}   |   Complexity: ${eq.complexity}`;
          pdf.text(metrics, pageWidth - margin, y + 1, { align: 'right' });

          y += 8;

          // Equation box (scientific styling)
          // Equation box (scientific styling)
          pdf.setFillColor(250, 250, 250);
          pdf.setDrawColor(230, 230, 230);

          pdf.setFontSize(10);
          pdf.setFont('times', 'italic');
          pdf.setTextColor(0, 0, 0);
          const eqText = pdf.splitTextToSize(eq.equation, contentWidth - 10);
          const boxHeight = Math.max(12, eqText.length * 6 + 6);

          pdf.rect(margin, y - 3, contentWidth, boxHeight, 'FD'); // Dynamic height box

          let textY = y + 4;
          eqText.forEach((line: string) => {
            pdf.text(line, contentWidth / 2 + margin, textY, { align: 'center' });
            textY += 6;
          });
          y += boxHeight + 6;

          // Overview paragraph
          addText(eq.overview, 10, false, [40, 40, 40], 'justify');
          y += 2;

          // Term Breakdown
          if (eq.term_explanations && eq.term_explanations.length > 0) {
            y += 2;
            pdf.setFontSize(10);
            pdf.setFont('helvetica', 'bold');
            pdf.setTextColor(brandBlue[0], brandBlue[1], brandBlue[2]);
            pdf.text('Term Interpretation', margin, y);
            y += 6;

            eq.term_explanations.forEach((term: { term: string; explanation: string }) => {
              if (y > pageHeight - margin - 20) { pdf.addPage(); y = 30; }

              const termPrefix = `${term.term}: `;
              pdf.setFontSize(10);
              pdf.setFont('times', 'bold');
              pdf.setTextColor(0, 0, 0);
              const prefixWidth = pdf.getTextWidth(termPrefix);
              pdf.text(termPrefix, margin + 4, y);

              pdf.setFont('times', 'normal');
              pdf.setTextColor(60, 60, 60);

              // Handle multiline text indentation
              const explanationLines = pdf.splitTextToSize(term.explanation, contentWidth - prefixWidth - 4);
              if (explanationLines.length > 0) {
                pdf.text(explanationLines[0], margin + 4 + prefixWidth, y);
                for (let i = 1; i < explanationLines.length; i++) {
                  y += 5;
                  pdf.text(explanationLines[i], margin + 4 + prefixWidth, y);
                }
              }
              y += 6;
            });
            y += 4;
          }

          // Citations
          if (eq.citations && eq.citations.length > 0) {
            if (y > pageHeight - margin - 20) { pdf.addPage(); y = 30; }
            pdf.setFontSize(9);
            pdf.setFont('helvetica', 'bold');
            pdf.setTextColor(100, 100, 100);
            pdf.text('REFERENCES', margin, y);
            y += 5;

            eq.citations.forEach((citation: string, cIdx: number) => {
              if (y > pageHeight - margin - 10) { pdf.addPage(); y = 30; }
              pdf.setFontSize(8);
              pdf.setFont('helvetica', 'normal');
              pdf.setTextColor(brandBlue[0], brandBlue[1], brandBlue[2]);
              pdf.text(`[${cIdx + 1}] ${citation}`, margin + 4, y);
              y += 4;
            });
            y += 6;
          }

          // Scatter Plot
          if (eq.scatter_data && eq.scatter_data.measured.length > 0) {
            if (y > pageHeight - margin - 60) { pdf.addPage(); y = 30; }

            pdf.setFontSize(10);
            pdf.setFont('helvetica', 'bold');
            pdf.setTextColor(40, 40, 40);
            pdf.text('Predicted vs. Measured', margin, y);
            y += 6;

            const chartX = margin + 10;
            const chartY = y;
            const chartSize = 50;

            // Chart background - white with simple border
            pdf.setFillColor(255, 255, 255);
            pdf.setDrawColor(180, 180, 180);
            pdf.setLineWidth(0.2);
            pdf.rect(chartX, chartY, chartSize, chartSize);

            // Grid lines (dotted)
            pdf.setDrawColor(220, 220, 220);
            pdf.setLineDashPattern([1, 1], 0);
            for (let g = 1; g < 5; g++) {
              const gPos = g * (chartSize / 5);
              pdf.line(chartX + gPos, chartY, chartX + gPos, chartY + chartSize);
              pdf.line(chartX, chartY + gPos, chartX + chartSize, chartY + gPos);
            }
            pdf.setLineDashPattern([], 0); // Reset dash

            const allVals = [...eq.scatter_data.measured, ...eq.scatter_data.predicted];
            const minVal = Math.min(...allVals);
            const maxVal = Math.max(...allVals);
            const range = maxVal - minVal || 1;

            // 1:1 line
            pdf.setDrawColor(200, 50, 50);
            pdf.setLineWidth(0.3);
            pdf.line(chartX, chartY + chartSize, chartX + chartSize, chartY);

            // Scatter points
            pdf.setFillColor(brandBlue[0], brandBlue[1], brandBlue[2]);
            const sampleRate = Math.max(1, Math.floor(eq.scatter_data.measured.length / 80));
            for (let i = 0; i < eq.scatter_data.measured.length; i += sampleRate) {
              const xNorm = (eq.scatter_data.measured[i] - minVal) / range;
              const yNorm = (eq.scatter_data.predicted[i] - minVal) / range;
              const px = chartX + xNorm * chartSize;
              const py = chartY + chartSize - yNorm * chartSize;
              pdf.circle(px, py, 0.7, 'F');
            }

            // Labels
            pdf.setFontSize(8);
            pdf.setTextColor(80, 80, 80);
            pdf.text('Measured', chartX + chartSize / 2, chartY + chartSize + 5, { align: 'center' });
            pdf.text('Predicted', chartX - 5, chartY + chartSize / 2, { angle: 90, align: 'center' });

            y = chartY + chartSize + 15;
          }

          // Separator line between equations
          if (idx < equations.length - 1) {
            pdf.setDrawColor(230, 230, 230);
            pdf.setLineWidth(0.3);
            pdf.line(margin, y, pageWidth - margin, y);
            y += 6;
          }
        });
      }

      // Add page footers
      addFooter();

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
              <>
                {result && (
                  <Button
                    icon={exportingPdf ? "pi pi-spin pi-spinner" : "pi pi-file-pdf"}
                    onClick={handleExportPdf}
                    disabled={exportingPdf}
                    size="large"
                    className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-3 py-2 shadow-sm"
                    tooltip="Export to PDF"
                    tooltipOptions={{ position: 'bottom' }}
                  />
                )}
              <Message severity="success" text="Completed" className="w-full md:w-auto" />
              </>
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
