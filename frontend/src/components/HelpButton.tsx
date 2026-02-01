/**
 * HelpButton Component
 * Reusable help button that displays contextual help in a dialog
 * Matches the existing style used in JsonConfigUpload
 */

import React, { useState } from 'react';
import { Button } from 'primereact/button';
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
      <Button
        icon="pi pi-question-circle"
        className={`p-button-rounded p-button-text p-button-sm ${className}`}
        onClick={() => setVisible(true)}
        aria-label={`Help: ${title}`}
      />

      <Dialog
        visible={visible}
        onHide={() => setVisible(false)}
        header={title}
        className="help-dialog w-[90vw] max-w-[600px]"
        dismissableMask
        draggable={false}
        resizable={false}
      >
        <div className="help-content text-slate-600 leading-relaxed pt-2">{children}</div>
      </Dialog>
    </>
  );
};

export default HelpButton;
