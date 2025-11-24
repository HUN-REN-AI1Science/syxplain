import React, { useEffect, useState } from 'react';
import api from './api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { MathJax, MathJaxContext } from 'better-react-mathjax';

interface ResultsViewProps {
  runId: string;
}

const ResultsView: React.FC<ResultsViewProps> = ({ runId }) => {
  const [status, setStatus] = useState<string>('pending');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return; // Don't poll if runId is not set yet

    let intervalId: NodeJS.Timeout;

    const poll = async () => {
      try {
        const response = await api.get(`/runs/${runId}`);
        setStatus(response.data.status);

        if (response.data.status === 'completed') {
          setResult(response.data.results.pysr_explanations);
          clearInterval(intervalId);
        } else if (response.data.status === 'failed') {
          setError(response.data.error || 'Unknown error');
          clearInterval(intervalId);
        }
      } catch (e) {
        console.error(e);
      }
    };

    poll(); // Initial call
    intervalId = setInterval(poll, 2000);

    return () => clearInterval(intervalId);
  }, [runId]);

  const handleDownload = async (filename: string) => {
    try {
      const response = await api.get(`/runs/${runId}/download/${filename}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      alert('Failed to download file');
    }
  };

  const isEquation = (text: string): boolean => {
    // Heuristic: contains math operators and no common code keywords
    const mathOperators = ['+', '-', '*', '/', '=', '(', ')'];
    const codeKeywords = ['def', 'return', 'import', 'from', 'class', 'if', 'else', 'for', 'while', 'print', 'const', 'let', 'var', 'function'];

    const hasOperator = mathOperators.some(op => text.includes(op));
    const hasKeyword = codeKeywords.some(keyword => new RegExp(`\\b${keyword}\\b`).test(text));

    // Also check if it looks like a file path or simple variable assignment without math
    const isSimpleAssignment = /^[a-zA-Z0-9_]+\s*=\s*[a-zA-Z0-9_]+$/.test(text.trim());

    return hasOperator && !hasKeyword && !isSimpleAssignment;
  };

  const mathJaxConfig = {
    loader: { load: ["input/asciimath", "input/tex", "output/chtml"] },
    asciimath: {
      displaystyle: true,
      delimiters: [["`", "`"]]
    },
    tex: {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']]
    }
  };

  return (
    <div className="p-4">
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

      <div>
        {error && (
          <div className="mb-6">
            <Message severity="error" text={`Analysis Failed: ${error}`} className="w-full" />
          </div>
        )}

        {(!runId || status === 'pending' || status === 'running') && !error && (
          <div className="text-center py-20">
            <ProgressSpinner style={{ width: '50px', height: '50px' }} strokeWidth="4" animationDuration=".5s" />
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
            <MathJaxContext config={mathJaxConfig}>
              <div className="prose prose-slate max-w-none p-8 bg-slate-50 rounded-xl border border-slate-200 shadow-inner">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    pre(props) {
                      const { children, ...rest } = props;

                      // Check if the child is a code element
                      // When using react-markdown, the child of pre is usually a code element.
                      // Since we removed the custom code component, children.type should be 'code'.
                      if (React.isValidElement(children) && (children.type === 'code' || typeof children.type === 'function')) {
                        // Extract text content from the code element's children
                        // @ts-ignore - children.props is not typed in generic ReactElement
                        const rawContent = String(children.props.children);
                        // Replace newlines with spaces for AsciiMath to render as a single equation
                        const textContent = rawContent.replace(/\s+/g, ' ').trim();

                        if (isEquation(textContent)) {
                          return (
                            <div className="overflow-x-auto w-full">
                              <MathJax inline={false} dynamic>
                                {`\`${textContent}\``}
                              </MathJax>
                            </div>
                          );
                        }
                      }

                      return <pre {...rest}>{children}</pre>;
                    },
                    p(props) {
                      const { children } = props;

                      // If children is just a string, we can process it
                      if (typeof children === 'string') {
                        const parts = children.split(/(\[.*?\])/g);
                        return (
                          <p className="mb-4">
                            {parts.map((part, index) => {
                              // Check if part matches [ ... ] and contains latex-like chars
                              if (part.startsWith('[') && part.endsWith(']') && (part.includes('\\') || part.includes('_'))) {
                                // Remove brackets for rendering if needed, or keep them if they are part of the syntax
                                // The user example was [ \text{...} ], which looks like a display math block.
                                // We'll try to render it as TeX.
                                let content = part.slice(1, -1);

                                // Fix for underscores in \text{...} which cause "allowed only in math mode" error
                                content = content.replace(/\\text\{([^}]+)\}/g, (_, inner) => {
                                  return `\\text{${inner.replace(/_/g, '\\_')}}`;
                                });

                                return (
                                  <div key={index} className="overflow-x-auto w-full">
                                    <MathJax inline={false} dynamic>
                                      {`\\[${content}\\]`}
                                    </MathJax>
                                  </div>
                                );
                              }
                              return <span key={index}>{part}</span>;
                            })}
                          </p>
                        );
                      }

                      // If children is an array (mixed text and other elements), we need to process text nodes
                      if (Array.isArray(children)) {
                        return (
                          <p className="mb-4">
                            {React.Children.map(children, (child) => {
                              if (typeof child === 'string') {
                                const parts = child.split(/(\[.*?\])/g);
                                return parts.map((part, i) => {
                                  if (part.startsWith('[') && part.endsWith(']') && (part.includes('\\') || part.includes('_'))) {
                                    let content = part.slice(1, -1);

                                    // Fix for underscores in \text{...}
                                    content = content.replace(/\\text\{([^}]+)\}/g, (_, inner) => {
                                      return `\\text{${inner.replace(/_/g, '\\_')}}`;
                                    });

                                    return (
                                      <div key={i} className="overflow-x-auto w-full">
                                        <MathJax inline={false} dynamic>
                                          {`\\[${content}\\]`}
                                        </MathJax>
                                      </div>
                                    );
                                  }
                                  return part;
                                });
                              }
                              return child;
                            })}
                          </p>
                        );
                      }

                      return <p className="mb-4">{children}</p>;
                    }
                  }}
                >
                  {result}
                </ReactMarkdown>
              </div>
            </MathJaxContext>

            <div className="flex flex-wrap gap-4 pt-4 border-t border-slate-100">
              <Button
                label="Download Report (Markdown)"
                icon="pi pi-download"
                onClick={() => handleDownload('pysr_explanations.md')}
              />
              <Button
                label="Download Logs (Coming Soon)"
                icon="pi pi-file"
                outlined
                disabled
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsView;
