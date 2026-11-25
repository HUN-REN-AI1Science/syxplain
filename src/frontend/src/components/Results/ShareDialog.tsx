/**
 * ShareDialog Component
 * Dialog for managing public share links for run results
 */

import React, { useState, useRef } from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Toast } from 'primereact/toast';
import { sharingService } from '@services/api';

interface ShareDialogProps {
  visible: boolean;
  onHide: () => void;
  runId: string;
  currentShareToken: string | null;
  onShareStatusChange: (token: string | null) => void;
}

const ShareDialog: React.FC<ShareDialogProps> = ({
  visible,
  onHide,
  runId,
  currentShareToken,
  onShareStatusChange,
}) => {
  const [loading, setLoading] = useState(false);
  const [shareToken, setShareToken] = useState<string | null>(currentShareToken);
  const toast = useRef<Toast>(null);

  // Update local state when prop changes
  React.useEffect(() => {
    setShareToken(currentShareToken);
  }, [currentShareToken]);

  const getShareUrl = () => {
    if (!shareToken) return '';
    return `${window.location.origin}/share/${shareToken}`;
  };

  const handleCreateShareLink = async () => {
    setLoading(true);
    try {
      const response = await sharingService.createShareLink(runId);
      setShareToken(response.data.share_token);
      onShareStatusChange(response.data.share_token);
      toast.current?.show({
        severity: 'success',
        summary: 'Link Created',
        detail: 'Public share link has been created',
      });
    } catch (e) {
      console.error('Failed to create share link:', e);
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to create share link',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeShareLink = async () => {
    setLoading(true);
    try {
      await sharingService.revokeShareLink(runId);
      setShareToken(null);
      onShareStatusChange(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Link Revoked',
        detail: 'Public share link has been removed',
      });
    } catch (e) {
      console.error('Failed to revoke share link:', e);
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to revoke share link',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(getShareUrl());
      toast.current?.show({
        severity: 'success',
        summary: 'Copied',
        detail: 'Link copied to clipboard',
        life: 2000,
      });
    } catch (e) {
      console.error('Failed to copy link:', e);
    }
  };

  return (
    <>
      <Toast ref={toast} />
      <Dialog
        visible={visible}
        onHide={onHide}
        header={
          <div className="flex items-center gap-3">
            <i className="pi pi-share-alt text-brand-500 text-xl"></i>
            <span>Share Results</span>
          </div>
        }
        className="w-full max-w-lg mx-4"
        modal
        draggable={false}
      >
        <div className="py-4">
          {!shareToken ? (
            // Not shared - show create button
            <div className="space-y-5">
              <div className="border border-amber-300 bg-amber-50 rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <i className="pi pi-exclamation-triangle text-amber-600 text-lg"></i>
                  </div>
                  <div>
                    <p className="font-semibold text-amber-800 mb-1">Public Access Warning</p>
                    <p className="text-sm text-amber-700">
                      Anyone with this link can view your analysis results and download the dataset.
                      Only share with people you trust.
                    </p>
                  </div>
                </div>
              </div>
              <Button
                label="Create Public Link"
                icon={loading ? 'pi pi-spin pi-spinner' : 'pi pi-link'}
                onClick={handleCreateShareLink}
                disabled={loading}
                className="w-full !bg-blue-600 hover:!bg-blue-700 !border-blue-600 !text-white font-semibold py-3 px-6 shadow-sm"
              />
            </div>
          ) : (
            // Already shared - show link and revoke option
            <div className="space-y-5">
              <div className="border border-blue-200 bg-brand-50 rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <i className="pi pi-globe text-brand-500 text-lg"></i>
                  </div>
                  <p className="text-blue-800">
                    This result is publicly accessible via the link below.
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <InputText value={getShareUrl()} readOnly className="flex-1 font-mono text-sm" />
                <Button
                  icon="pi pi-copy"
                  onClick={handleCopyLink}
                  tooltip="Copy to clipboard"
                  tooltipOptions={{ position: 'top' }}
                  className="!bg-surface-alt !text-primary !border-[var(--color-border)] hover:!bg-surface-alt"
                />
              </div>

              <div className="bg-surface-alt border border-[var(--color-border)] rounded-xl p-4 mt-4">
                <p className="text-sm text-secondary mb-3">
                  Want to make this result private again?
                </p>
                <Button
                  label="Make Private"
                  icon={loading ? 'pi pi-spin pi-spinner' : 'pi pi-lock'}
                  onClick={handleRevokeShareLink}
                  disabled={loading}
                  className="w-full !bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold py-3 px-6 shadow-sm"
                />
              </div>
            </div>
          )}
        </div>
      </Dialog>
    </>
  );
};

export default ShareDialog;
