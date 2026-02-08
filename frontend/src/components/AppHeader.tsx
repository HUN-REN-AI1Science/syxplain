/**
 * AppHeader Component
 * Main application header with logo, navigation, and user actions
 */

import React, { useRef } from 'react';
import { Button } from 'primereact/button';
import { Menu } from 'primereact/menu';
import { Tooltip } from 'primereact/tooltip';
import type { MenuItem } from 'primereact/menuitem';
import syxplainLogo from '@assets/syxplain_logo.png';

interface AppHeaderProps {
  userEmail?: string;
  onLogoClick: () => void;
  onHistoryClick: () => void;
  onProfileClick: () => void;
  onAdminClick?: () => void;
  onFeedbackClick: () => void;
  onLogout: () => void;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  userEmail,
  onLogoClick,
  onHistoryClick,
  onProfileClick,
  onAdminClick,
  onFeedbackClick,
  onLogout,
}) => {
  const mobileMenu = useRef<Menu>(null);

  const mobileMenuItems: MenuItem[] = [
    { label: 'History', icon: 'pi pi-history', command: onHistoryClick },
    { label: 'Profile', icon: 'pi pi-user', command: onProfileClick },
    ...(onAdminClick ? [{ label: 'Admin', icon: 'pi pi-cog', command: onAdminClick }] : []),
    { label: 'Feedback', icon: 'pi pi-comment', command: onFeedbackClick },
    { separator: true },
    { label: 'Logout', icon: 'pi pi-sign-out', className: 'text-red-600', command: onLogout },
  ];

  return (
    <header className="bg-white shadow-sm border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div
          className="flex items-center space-x-3 cursor-pointer transition-opacity"
          onClick={onLogoClick}
        >
          <div
            className="rounded-full flex-shrink-0 flex items-center justify-center overflow-hidden"
            style={{ backgroundColor: '#0052cc', width: '40px', height: '40px' }}
          >
            <img src={syxplainLogo} alt="Syxplain Logo" className="w-7 h-7 object-contain" />
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight whitespace-nowrap">
            Syxplain <span className="text-blue-600">AI</span>
          </h1>
        </div>

        {/* Desktop navigation */}
        <div className="hidden md:flex items-center space-x-4">
          <Button
            label="History"
            icon="pi pi-history"
            className="p-button-outlined p-button-sm"
            onClick={onHistoryClick}
          />
          <Button
            label="Profile"
            icon="pi pi-user"
            className="p-button-outlined p-button-sm"
            onClick={onProfileClick}
          />
          {onAdminClick && (
            <Button
              label="Admin"
              icon="pi pi-cog"
              className="p-button-outlined p-button-sm p-button-warning"
              onClick={onAdminClick}
            />
          )}
          <Button
            label="Feedback"
            icon="pi pi-comment"
            className="p-button-outlined p-button-sm p-button-help"
            onClick={onFeedbackClick}
          />
          <div className="flex items-center space-x-2">
            <Tooltip target=".logout-button" content={userEmail || ''} position="bottom" />
            <Button
              label="Logout"
              icon="pi pi-sign-out"
              className="p-button-outlined p-button-sm p-button-danger logout-button"
              onClick={onLogout}
            />
          </div>
          <div className="text-sm text-slate-500 font-medium hidden lg:block">
            Automated Symbolic Regression
          </div>
        </div>

        {/* Mobile hamburger menu */}
        <div className="md:hidden">
          <Menu model={mobileMenuItems} popup ref={mobileMenu} />
          <Button
            icon="pi pi-bars"
            className="p-button-text p-button-sm"
            onClick={(e) => mobileMenu.current?.toggle(e)}
            aria-label="Menu"
          />
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
