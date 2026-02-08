/**
 * AppFooter Component
 * Simple footer with copyright notice and partner logos
 */

import React from 'react';
import aiCampusLogo from '../assets/ai_campus_logo.png';
import hunrenLogo from '../assets/hunren_logo.png';

export const AppFooter: React.FC = () => (
  <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
    <div className="max-w-7xl mx-auto px-4">
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="text-slate-400 text-sm">
          &copy; {new Date().getFullYear()} Syxplain AI. All rights reserved.
        </div>
        <div className="flex items-center gap-6">
          <a
            href="https://ai.uni-obuda.hu"
            target="_blank"
            rel="noopener noreferrer"
            className="opacity-70 hover:opacity-100 transition-opacity"
          >
            <img
              src={aiCampusLogo}
              alt="AI Campus"
              className="h-8"
              style={{
                filter: 'invert(35%) sepia(85%) saturate(1500%) hue-rotate(200deg) brightness(95%)',
              }}
            />
          </a>
          <a
            href="https://www.ai1science.com"
            target="_blank"
            rel="noopener noreferrer"
            className="opacity-70 hover:opacity-100 transition-opacity"
          >
            <img src={hunrenLogo} alt="HUNREN" className="h-8" />
          </a>
        </div>
      </div>
    </div>
  </footer>
);

export default AppFooter;
