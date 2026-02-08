import { useState, useRef } from 'react';
import { InputText } from 'primereact/inputtext';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useAuth } from '@contexts/AuthContext';
import { AuthLayout } from '@components/Auth';

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
      setTimeout(() => onBackToLogin(), 3000);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error instanceof Error ? error.message : 'Failed to send reset email',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Forgot Password"
      subtitle="Enter your email to reset your password"
      toastRef={toast}
    >
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
          style={{
            backgroundColor: '#0052cc',
            color: 'white',
            borderColor: '#0052cc',
            height: '48px',
            fontSize: '16px',
          }}
          pt={{
            loadingIcon: { className: 'ml-2' },
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
    </AuthLayout>
  );
};

export default ForgotPassword;
