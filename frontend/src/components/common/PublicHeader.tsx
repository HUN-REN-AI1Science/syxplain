/**
 * PublicHeader Component
 * Simplified header for public share view (no user menu items)
 */

import React from 'react';
import syxplainLogo from '@assets/syxplain_logo.png';

const PublicHeader: React.FC = () => {
  return (
    <header className="bg-white shadow-sm border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div
            className="rounded-full flex-shrink-0 flex items-center justify-center overflow-hidden"
            style={{ backgroundColor: '#0052cc', width: '40px', height: '40px' }}
          >
            <img src={syxplainLogo} alt="Syxplain Logo" className="w-7 h-7 object-contain" />
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
            Syxplain <span className="text-blue-600">AI</span>
          </h1>
        </div>
        <div className="flex items-center space-x-2">
          <span className="px-3 py-1 bg-blue-100 text-blue-700 text-sm font-medium rounded-full">
            <i className="pi pi-globe mr-1"></i>
            Shared Results
          </span>
        </div>
      </div>
    </header>
  );
};

export default PublicHeader;
