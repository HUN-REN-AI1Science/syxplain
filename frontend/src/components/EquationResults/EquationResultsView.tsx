/**
 * EquationResultsView Component
 * Displays equation analysis results with MathJax rendering and interactive charts
 */

import React, { useState, useMemo } from 'react';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { SplitButton } from 'primereact/splitbutton';
import { MathJax, MathJaxContext } from 'better-react-mathjax';
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js';
import { Scatter } from 'react-chartjs-2';
import { escapeForAsciiMath } from '@utils/formatting';
import { exportToCSV, exportToExcel } from '@utils/dataExport';
import CitationText from './CitationText';
import type { Equation, ScatterData, EquationResults } from '@/types';

// Register Chart.js components
ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend);

interface EquationResultsViewProps {
  data: EquationResults;
}

const mathJaxConfig = {
  loader: { load: ['input/asciimath', 'input/tex', 'output/chtml'] },
  asciimath: { displaystyle: true, delimiters: [['`', '`']] },
  tex: {
    inlineMath: [['$', '$'], ['\\(', '\\)']],
    displayMath: [['$$', '$$'], ['\\[', '\\]']]
  }
};

// Interactive Scatter Plot Component
const ScatterPlot: React.FC<{ data: ScatterData }> = ({ data }) => {
  const chartData = useMemo(() => {
    const points = data.measured.map((m, i) => ({ x: m, y: data.predicted[i] }));

    // Calculate min/max for 1:1 line
    const allValues = [...data.measured, ...data.predicted];
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);
    const padding = (maxVal - minVal) * 0.05;

    return {
      datasets: [
        {
          label: 'Data Points',
          data: points,
          backgroundColor: 'rgba(0, 82, 204, 0.5)',
          borderColor: 'rgba(0, 82, 204, 0.8)',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: '1:1 Line',
          data: [
            { x: minVal - padding, y: minVal - padding },
            { x: maxVal + padding, y: maxVal + padding }
          ],
          showLine: true,
          borderColor: 'rgba(220, 38, 38, 0.8)',
          borderDash: [5, 5],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
        }
      ]
    };
  }, [data]);

  const options = useMemo(() => {
    const allValues = [...data.measured, ...data.predicted];
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);
    const padding = (maxVal - minVal) * 0.1;

    return {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1,
      plugins: {
        legend: {
          position: 'top' as const,
          labels: {
            usePointStyle: true,
            font: { size: 11 }
          }
        },
        tooltip: {
          callbacks: {
            label: (context: any) => {
              if (context.dataset.label === '1:1 Line') return '';
              return `Measured: ${context.parsed.x.toFixed(3)}, Predicted: ${context.parsed.y.toFixed(3)}`;
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Measured', font: { size: 12 } },
          min: minVal - padding,
          max: maxVal + padding,
          grid: { color: 'rgba(0, 0, 0, 0.05)' }
        },
        y: {
          title: { display: true, text: 'Predicted', font: { size: 12 } },
          min: minVal - padding,
          max: maxVal + padding,
          grid: { color: 'rgba(0, 0, 0, 0.05)' }
        }
      }
    };
  }, [data]);

  return (
    <div className="w-full max-w-md mx-auto">
      <Scatter data={chartData} options={options} />
    </div>
  );
};

