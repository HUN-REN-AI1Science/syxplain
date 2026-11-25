/**
 * AppFooter Component
 * Simple footer with copyright notice and partner logos
 */

import React from 'react';
import aiCampusLogo from '../assets/ai_campus_logo.png';
import hunrenLogo from '../assets/hunren_logo.png';
import { useTheme } from '@contexts/ThemeContext';

export const AppFooter: React.FC = () => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // AI Campus logo: black PNG → blue in light mode, white in dark mode
  const aiCampusFilter = isDark
    ? 'brightness(0) invert(1)'
    : 'invert(19%) sepia(95%) saturate(4700%) hue-rotate(211deg) brightness(82%) contrast(104%)';

  return (
    <footer className="bg-surface border-t border-[var(--color-border)] py-6 mt-auto">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-muted text-sm">
            &copy; {new Date().getFullYear()} Syxplain AI. All rights reserved.
          </div>
          <div className="flex items-center gap-6">
            <a
              href="https://ai.uni-obuda.hu"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:opacity-80 transition-opacity"
            >
              <img
                src={aiCampusLogo}
                alt="AI Campus"
                className="h-8"
                style={{ filter: aiCampusFilter }}
              />
            </a>
            <a
              href="https://www.ai1science.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:opacity-80 transition-opacity"
            >
              <img
                src={hunrenLogo}
                alt="HUNREN"
                className="h-8"
                style={isDark ? { filter: 'brightness(0) invert(1)' } : undefined}
              />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default AppFooter;
