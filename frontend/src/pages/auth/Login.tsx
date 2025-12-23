import { useState, useRef } from 'react';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useAuth } from '@contexts/AuthContext';
import { AuthLayout } from '@components/Auth';

interface LoginProps {
  onSwitchToSignUp: () => void;
  onForgotPassword: () => void;
}

const Login: React.FC<LoginProps> = ({ onSwitchToSignUp, onForgotPassword }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { signIn } = useAuth();
  const toast = useRef<Toast>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await signIn(email, password);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Logged in successfully',
      });
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.message || 'Failed to log in',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Syxplain AI" subtitle="Sign in to your account" toastRef={toast}>
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

        <div className="flex flex-col gap-2">
          <label htmlFor="password" className="font-semibold text-slate-700">
            Password
          </label>
          <Password
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            required
            feedback={false}
            toggleMask
            className="w-full"
            inputStyle={{ backgroundColor: '#f1f5f9', width: '100%' }}
            style={{ width: '100%', display: 'flex' }}
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onForgotPassword}
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline font-medium"
            >
              Forgot Password?
            </button>
          </div>
        </div>

        <Button
          type="submit"
          label="Sign In"
          loading={loading}
          className="w-full mt-4"
          style={{ backgroundColor: '#0052cc', color: 'white', borderColor: '#0052cc', height: '48px', fontSize: '16px' }}
          pt={{
            loadingIcon: { className: 'ml-2' }
          }}
        />

        <div className="text-center mt-4">
          <span className="text-slate-600">Don't have an account? </span>
          <button
            type="button"
            onClick={onSwitchToSignUp}
            className="text-blue-600 font-semibold hover:underline"
          >
            Sign Up
          </button>
        </div>
      </form>
    </AuthLayout>
  );
};

export default Login;
