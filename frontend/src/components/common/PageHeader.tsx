/**
 * PageHeader Component
 * Consistent page header pattern
 */

import React from 'react';

interface PageHeaderProps {
  /** Page title */
  title: string;
  /** Optional subtitle */
  subtitle?: string;
  /** Optional right-side content */
  actions?: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  actions,
  className = '',
}) => (
  <div className={`flex flex-col md:flex-row justify-between items-start md:items-center mb-6 ${className}`}>
    <div>
      <h2 className="text-2xl font-bold text-slate-800 mb-2">{title}</h2>
      {subtitle && <p className="text-slate-500">{subtitle}</p>}
    </div>
    {actions && (
      <div className="mt-4 md:mt-0">{actions}</div>
    )}
  </div>
);

export default PageHeader;
