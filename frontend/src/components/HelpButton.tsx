/**
 * HelpButton Component
 * Inline help icon that opens a contextual help dialog.
 * Renders as a lightweight inline trigger — not a PrimeReact Button —
 * so it sits tight against adjacent text without extra spacing.
 */

import React, { useState } from 'react';
import { Dialog } from 'primereact/dialog';

interface HelpButtonProps {
  /** Dialog title */
  title: string;
  /** Help content to display (can be JSX) */
  children: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
}

export const HelpButton: React.FC<HelpButtonProps> = ({ title, children, className = '' }) => {
  const [visible, setVisible] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setVisible(true)}
        aria-label={`Help: ${title}`}
        className={`inline-flex items-center justify-center w-5 h-5 shrink-0
          text-muted hover:text-brand-500 rounded-full
          transition-colors duration-fast cursor-pointer
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200
          ${className}`}
      >
        <i className="pi pi-question-circle text-sm" />
      </button>

      <Dialog
        visible={visible}
        onHide={() => setVisible(false)}
        header={title}
        className="help-dialog w-[90vw] max-w-[600px]"
        dismissableMask
        draggable={false}
        resizable={false}
      >
        <div className="help-content text-secondary leading-relaxed pt-2">{children}</div>
      </Dialog>
    </>
  );
};

export default HelpButton;
