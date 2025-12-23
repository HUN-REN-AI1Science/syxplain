/**
 * RevokeShareDialog Component
 * Confirmation modal for revoking share links
 */

import React from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';

interface RevokeShareDialogProps {
  visible: boolean;
  onHide: () => void;
  onConfirm: () => void;
}

export const RevokeShareDialog: React.FC<RevokeShareDialogProps> = ({
  visible,
  onHide,
  onConfirm,
}) => (
  <Dialog
    visible={visible}
    onHide={onHide}
    header="Revoke Share Link?"
    className="w-full max-w-md mx-4"
    modal
    footer={
      <div className="flex gap-3 justify-end">
        <Button label="Cancel" className="p-button-text" onClick={onHide} />
        <Button label="Revoke" className="p-button-danger" onClick={onConfirm} />
      </div>
    }
  >
    <p className="text-slate-600">This will remove public access. Anyone with the link will no longer be able to view this result.</p>
  </Dialog>
);

export default RevokeShareDialog;
