import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { Button } from 'primereact/button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  subtitle,
  actionLabel,
  onAction,
}) => (
  <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
    <div className="w-16 h-16 rounded-full bg-surface-alt flex items-center justify-center mb-5">
      <Icon className="w-8 h-8 text-muted" />
    </div>
    <h3 className="font-heading text-xl font-semibold text-primary mb-2">{title}</h3>
    {subtitle && <p className="text-secondary text-sm max-w-sm mb-6">{subtitle}</p>}
    {actionLabel && onAction && (
      <Button label={actionLabel} icon="pi pi-plus" className="p-button-outlined" onClick={onAction} />
    )}
  </div>
);

export default EmptyState;
