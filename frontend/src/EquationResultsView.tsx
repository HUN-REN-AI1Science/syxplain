import React, { useState } from 'react';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { MathJax, MathJaxContext } from 'better-react-mathjax';

interface TermExplanation {
  term: string;
  explanation: string;
}

interface Equation {
  id: number;
  equation: string;
  loss: number;
  complexity: number;
  overview: string;
  term_explanations: TermExplanation[];
}

interface Summary {
  key_drivers: string[];
  secondary_drivers: string[];
  findings: string;
}

interface Recommendation {
  equation_id: number;
  rationale: string[];
}

interface EquationResults {
  equations: Equation[];
  summary: Summary;
  recommendation: Recommendation;
  _parse_error?: string;
}

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

// Helper to escape special characters for AsciiMath rendering
// In AsciiMath, underscores create subscripts, so we need to wrap variable names in quotes
const escapeForAsciiMath = (text: string): string => {
  // Replace variable names containing underscores with quoted versions
  // This prevents AsciiMath from interpreting underscores as subscripts
  return text.replace(/([a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+)/g, '"$1"');
};

const EquationCard: React.FC<{ equation: Equation; isRecommended: boolean }> = ({ equation, isRecommended }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <MathJaxContext config={mathJaxConfig}>
      <div className={`rounded-xl border overflow-hidden transition-all duration-300 ${isRecommended
        ? 'border-green-300 bg-gradient-to-br from-green-50 to-emerald-50 ring-2 ring-green-200'
        : 'border-slate-200 bg-white hover:border-slate-300'
        }`}>
        {/* Header */}
        <div className={`px-5 py-4 flex items-center justify-between ${isRecommended
          ? 'bg-gradient-to-r from-green-100 to-emerald-100'
          : 'bg-gradient-to-r from-blue-50 to-indigo-50'
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
            {equation.overview}
          </p>

          {/* Term Explanations (Expandable with animation) */}
          {equation.term_explanations && equation.term_explanations.length > 0 && (
            <div className="mt-4">
              <Button
                label={expanded ? 'Hide term breakdown' : `Show term breakdown (${equation.term_explanations.length})`}
                icon={expanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'}
                iconPos="right"
                className="p-button-text p-button-sm text-blue-600"
                onClick={() => setExpanded(!expanded)}
              />

              <div className={`overflow-hidden transition-all duration-300 ease-in-out ${expanded ? 'max-h-[2000px] opacity-100 mt-3' : 'max-h-0 opacity-0'
                }`}>
                <div className="space-y-3">
                  {equation.term_explanations.map((term, idx) => (
                    <div key={idx} className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                      <code className="text-purple-600 font-mono text-sm bg-purple-50 px-2 py-1 rounded">
                        {term.term}
                      </code>
                      <p className="mt-2 text-sm text-slate-600">{term.explanation}</p>
                    </div>
                  ))}
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

        {/* Summary Section */}
        {summary && (
          <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl border border-indigo-200 p-6">
            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2 mb-4">
              <i className="pi pi-chart-bar text-indigo-500"></i>
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
      </div>
    </MathJaxContext>
  );
};

export default EquationResultsView;
