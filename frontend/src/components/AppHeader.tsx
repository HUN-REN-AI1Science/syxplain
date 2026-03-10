/**
 * AppHeader Component
 * Main application header with logo and avatar dropdown navigation
 */

import React, { useEffect, useRef } from 'react';
import { Menu } from 'primereact/menu';
import type { MenuItem } from 'primereact/menuitem';
import { ChevronDown } from 'lucide-react';
import syxplainLogo from '@assets/syxplain_logo.png';
import UserAvatar from '@components/UserAvatar';
import { useTheme } from '@contexts/ThemeContext';

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
  const userMenu = useRef<Menu>(null);
  const { theme, toggleTheme } = useTheme();

  // Close menu on scroll so it doesn't drift from the trigger button
  useEffect(() => {
    const hideMenu = () =>
      userMenu.current?.hide(new Event('scroll') as unknown as React.SyntheticEvent);
    window.addEventListener('scroll', hideMenu, { passive: true });
    return () => window.removeEventListener('scroll', hideMenu);
  }, []);

  const themeLabel = theme === 'light' ? 'Dark Mode' : 'Light Mode';
  const themeIcon = theme === 'light' ? 'pi pi-moon' : 'pi pi-sun';

  const menuItems: MenuItem[] = [
    { label: 'History', icon: 'pi pi-history', command: onHistoryClick },
    { label: 'Profile', icon: 'pi pi-user', command: onProfileClick },
    ...(onAdminClick ? [{ label: 'Admin', icon: 'pi pi-cog', command: onAdminClick }] : []),
    { label: 'Feedback', icon: 'pi pi-comment', command: onFeedbackClick },
    {
      label: 'API Docs',
      icon: 'pi pi-book',
      command: () => window.open('/docs', '_blank'),
    },
    { separator: true },
    { label: themeLabel, icon: themeIcon, command: toggleTheme },
    { separator: true },
    { label: 'Logout', icon: 'pi pi-sign-out', className: 'text-red-600', command: onLogout },
  ];

  return (
    <header className="bg-surface shadow-sm border-b border-[var(--color-border)] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div
          className="flex items-center space-x-3 cursor-pointer transition-opacity hover:opacity-80"
          onClick={onLogoClick}
        >
          <div className="w-10 h-10 rounded-full bg-brand-500 flex-shrink-0 flex items-center justify-center overflow-hidden">
            <img src={syxplainLogo} alt="Syxplain Logo" className="w-7 h-7 object-contain" />
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-primary tracking-tight whitespace-nowrap">
            Syxplain <span className="text-brand-500">AI</span>
          </h1>
        </div>

        {/* User avatar dropdown */}
        <div>
          <Menu model={menuItems} popup ref={userMenu} />
          <button
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-alt transition-colors"
            onClick={(e) => userMenu.current?.toggle(e)}
            aria-label="User menu"
          >
            <UserAvatar email={userEmail} size="sm" />
            <span className="hidden sm:block text-sm font-medium text-secondary max-w-[160px] truncate">
              {userEmail}
            </span>
            <ChevronDown className="w-4 h-4 text-muted" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
