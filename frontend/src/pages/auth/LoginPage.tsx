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
          className="w-full h-12 text-base bg-brand-500 border-brand-500 text-white hover:bg-brand-600"
        />

        {enableMicrosoftSSO && (
          <>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-[var(--color-border)]" />
              <span className="text-muted text-sm">or</span>
              <div className="flex-1 h-px bg-[var(--color-border)]" />
            </div>

            <Button
              label="Sign In with Microsoft"
              icon="pi pi-microsoft"
              onClick={() => signInWithSSO()}
              className="w-full h-12 text-base"
              outlined
              style={{
                borderColor: 'var(--color-border)',
                color: 'var(--color-text-secondary)',
              }}
            />
          </>
        )}
      </div>
    </AuthLayout>
  );
};

export default LoginPage;
