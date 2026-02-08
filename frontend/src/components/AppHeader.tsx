/**
 * AppHeader Component
 * Main application header with logo, navigation, and user actions
 */

import React from 'react';
import { Button } from 'primereact/button';
import { Tooltip } from 'primereact/tooltip';
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
}) => (
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
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
          Syxplain <span className="text-blue-600">AI</span>
        </h1>
      </div>
      <div className="flex items-center space-x-2 md:space-x-4">
        <Button
          label="History"
          icon="pi pi-history"
          className="p-button-outlined p-button-sm hidden md:flex"
          onClick={onHistoryClick}
        />
        <Button
          icon="pi pi-history"
          className="p-button-outlined p-button-sm md:hidden"
          onClick={onHistoryClick}
          tooltip="History"
        />
        <Button
          label="Profile"
          icon="pi pi-user"
          className="p-button-outlined p-button-sm hidden md:flex"
          onClick={onProfileClick}
        />
        <Button
          icon="pi pi-user"
          className="p-button-outlined p-button-sm md:hidden"
          onClick={onProfileClick}
          tooltip="Profile"
        />
        {onAdminClick && (
          <>
            <Button
              label="Admin"
              icon="pi pi-cog"
              className="p-button-outlined p-button-sm p-button-warning hidden md:flex"
              onClick={onAdminClick}
            />
            <Button
              icon="pi pi-cog"
              className="p-button-outlined p-button-sm p-button-warning md:hidden"
              onClick={onAdminClick}
              tooltip="Admin"
            />
          </>
        )}
        <Button
          label="Feedback"
          icon="pi pi-comment"
          className="p-button-outlined p-button-sm p-button-help hidden md:flex"
          onClick={onFeedbackClick}
        />
        <Button
          icon="pi pi-comment"
          className="p-button-outlined p-button-sm p-button-help md:hidden"
          onClick={onFeedbackClick}
          tooltip="Feedback"
        />
        <div className="flex items-center space-x-2">
          <Tooltip target=".logout-button" content={userEmail || ''} position="bottom" />
          <Button
            label="Logout"
            icon="pi pi-sign-out"
            className="p-button-outlined p-button-sm p-button-danger logout-button hidden md:flex"
            onClick={onLogout}
          />
          <Button
            icon="pi pi-sign-out"
            className="p-button-outlined p-button-sm p-button-danger logout-button md:hidden"
            onClick={onLogout}
            tooltip="Logout"
          />
        </div>
        <div className="text-sm text-slate-500 font-medium hidden lg:block">
          Automated Symbolic Regression
        </div>
      </div>
    </div>
  </header>
);

export default AppHeader;
