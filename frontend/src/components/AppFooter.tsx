/**
 * AppFooter Component
 * Simple footer with copyright notice
 */

import React from 'react';

export const AppFooter: React.FC = () => (
  <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
    <div className="max-w-7xl mx-auto px-4 text-center text-slate-400 text-sm">
      &copy; {new Date().getFullYear()} Syxplain AI. All rights reserved.
    </div>
  </footer>
);

export default AppFooter;
