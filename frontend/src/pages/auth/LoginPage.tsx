import { Button } from 'primereact/button';
import { AuthLayout } from '@components/Auth';
import { useAuth } from '@contexts/AuthContext';

const enableMicrosoftSSO = import.meta.env.VITE_ENABLE_MICROSOFT_SSO === 'true';

const LoginPage: React.FC = () => {
  const { signIn, signInWithSSO } = useAuth();

  return (
    <AuthLayout title="Syxplain AI" subtitle="Sign in to continue">
      <div className="flex flex-col gap-4">
        <Button
          label="Sign In with Email"
          onClick={() => signIn()}
          className="w-full"
          style={{
            backgroundColor: '#0052cc',
            color: 'white',
            borderColor: '#0052cc',
            height: '48px',
            fontSize: '16px',
          }}
        />

        {enableMicrosoftSSO && (
          <>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-slate-200"></div>
              <span className="text-slate-400 text-sm">or</span>
              <div className="flex-1 h-px bg-slate-200"></div>
            </div>

            <Button
              label="Sign In with Microsoft"
              icon="pi pi-microsoft"
              onClick={() => signInWithSSO()}
              className="w-full"
              outlined
              style={{
                height: '48px',
                fontSize: '16px',
                borderColor: '#e2e8f0',
                color: '#334155',
              }}
            />
          </>
        )}
      </div>
    </AuthLayout>
  );
};

export default LoginPage;
