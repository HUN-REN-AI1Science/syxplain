import { useState, useRef, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import { WebStorageStateStore } from 'oidc-client-ts';
import UploadView from '@pages/UploadView';
import ProblemView from '@pages/ProblemView';
import ResultsView from '@pages/results/ResultsView';
import HistoryView from '@pages/HistoryView';
import ProfileView from '@pages/ProfileView';
import HelpView from '@pages/HelpView';
import AdminLayout from '@pages/admin/AdminLayout';
import PublicResultsView from '@pages/results/PublicResultsView';
import { AuthProvider, useAuth } from '@contexts/AuthContext';
import { ThemeProvider } from '@contexts/ThemeContext';
import { NavigationContext } from '@contexts/NavigationContext';
import { runsService } from '@services/api';
import { Toast } from 'primereact/toast';
import { Card } from 'primereact/card';
import { SwitchTransition, CSSTransition } from 'react-transition-group';
import AppHeader from '@components/AppHeader';
import AppFooter from '@components/AppFooter';
import WorkflowSteps from '@components/WorkflowSteps';
import FeedbackDialog from '@components/FeedbackDialog';
import type { FeedbackContext, ProgressPhase, UserApiKeys } from '@/types';

const WORKFLOW_STEPS = [
  { label: 'Upload Data' },
  { label: 'Define Problem' },
  { label: 'Analysis Results' },
];

// OIDC configuration for Keycloak
const keycloakUrl = import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8080/keycloak';
const keycloakRealm = import.meta.env.VITE_KEYCLOAK_REALM || 'syxplain';
const keycloakClientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'syxplain-frontend';

const oidcConfig = {
  authority: `${keycloakUrl}/realms/${keycloakRealm}`,
  client_id: keycloakClientId,
  redirect_uri: window.location.origin + '/',
  post_logout_redirect_uri: window.location.origin + '/',
  response_type: 'code',
  scope: 'openid email profile',
  automaticSilentRenew: true,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
};

function MainApp() {
  const [view, setView] = useState<'workflow' | 'history' | 'profile' | 'admin' | 'help'>('workflow');
  const [helpAnchor, setHelpAnchor] = useState<string | undefined>(undefined);
  const [activeIndex, setActiveIndex] = useState(0);
  const [filename, setFilename] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [excludedColumns, setExcludedColumns] = useState<string[]>([]);
  const [nanCounts, setNanCounts] = useState<Record<string, number>>({});
  const [runId, setRunId] = useState<string | null>(null);
  const [progressPhases, setProgressPhases] = useState<ProgressPhase[]>([]);
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

  const handleStartAnalysis = async (problemData: Record<string, unknown>) => {
    setFromHistory(false);
    setActiveIndex(2);

    try {
      const { analysis_type, deep_research_model, user_api_keys, ...problemDescription } =
        problemData;
      const response = await runsService.create({
        problem_description: problemDescription,
        csv_filename: filename!,
        analysis_type: (analysis_type as string) || 'quick',
        deep_research_model: (deep_research_model as string | null) || null,
        user_api_keys: user_api_keys as UserApiKeys | undefined,
      });
      setRunId(response.data.run_id);
      if (response.data.progress_phases) {
        setProgressPhases(response.data.progress_phases);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      const errorMessage = err.response?.data?.detail || 'Failed to start analysis';
      toast.current?.show({ severity: 'error', summary: 'Error', detail: errorMessage });
      console.error(e);
      setActiveIndex(1);
    }
  };

  const navigateTo = (newView: string, anchor?: string) => {
    setHelpAnchor(anchor);
    setView(newView as 'workflow' | 'history' | 'profile' | 'admin' | 'help');
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
    <NavigationContext.Provider value={{ navigateTo }}>
    <div className="min-h-screen bg-page font-body flex flex-col">
      <a href="#main-content" className="skip-to-content">
        Skip to main content
      </a>

      <Toast ref={toast} />

      <AppHeader
        userEmail={user?.email}
        onLogoClick={handleReset}
        onHistoryClick={() => setView('history')}
        onProfileClick={() => setView('profile')}
        onAdminClick={isAdmin ? () => setView('admin') : undefined}
        onHelpClick={() => setView('help')}
        onFeedbackClick={() => setFeedbackVisible(true)}
        onLogout={handleLogout}
      />

      <FeedbackDialog
        visible={feedbackVisible}
        onHide={() => setFeedbackVisible(false)}
        context={buildFeedbackContext()}
      />

      <main id="main-content" className="flex-grow py-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          {view === 'help' ? (
            <Card className="shadow-card border-round-2xl overflow-hidden border-none">
              <HelpView onBack={() => setView('workflow')} anchor={helpAnchor} />
            </Card>
          ) : view === 'admin' ? (
            <Card className="shadow-card border-round-2xl overflow-hidden border-none">
              <AdminLayout onBack={() => setView('workflow')} />
            </Card>
          ) : view === 'history' ? (
            <Card className="shadow-card border-round-2xl overflow-hidden border-none">
              <HistoryView onSelectRun={handleSelectRun} />
            </Card>
          ) : view === 'profile' ? (
            <Card className="shadow-card border-round-2xl overflow-hidden border-none">
              <ProfileView onBack={() => setView('workflow')} onSelectRun={handleSelectRun} />
            </Card>
          ) : (
            <Card className="shadow-card border-round-2xl overflow-hidden border-none">
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
                          <ResultsView
                            runId={runId}
                            fromHistory={fromHistory}
                            initialProgressPhases={progressPhases}
                          />
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
    </NavigationContext.Provider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <Routes>
          <Route path="/share/:token" element={<PublicResultsView />} />
          <Route
            path="*"
            element={
              <OidcProvider {...oidcConfig}>
                <AuthProvider>
                  <AuthGate />
                </AuthProvider>
              </OidcProvider>
            }
          />
        </Routes>
      </ThemeProvider>
    </BrowserRouter>
  );
}

function AuthGate() {
  const { user, loading, signIn } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      signIn();
    }
  }, [loading, user, signIn]);

  if (loading || !user) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center">
        <i className="pi pi-spin pi-spinner text-brand-500 text-4xl" />
      </div>
    );
  }

  return <MainApp />;
}

export default App;
