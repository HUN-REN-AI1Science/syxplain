import { useState, useRef } from 'react';
import { Card } from 'primereact/card';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useAuth } from '@contexts/AuthContext';
import syxplainLogo from '@assets/syxplain_logo.png';

interface SignUpProps {
  onSwitchToLogin: () => void;
}

const SignUp: React.FC<SignUpProps> = ({ onSwitchToLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { signUp } = useAuth();
  const toast = useRef<Toast>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password !== confirmPassword) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Passwords do not match',
      });
      return;
    }

    setLoading(true);

    try {
      await signUp(email, password);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Account created! Please check your email to confirm.',
        life: 5000,
      });
      // Switch to login after success
      setTimeout(() => onSwitchToLogin(), 2000);
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.message || 'Failed to sign up',
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
            Syxplain <span className="text-blue-600">AI</span>
          </h1>
          <p className="text-slate-500 mt-2">Create a new account</p>
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
              toggleMask
              className="w-full"
              inputStyle={{ backgroundColor: '#f1f5f9', width: '100%' }}
              style={{ width: '100%', display: 'flex' }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="confirmPassword" className="font-semibold text-slate-700">
              Confirm Password
            </label>
            <Password
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm your password"
              required
              feedback={false}
              toggleMask
              className="w-full"
              inputStyle={{ backgroundColor: '#f1f5f9', width: '100%' }}
              style={{ width: '100%', display: 'flex' }}
            />
          </div>

          <Button
            type="submit"
            label="Sign Up"
            loading={loading}
            className="w-full mt-4"
            style={{ backgroundColor: '#0052cc', color: 'white', borderColor: '#0052cc', height: '48px', fontSize: '16px' }}
          />

          <div className="text-center mt-4">
            <span className="text-slate-600">Already have an account? </span>
            <button
              type="button"
              onClick={onSwitchToLogin}
              className="text-blue-600 font-semibold hover:underline"
            >
              Sign In
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
};

export default SignUp;
