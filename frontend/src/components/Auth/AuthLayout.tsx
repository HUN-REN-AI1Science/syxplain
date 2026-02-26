import React from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import syxplainLogo from '@assets/syxplain_logo.png';

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  toastRef?: React.RefObject<Toast>;
}

export const AuthLayout: React.FC<AuthLayoutProps> = ({ title, subtitle, children, toastRef }) => (
  <div className="min-h-screen bg-page flex items-center justify-center p-4">
    {toastRef && <Toast ref={toastRef} />}

    <Card className="w-full max-w-md shadow-xl">
      <div className="flex flex-col items-center mb-6">
        <div className="w-[72px] h-[72px] rounded-full bg-brand-500 flex items-center justify-center overflow-hidden mb-4">
          <img src={syxplainLogo} alt="Syxplain Logo" className="w-12 h-12 object-contain" />
        </div>
        <h1 className="font-heading text-3xl font-bold text-primary">
          {title.includes('AI') ? (
            <>
              Syxplain <span className="text-brand-500">AI</span>
            </>
          ) : (
            title
          )}
        </h1>
        <p className="text-secondary mt-2">{subtitle}</p>
      </div>

      {children}
    </Card>
  </div>
);

export default AuthLayout;
