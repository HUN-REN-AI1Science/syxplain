import { useState, useRef } from 'react';
import FileUpload from './FileUpload';
import ProblemForm from './ProblemForm';
import ResultsView from './ResultsView';
import HistoryView from './HistoryView';
import Login from './pages/Login';
import SignUp from './pages/SignUp';
import ForgotPassword from './pages/ForgotPassword';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import api from './api';
import { Steps } from 'primereact/steps';
import { Toast } from 'primereact/toast';
import { Card } from 'primereact/card';
import { Button } from 'primereact/button';
import { Tooltip } from 'primereact/tooltip';
import { SwitchTransition, CSSTransition } from 'react-transition-group';

function MainApp() {
  const [view, setView] = useState<'workflow' | 'history'>('workflow');
  const [activeIndex, setActiveIndex] = useState(0);
  const [filename, setFilename] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const toast = useRef<Toast>(null);
  const nodeRef = useRef(null);
  const { signOut, user } = useAuth();

  const handleUploadComplete = (fname: string, cols: string[]) => {
    setFilename(fname);
    setColumns(cols);
    setActiveIndex(1);
  };

  const handleStartAnalysis = async (problemData: any) => {
    // Navigate to results page immediately to show loading screen
    setActiveIndex(2);

    try {
      const response = await api.post('/run', {
        problem_description: problemData,
        csv_filename: filename
      });
      setRunId(response.data.run_id);
    } catch (e) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to start analysis' });
      console.error(e);
      // Go back to problem form on error
      setActiveIndex(1);
    }
  };

  const items = [
    { label: 'Upload Data' },
    { label: 'Define Problem' },
    { label: 'Analysis Results' }
  ];

  const handleReset = () => {
    setView('workflow');
    setActiveIndex(0);
    setFilename(null);
    setColumns([]);
    setRunId(null);
  };

  const handleSelectRun = (selectedRunId: string) => {
    setRunId(selectedRunId);
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

  return (
    <div className="min-h-screen bg-slate-50 font-sans flex flex-col">
      <Toast ref={toast} />

      {/* Modern Header */}
      <header className="bg-white shadow-sm border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div
            className="flex items-center space-x-3 cursor-pointer transition-opacity"
            onClick={handleReset}
          >
            <div className="bg-blue-600 p-2 rounded-lg flex-shrink-0">
              <i className="pi pi-bolt text-white text-lg md:text-xl"></i>
            </div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
              Syxplain <span className="text-blue-600">AI</span>
            </h1>
          </div>
          <div className="flex items-center space-x-2 md:space-x-4">
            <Button
              label="History"
              icon="pi pi-history"
              className="p-button-outlined p-button-sm hidden md:flex"
              onClick={() => setView('history')}
            />
            <Button
              icon="pi pi-history"
              className="p-button-outlined p-button-sm md:hidden"
              onClick={() => setView('history')}
              tooltip="History"
            />
            <div className="flex items-center space-x-2">
              <Tooltip target=".logout-button" content={user?.email || ''} position="bottom" />
              <Button
                label="Logout"
                icon="pi pi-sign-out"
                className="p-button-outlined p-button-sm p-button-danger logout-button hidden md:flex"
                onClick={handleLogout}
              />
              <Button
                icon="pi pi-sign-out"
                className="p-button-outlined p-button-sm p-button-danger logout-button md:hidden"
                onClick={handleLogout}
                tooltip="Logout"
              />
            </div>
            <div className="text-sm text-slate-500 font-medium hidden lg:block">
              Automated Symbolic Regression
            </div>
          </div>
        </div>
      </header>

      <main className="flex-grow py-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          {view === 'history' ? (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
              <HistoryView onSelectRun={handleSelectRun} />
            </Card>
          ) : (
            <Card className="shadow-xl border-round-2xl overflow-hidden border-none">
                <div className="flex flex-col">
                  <div className="px-4 pt-4">
                    <div className="hidden md:block">
                      <Steps model={items} activeIndex={activeIndex} onSelect={(e: any) => setActiveIndex(e.index)} readOnly={true} className="mb-8 custom-steps" />
                    </div>
                    <div className="md:hidden mb-6 text-center">
                      <span className="text-sm font-semibold text-blue-600 uppercase tracking-wider">Step {activeIndex + 1} of {items.length}</span>
                      <h2 className="text-xl font-bold text-slate-800 mt-1">{items[activeIndex].label}</h2>
                      <div className="w-full bg-slate-200 h-1.5 mt-3 rounded-full overflow-hidden">
                        <div className="bg-blue-600 h-full transition-all duration-300" style={{ width: `${((activeIndex + 1) / items.length) * 100}%` }}></div>
                      </div>
                    </div>
                  </div>

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
                          {activeIndex === 0 && <FileUpload onUploadComplete={handleUploadComplete} />}
                          {activeIndex === 1 && <ProblemForm columns={columns} onSubmit={handleStartAnalysis} />}
                          {activeIndex === 2 && runId && <ResultsView runId={runId} />}
                        </div>
                      </CSSTransition>
                    </SwitchTransition>
                  </div>
                </div>
            </Card>
          )}
        </div>
      </main>

      <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 text-center text-slate-400 text-sm">
          &copy; {new Date().getFullYear()} Syxplain AI. All rights reserved.
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
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
