import { useState, useRef } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import UploadView from '@pages/UploadView';
import ProblemView from '@pages/ProblemView';
import ResultsView from '@pages/results/ResultsView';
import HistoryView from '@pages/HistoryView';
import ProfileView from '@pages/ProfileView';
import AdminLayout from '@pages/admin/AdminLayout';
import Login from '@pages/auth/Login';
import SignUp from '@pages/auth/SignUp';
import ForgotPassword from '@pages/auth/ForgotPassword';
import PublicResultsView from '@pages/results/PublicResultsView';
import { AuthProvider, useAuth } from '@contexts/AuthContext';
import { runsService } from '@services/api';
import { Toast } from 'primereact/toast';
import { Card } from 'primereact/card';
import { SwitchTransition, CSSTransition } from 'react-transition-group';
import AppHeader from '@components/AppHeader';
import AppFooter from '@components/AppFooter';
import WorkflowSteps from '@components/WorkflowSteps';
import FeedbackDialog from '@components/FeedbackDialog';
import type { FeedbackContext } from '@/types';

const WORKFLOW_STEPS = [
  { label: 'Upload Data' },
  { label: 'Define Problem' },
  { label: 'Analysis Results' },
];

function MainApp() {
  const [view, setView] = useState<'workflow' | 'history' | 'profile' | 'admin'>('workflow');
  const [activeIndex, setActiveIndex] = useState(0);
  const [filename, setFilename] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [excludedColumns, setExcludedColumns] = useState<string[]>([]);
  const [nanCounts, setNanCounts] = useState<Record<string, number>>({});
  const [runId, setRunId] = useState<string | null>(null);
  const [fromHistory, setFromHistory] = useState<boolean>(false);
  const [feedbackVisible, setFeedbackVisible] = useState(false);
  const toast = useRef<Toast>(null);
  const nodeRef = useRef(null);
  const { signOut, user, isAdmin } = useAuth();

  const handleUploadComplete = (
    fname: string,
    cols: string[],
    excludedCols: string[] = [],
    nanCountsData: Record<string, number> = {}
  ) => {
    setFilename(fname);
    setColumns(cols);
    setExcludedColumns(excludedCols);
    setNanCounts(nanCountsData);
    setActiveIndex(1);
  };

  const handleStartAnalysis = async (problemData: any) => {
    setFromHistory(false);
    setActiveIndex(2);

    try {
      const { analysis_type, deep_research_model, user_api_keys, ...problemDescription } =
        problemData;
      const response = await runsService.create({
        problem_description: problemDescription,
        csv_filename: filename!,
        analysis_type: analysis_type || 'quick',
        deep_research_model: deep_research_model || null,
        user_api_keys: user_api_keys,
      });
      setRunId(response.data.run_id);
    } catch (e: any) {
      const errorMessage = e.response?.data?.detail || 'Failed to start analysis';
      toast.current?.show({ severity: 'error', summary: 'Error', detail: errorMessage });
      console.error(e);
      setActiveIndex(1);
    }
  };

  const handleReset = () => {
    setView('workflow');
    setActiveIndex(0);
    setFilename(null);
    setColumns([]);
    setExcludedColumns([]);
    setNanCounts({});
    setRunId(null);
    setFromHistory(false);
  };

  const handleSelectRun = (selectedRunId: string) => {
    setRunId(selectedRunId);
    setFromHistory(true);
    setView('workflow');
    setActiveIndex(2);
  };

  const handleLogout = async () => {
    try {
      await signOut();
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const buildFeedbackContext = (): FeedbackContext => ({
    current_view: view,
    workflow_step: view === 'workflow' ? activeIndex : undefined,
    current_run_id: runId || undefined,
    csv_filename: filename || undefined,
    browser_user_agent: navigator.userAgent,
    screen_resolution: `${window.innerWidth}x${window.innerHeight}`,
    app_url: window.location.href,
    timestamp: new Date().toISOString(),
  });

  return (
    <div className="min-h-screen bg-slate-50 font-sans flex flex-col">
      <Toast ref={toast} />

      <AppHeader
        userEmail={user?.email}
        onLogoClick={handleReset}
        onHistoryClick={() => setView('history')}
        onProfileClick={() => setView('profile')}
        onAdminClick={isAdmin ? () => setView('admin') : undefined}
        onFeedbackClick={() => setFeedbackVisible(true)}
        onLogout={handleLogout}
      />

      <FeedbackDialog
        visible={feedbackVisible}
        onHide={() => setFeedbackVisible(false)}
        context={buildFeedbackContext()}
      />

      <main className="flex-grow py-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          {view === 'admin' ? (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
              <AdminLayout onBack={() => setView('workflow')} />
            </Card>
          ) : view === 'history' ? (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
              <HistoryView onSelectRun={handleSelectRun} />
            </Card>
          ) : view === 'profile' ? (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
              <ProfileView onBack={() => setView('workflow')} onSelectRun={handleSelectRun} />
            </Card>
          ) : (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
              <div className="flex flex-col">
                <WorkflowSteps activeIndex={activeIndex} items={WORKFLOW_STEPS} />

                <div className="mt-6 min-h-[400px] relative overflow-hidden">
                  <SwitchTransition mode="out-in">
                    <CSSTransition
                      key={activeIndex}
                      nodeRef={nodeRef}
                      timeout={300}
                      classNames="fade"
                      unmountOnExit
                    >
                      <div ref={nodeRef} className="w-full">
                        {activeIndex === 0 && (
                          <UploadView onUploadComplete={handleUploadComplete} />
                        )}
                        {activeIndex === 1 && (
                          <ProblemView
                            columns={columns}
                            excludedColumns={excludedColumns}
                            nanCounts={nanCounts}
                            onSubmit={handleStartAnalysis}
                          />
                        )}
                        {activeIndex === 2 && (
                          <ResultsView runId={runId} fromHistory={fromHistory} />
                        )}
                      </div>
                    </CSSTransition>
                  </SwitchTransition>
                </div>
              </div>
            </Card>
          )}
        </div>
      </main>

      <AppFooter />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/share/:token" element={<PublicResultsView />} />
        <Route
          path="*"
          element={
            <AuthProvider>
              <AuthGate />
            </AuthProvider>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

function AuthGate() {
  const { user, loading } = useAuth();
  const [showSignUp, setShowSignUp] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <i className="pi pi-spin pi-spinner text-blue-600 text-4xl"></i>
      </div>
    );
  }

  if (!user) {
    if (showForgotPassword) {
      return <ForgotPassword onBackToLogin={() => setShowForgotPassword(false)} />;
    }
    return showSignUp ? (
      <SignUp onSwitchToLogin={() => setShowSignUp(false)} />
    ) : (
      <Login
        onSwitchToSignUp={() => setShowSignUp(true)}
        onForgotPassword={() => setShowForgotPassword(true)}
      />
    );
  }

  return <MainApp />;
}

export default App;
