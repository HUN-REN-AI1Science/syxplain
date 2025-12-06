import { useState, useRef } from 'react';
import { Card } from 'primereact/card';
import { InputText } from 'primereact/inputtext';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useAuth } from '../contexts/AuthContext';
import syxplainLogo from '../assets/syxplain_logo.png';

interface ForgotPasswordProps {
  onBackToLogin: () => void;
}

const ForgotPassword: React.FC<ForgotPasswordProps> = ({ onBackToLogin }) => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const { resetPassword } = useAuth();
  const toast = useRef<Toast>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await resetPassword(email);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Password reset email sent. Please check your inbox.',
      });
      // Optionally redirect back to login after a delay
      setTimeout(() => {
        onBackToLogin();
      }, 3000);
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.message || 'Failed to send reset email',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <Toast ref={toast} />

      <Card className="w-full max-w-md shadow-xl">
        <div className="flex flex-col items-center mb-6">
          <div
            className="rounded-full flex items-center justify-center overflow-hidden mb-4"
            style={{ backgroundColor: '#0052cc', width: '72px', height: '72px' }}
          >
            <img src={syxplainLogo} alt="Syxplain Logo" className="w-12 h-12 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900">
            Forgot Password
          </h1>
          <p className="text-slate-500 mt-2">Enter your email to reset your password</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="email" className="font-semibold text-slate-700">
              Email
            </label>
            <InputText
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              className="w-full"
              style={{ backgroundColor: '#f1f5f9', width: '100%' }}
            />
          </div>

          <Button
            type="submit"
            label="Send Reset Link"
            loading={loading}
            className="w-full mt-4"
            style={{ backgroundColor: '#0052cc', color: 'white', borderColor: '#0052cc', height: '48px', fontSize: '16px' }}
            pt={{
                loadingIcon: { className: 'ml-2' }
            }}
          />

          <div className="text-center mt-4">
            <button
              type="button"
              onClick={onBackToLogin}
              className="text-slate-600 hover:text-slate-800 font-medium flex items-center justify-center gap-2 mx-auto transition-colors"
            >
              <i className="pi pi-arrow-left text-sm"></i>
              Back to Login
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
};

export default ForgotPassword;