const EquationCard: React.FC<{ equation: Equation; isRecommended: boolean }> = ({ equation, isRecommended }) => {
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  // Count available details
  const detailsCount = [
    equation.scatter_data ? 1 : 0,
    (equation.term_explanations?.length ?? 0) > 0 ? 1 : 0,
    (equation.citations?.length ?? 0) > 0 ? 1 : 0
  ].reduce((a, b) => a + b, 0);

  const hasDetails = detailsCount > 0;

  return (
    <MathJaxContext config={mathJaxConfig}>
      <div className={`rounded-xl border overflow-hidden transition-all duration-300 ${isRecommended
        ? 'border-green-300 bg-gradient-to-br from-green-50 to-emerald-50 ring-2 ring-green-200'
        : 'border-slate-200 bg-white hover:border-slate-300'
        }`}>
        {/* Header */}
        <div className={`px-5 py-4 flex items-center justify-between ${isRecommended
          ? 'bg-gradient-to-r from-green-100 to-emerald-100'
          : 'bg-gradient-to-r from-blue-50 to-slate-50'
          }`}>
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg ${isRecommended
              ? 'bg-green-500 text-white'
              : 'bg-blue-500 text-white'
              }`}>
              {equation.id}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800">Equation {equation.id}</span>
                {isRecommended && (
                  <Tag value="Recommended" severity="success" className="text-xs" />
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Tag
              value={`Loss: ${equation.loss.toFixed(3)}`}
              className="bg-amber-100 text-amber-800 text-xs px-2 py-1"
            />
            <Tag
              value={`Complexity: ${equation.complexity}`}
              className="bg-slate-100 text-slate-700 text-xs px-2 py-1"
            />
          </div>
        </div>

        {/* Equation Display with MathJax */}
        <div className="px-5 py-4">
          <div className="bg-slate-50 rounded-lg p-4 overflow-x-auto border border-slate-200">
            <MathJax inline dynamic>
              {`\`${escapeForAsciiMath(equation.equation)}\``}
            </MathJax>
          </div>

          {/* Overview */}
          <p className="mt-4 text-slate-600 leading-relaxed">
            <CitationText text={equation.overview} citations={equation.citations} />
          </p>

          {/* Foldable Details Section */}
          {hasDetails && (
            <div className="mt-4">
              <Button
                label={detailsExpanded ? 'Hide Details' : 'Show Details'}
                icon={detailsExpanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'}
                iconPos="left"
                className="p-button-text p-button-sm !text-blue-600 hover:!bg-blue-50 !px-4 !py-2"
                onClick={() => setDetailsExpanded(!detailsExpanded)}
              />

              <div className={`overflow-hidden transition-all duration-400 ease-in-out ${detailsExpanded ? 'max-h-[3000px] opacity-100 mt-4' : 'max-h-0 opacity-0'
                }`}>
                <div className="space-y-4 bg-slate-50 rounded-lg p-4 border border-slate-200">



                  {/* Term Explanations */}
                  {equation.term_explanations && equation.term_explanations.length > 0 && (
                    <div>
                      <h5 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
                        <i className="pi pi-info-circle text-blue-500"></i>
                        Term Breakdown ({equation.term_explanations.length})
                      </h5>
                      <div className="space-y-2">
                        {equation.term_explanations.map((term, idx) => (
                          <div key={idx} className="bg-white rounded-lg p-3 border border-slate-100">
                            <code className="text-blue-600 font-mono text-sm bg-blue-50 px-2 py-1 rounded">
                              {term.term}
                            </code>
                            <p className="mt-2 text-sm text-slate-600">
                              <CitationText text={term.explanation} citations={equation.citations} />
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Scatter Plot */}
                  {equation.scatter_data && (
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h5 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <i className="pi pi-chart-line text-blue-500"></i>
                          Predicted vs. Measured
                        </h5>
                        <SplitButton
                          label="Export Data"
                          icon="pi pi-table"
                          onClick={() => {
                            exportToCSV([equation], `eq${equation.id}`);
                          }}
                          model={[
                            {
                              label: 'Excel (.xlsx)',
                              icon: 'pi pi-file-excel',
                              command: () => exportToExcel([equation], `eq${equation.id}`)
                            }
                          ]}
                          className="equation-export-button"
                          size="small"
                        />
                      </div>
                      <div className="bg-white rounded-lg p-4 border border-slate-200">
                        <ScatterPlot data={equation.scatter_data} />
                      </div>
                    </div>
                  )}

                  {/* Citations */}
                  {equation.citations && equation.citations.length > 0 && (
                    <div>
                      <h5 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
                        <i className="pi pi-book text-blue-500"></i>
                        Scientific Sources ({equation.citations.length})
                      </h5>
                      <div className="bg-white rounded-lg p-3 border border-slate-100">
                        <ul className="space-y-1">
                          {equation.citations.map((citation, idx) => (
                            <li key={idx} className="text-sm">
                              <a
                                href={citation}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-800 hover:underline break-all"
                              >
                                <span className="citation-link">[{idx + 1}]</span> {citation}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </MathJaxContext>
  );
};

const EquationResultsView: React.FC<EquationResultsViewProps> = ({ data }) => {
  const { equations, summary, recommendation } = data;

  // Handle parse error fallback
  if (data._parse_error) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <i className="pi pi-exclamation-triangle text-amber-600 text-xl mt-0.5"></i>
          <div>
            <h4 className="font-semibold text-amber-800">Results Format Issue</h4>
            <p className="text-amber-700 mt-1 text-sm">
              The analysis completed but the results couldn't be fully parsed. Here's the raw output:
            </p>
            <pre className="mt-4 bg-white p-4 rounded-lg border border-amber-200 text-sm overflow-x-auto whitespace-pre-wrap">
              {summary?.findings || 'No results available'}
            </pre>
          </div>
        </div>
      </div>
    );
  }

  return (
    <MathJaxContext config={mathJaxConfig}>
      <div className="space-y-6">
        {/* Summary Section */}
        {summary && (
          <div className="bg-gradient-to-br from-blue-50 to-slate-50 rounded-xl border border-blue-200 p-6">
            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2 mb-4">
              <i className="pi pi-chart-bar text-blue-500"></i>
              Analysis Summary
            </h3>

            {/* Key Drivers */}
            {summary.key_drivers && summary.key_drivers.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold text-slate-600 mb-2">Key Drivers</h4>
                <div className="flex flex-wrap gap-2">
                  {summary.key_drivers.map((driver, idx) => (
                    <Tag
                      key={idx}
                      value={driver}
                      severity="success"
                      className="font-mono text-sm"
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Secondary Drivers */}
            {summary.secondary_drivers && summary.secondary_drivers.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold text-slate-600 mb-2">Secondary Drivers</h4>
                <div className="flex flex-wrap gap-2">
                  {summary.secondary_drivers.map((driver, idx) => (
                    <Tag
                      key={idx}
                      value={driver}
                      className="bg-slate-200 text-slate-700 font-mono text-sm"
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Findings */}
            {summary.findings && (
              <div>
                <h4 className="text-sm font-semibold text-slate-600 mb-2">Findings</h4>
                <p className="text-slate-700 leading-relaxed">{summary.findings}</p>
              </div>
            )}
          </div>
        )}

        {/* Recommendation Card */}
        {recommendation && recommendation.equation_id > 0 && (() => {
          const recommendedEquation = equations.find(eq => eq.id === recommendation.equation_id);
          return (
            <div className="bg-gradient-to-br from-green-50 to-emerald-100 rounded-xl border border-green-200 p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center flex-shrink-0">
                  <i className="pi pi-star-fill text-white text-lg"></i>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-bold text-green-800">Recommended: Equation {recommendation.equation_id}</h3>
                  {recommendedEquation && (
                    <div className="mt-3 bg-white rounded-lg p-3 border border-green-200 overflow-x-auto">
                      <MathJax inline dynamic>
                        {`\`${escapeForAsciiMath(recommendedEquation.equation)}\``}
                      </MathJax>
                    </div>
                  )}
                  {recommendation.rationale && recommendation.rationale.length > 0 && (
                    <ul className="mt-4 space-y-2">
                      {recommendation.rationale.map((reason, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-slate-600">
                          <i className="pi pi-check-circle text-green-500 mt-0.5 flex-shrink-0"></i>
                          <span className="text-sm">{reason}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          );
        })()}

        {/* Equations List */}
        {equations && equations.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <i className="pi pi-list text-blue-500"></i>
              All Equations ({equations.length})
            </h3>
            <div className="space-y-4">
              {equations.map((eq) => (
                <EquationCard
                  key={eq.id}
                  equation={eq}
                  isRecommended={eq.id === recommendation?.equation_id}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </MathJaxContext>
  );
};

export default EquationResultsView;
