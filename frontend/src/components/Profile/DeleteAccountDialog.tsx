/**
 * DeleteAccountDialog Component
 * Confirmation modal for account deletion
 */

import React from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';

interface DeleteAccountDialogProps {
  visible: boolean;
  onHide: () => void;
  onConfirm: () => void;
}

export const DeleteAccountDialog: React.FC<DeleteAccountDialogProps> = ({
  visible,
  onHide,
  onConfirm,
}) => {
  const footer = (
    <div className="flex flex-col sm:flex-row gap-3 sm:justify-end pt-4 border-t border-slate-200 mt-4">
      <Button
        label="Cancel"
        icon="pi pi-times"
        onClick={onHide}
        className="w-full sm:w-auto"
        style={{
          backgroundColor: '#f1f5f9',
          color: '#334155',
          border: '1px solid #cbd5e1',
          borderRadius: '8px',
          padding: '0.75rem 1.5rem',
          fontWeight: 500,
        }}
      />
      <Button
        label="Delete My Account"
        icon="pi pi-trash"
        onClick={onConfirm}
        className="w-full sm:w-auto"
        style={{
          backgroundColor: '#dc2626',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          padding: '0.75rem 1.5rem',
          fontWeight: 500,
        }}
      />
    </div>
  );

  return (
    <Dialog
      visible={visible}
      onHide={onHide}
      header={
        <div className="flex items-center gap-3">
          <i className="pi pi-exclamation-triangle text-red-500 text-2xl"></i>
          <span>Delete Account Permanently?</span>
        </div>
      }
      footer={footer}
      className="w-full max-w-lg mx-4"
      modal
      draggable={false}
    >
      <div className="py-4">
        <p className="text-slate-700 mb-4">
          This action <span className="font-semibold text-red-600">cannot be undone</span>. Deleting
          your account will permanently remove:
        </p>
        <ul className="space-y-2 mb-4">
          <li className="flex items-center gap-2 text-slate-600">
            <i className="pi pi-check-circle text-red-400"></i>
            All your analysis runs and results
          </li>
          <li className="flex items-center gap-2 text-slate-600">
            <i className="pi pi-check-circle text-red-400"></i>
            All uploaded files and datasets
          </li>
          <li className="flex items-center gap-2 text-slate-600">
            <i className="pi pi-check-circle text-red-400"></i>
            Your account and login credentials
          </li>
        </ul>
        <p className="text-slate-700 font-medium">
          You will need to register again to use Syxplain.
        </p>
      </div>
    </Dialog>
  );
};

export default DeleteAccountDialog;
