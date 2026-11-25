/**
 * PublicHeader Component
 * Simplified header for public share view (no user menu items)
 */

import React from 'react';
import syxplainLogo from '@assets/syxplain_logo.png';

const PublicHeader: React.FC = () => {
  return (
    <header className="bg-surface shadow-sm border-b border-[var(--color-border)] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-full bg-brand-500 flex-shrink-0 flex items-center justify-center overflow-hidden">
            <img src={syxplainLogo} alt="Syxplain Logo" className="w-7 h-7 object-contain" />
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-primary tracking-tight">
            Syxplain <span className="text-brand-500">AI</span>
          </h1>
        </div>
        <div className="flex items-center space-x-2">
          <span className="px-3 py-1 bg-brand-100 text-brand-500 text-sm font-medium rounded-full">
            <i className="pi pi-globe mr-1" />
            Shared Results
          </span>
        </div>
      </div>
    </header>
  );
};

export default PublicHeader;
