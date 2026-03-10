/**
 * ApiKeysSection Component
 * Manage a single personal API key for programmatic access
 */

import React, { useEffect, useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { apiKeysService } from '@services/api';
import type { ApiKey, CreateApiKeyResponse } from '@/types';

export const ApiKeysSection: React.FC = () => {
  const [apiKey, setApiKey] = useState<ApiKey | null>(null);
  const [loading, setLoading] = useState(true);
  const [showKeyDialog, setShowKeyDialog] = useState(false);
  const [showRevokeConfirm, setShowRevokeConfirm] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreateApiKeyResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const toast = useRef<Toast>(null);

  const fetchKey = async () => {
    try {
      const response = await apiKeysService.get();
      setApiKey(response.data);
    } catch {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load API key',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKey();
  }, []);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const response = await apiKeysService.generate();
      setCreatedKey(response.data);
      setShowKeyDialog(true);
      fetchKey();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: err.response?.data?.detail || 'Failed to generate API key',
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleRevoke = async () => {
    try {
      await apiKeysService.revoke();
      setApiKey(null);
      toast.current?.show({ severity: 'success', summary: 'Revoked', detail: 'API key revoked' });
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to revoke key' });
    } finally {
      setShowRevokeConfirm(false);
    }
  };

  const handleRegenerate = async () => {
    setGenerating(true);
    try {
      const response = await apiKeysService.regenerate();
      setCreatedKey(response.data);
      setShowKeyDialog(true);
      fetchKey();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: err.response?.data?.detail || 'Failed to regenerate key',
      });
    } finally {
      setGenerating(false);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.current?.show({
        severity: 'success',
        summary: 'Copied',
        detail: 'API key copied to clipboard',
        life: 2000,
      });
    } catch {
      // fallback
    }
  };

  return (
    <div className="mt-8">
      <div className="flex items-center gap-2 mb-4">
        <i className="pi pi-key text-primary text-xl"></i>
        <h3 className="text-lg font-heading font-semibold text-primary">API Key</h3>
      </div>

      <div className="bg-surface-card border border-surface-border rounded-xl p-4 md:p-6">
        <p className="text-secondary text-sm mb-4">
          Use an API key to authenticate with the Syxplain API from scripts, notebooks, or CI
          pipelines. The key is shown only once when generated.
        </p>

        {loading ? (
          <div className="flex justify-center p-4">
            <ProgressSpinner style={{ width: '30px', height: '30px' }} />
          </div>
        ) : !apiKey ? (
          <div className="text-center py-4">
            <p className="text-secondary mb-3">No API key yet.</p>
            <Button
              label="Generate API Key"
              icon="pi pi-key"
              className="p-button-outlined"
              onClick={handleGenerate}
              loading={generating}
            />
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg border border-surface-border bg-surface-ground">
            <div className="flex-1 min-w-0">
              <div className="text-sm text-secondary space-x-3">
                <span>
                  <code className="bg-surface-hover px-1 rounded">{apiKey.key_prefix}...</code>
                </span>
                <span>
                  Created{' '}
                  {apiKey.created_at ? new Date(apiKey.created_at).toLocaleDateString() : 'N/A'}
                </span>
                {apiKey.last_used_at && (
                  <span>Last used {new Date(apiKey.last_used_at).toLocaleDateString()}</span>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                label="Regenerate"
                icon="pi pi-refresh"
                className="p-button-sm p-button-outlined p-button-secondary"
                onClick={handleRegenerate}
                loading={generating}
              />
              <Button
                label="Revoke"
                icon="pi pi-trash"
                className="p-button-sm p-button-outlined p-button-danger"
                onClick={() => setShowRevokeConfirm(true)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Show Key Once Dialog */}
      <Dialog
        header="Your New API Key"
        visible={showKeyDialog}
        onHide={() => {
          setShowKeyDialog(false);
          setCreatedKey(null);
        }}
        className="w-full max-w-lg"
        modal
        closable
      >
        {createdKey && (
          <div className="space-y-4">
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-800 font-medium">
                Copy this key now. You won't be able to see it again.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-surface-ground border border-surface-border rounded p-3 text-sm break-all select-all">
                {createdKey.key}
              </code>
              <Button
                icon="pi pi-copy"
                className="p-button-outlined p-button-sm"
                onClick={() => copyToClipboard(createdKey.key)}
                tooltip="Copy to clipboard"
              />
            </div>
          </div>
        )}
      </Dialog>

      {/* Revoke Confirmation Dialog */}
      <Dialog
        header="Revoke API Key"
        visible={showRevokeConfirm}
        onHide={() => setShowRevokeConfirm(false)}
        className="w-full max-w-sm"
        modal
        footer={
          <div className="flex justify-end gap-2">
            <Button
              label="Cancel"
              className="p-button-text"
              onClick={() => setShowRevokeConfirm(false)}
            />
            <Button label="Revoke" className="p-button-danger" onClick={handleRevoke} />
          </div>
        }
      >
        <p className="text-primary">
          This key will immediately stop working. Any scripts using it will fail to authenticate.
        </p>
      </Dialog>

      <Toast ref={toast} />
    </div>
  );
};

export default ApiKeysSection;
