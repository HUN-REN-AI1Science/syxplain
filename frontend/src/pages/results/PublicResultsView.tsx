/**
 * PublicResultsView Page
 * Displays shared run results for unauthenticated users
 */

import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card } from 'primereact/card';
import { Message } from 'primereact/message';
import {
  PublicRunSettingsPanel,
  PublicHeader,
  LoadingSpinner,
  ResultsHeader,
  ResultContent,
} from '@components/Results';
import { publicService, type PublicRunData } from '@services/api';
import type { EquationResults } from '@/types';

const PublicResultsView: React.FC = () => {
  const { token } = useParams<{ token: string }>();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runData, setRunData] = useState<PublicRunData | null>(null);

  useEffect(() => {
    if (!token) {
      setError('Invalid share link');
      setLoading(false);
      return;
    }

    const fetchPublicRun = async () => {
      try {
        const response = await publicService.getResults(token);
        setRunData(response.data);

        if (response.data.status !== 'completed') {
          setError('This analysis is not yet complete');
        }
      } catch (e: unknown) {
        console.error('Failed to fetch public run:', e);
        const err = e as { response?: { status?: number } };
        if (err.response?.status === 404) {
          setError('This share link is invalid or has been revoked');
        } else {
          setError('Failed to load shared results');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchPublicRun();
  }, [token]);

  // Parse results - handle both new direct format and old wrapper format
  let parsedResults: EquationResults | string | null = null;

  if (runData?.results) {
    const results = runData.results;
    if ('equations' in results) {
      // New format: results is the EquationResults object directly
      parsedResults = results as EquationResults;
    } else if ('pysr_explanations' in results) {
      // Old format: pass through to ResultContent for parsing
      parsedResults = results.pysr_explanations;
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 font-sans flex flex-col">
      <PublicHeader />

      <main className="flex-grow py-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
            {/* Loading State */}
            {loading && (
              <LoadingSpinner message="Loading shared results..." className="min-h-[400px] p-6" />
            )}

            {/* Error State */}
            {!loading && error && (
              <div className="flex flex-col items-center justify-center p-6 min-h-[400px]">
                <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mb-4">
                  <i className="pi pi-exclamation-triangle text-red-500 text-3xl"></i>
                </div>
                <h2 className="text-xl font-bold text-slate-800 mb-2">Unable to Load Results</h2>
                <p className="text-slate-600 text-center max-w-md mb-6">{error}</p>
                <Message
                  severity="warn"
                  className="max-w-md"
                  content={
                    <span>The share link may have expired or been revoked by the owner.</span>
                  }
                />
              </div>
            )}

            {/* Results */}
            {!loading && !error && runData && (
              <div className="p-4">
                {/* Header */}
                <ResultsHeader
                  title="Shared Analysis Results"
                  subtitle="These results have been shared publicly by the owner."
                  status="completed"
                />

                {/* Run Settings Panel (Public Mode) */}
                {token && <PublicRunSettingsPanel shareToken={token} />}

                {/* Results Content */}
                {parsedResults ? (
                  <ResultContent result={parsedResults} />
                ) : (
                  <Message severity="warn" text="No results available" className="w-full" />
                )}
              </div>
            )}
          </Card>
        </div>
      </main>

      <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 text-center text-slate-400 text-sm">
          &copy; {new Date().getFullYear()} Syxplain AI. All rights reserved.
        </div>
      </footer>
    </div>
  );
};

export default PublicResultsView;
