/**
 * ProfileView Component
 * Displays user profile and account management options
 */

import React, { useEffect, useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Toast } from 'primereact/toast';
import { useAuth } from './contexts/AuthContext';
import { profileService, sharingService, type SharedRunInfo } from './services/api';
import type { ProfileData } from './types';

interface ProfileViewProps {
  onBack: () => void;
  onSelectRun?: (runId: string) => void;
}

const ProfileView: React.FC<ProfileViewProps> = ({ onBack, onSelectRun }) => {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sharedRuns, setSharedRuns] = useState<SharedRunInfo[]>([]);
  const [sharedLoading, setSharedLoading] = useState(false);
  const [revokeRunId, setRevokeRunId] = useState<string | null>(null);
  const toast = useRef<Toast>(null);
  const { signOut } = useAuth();

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const response = await profileService.get();
        setProfile(response.data);
      } catch (e) {
        console.error('Failed to fetch profile:', e);
        setError('Failed to load profile data');
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, []);

  // Fetch shared runs
  useEffect(() => {
    const fetchSharedRuns = async () => {
      setSharedLoading(true);
      try {
        const response = await sharingService.getSharedRuns();
        setSharedRuns(response.data.items);
      } catch (e) {
        console.error('Failed to fetch shared runs:', e);
      } finally {
        setSharedLoading(false);
      }
    };
    fetchSharedRuns();
  }, []);

  const handleDeleteAccount = async () => {
    setDeleting(true);
    setShowDeleteDialog(false);
    try {
      await profileService.delete();
      await signOut();
    } catch (e: any) {
      console.error('Failed to delete account:', e);
      setError(e.response?.data?.detail || 'Failed to delete account. Please try again.');
      setDeleting(false);
    }
  };

  const handleRevokeShare = async () => {
    if (!revokeRunId) return;
    try {
      await sharingService.revokeShareLink(revokeRunId);
      setSharedRuns(prev => prev.filter(r => r.id !== revokeRunId));
      toast.current?.show({ severity: 'success', summary: 'Revoked', detail: 'Share link removed' });
    } catch (e) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to revoke share link' });
    } finally {
      setRevokeRunId(null);
    }
  };

  const handleCopyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${url}`);
      toast.current?.show({ severity: 'success', summary: 'Copied', detail: 'Link copied to clipboard', life: 2000 });
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  const deleteDialogFooter = (
    <div className="flex flex-col sm:flex-row gap-3 sm:justify-end pt-4 border-t border-slate-200 mt-4">
      <Button
        label="Cancel"
        icon="pi pi-times"
        onClick={() => setShowDeleteDialog(false)}
        className="w-full sm:w-auto"
        style={{
          backgroundColor: '#f1f5f9',
          color: '#334155',
          border: '1px solid #cbd5e1',
          borderRadius: '8px',
          padding: '0.75rem 1.5rem',
          fontWeight: 500
        }}
      />
      <Button
        label="Delete My Account"
        icon="pi pi-trash"
        onClick={handleDeleteAccount}
        className="w-full sm:w-auto"
        style={{
          backgroundColor: '#dc2626',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          padding: '0.75rem 1.5rem',
          fontWeight: 500
        }}
      />
    </div>
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-6 min-h-[400px]">
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        <p className="mt-4 text-slate-500">Loading profile...</p>
      </div>
    );
  }

  if (deleting) {
    return (
      <div className="flex flex-col items-center justify-center p-6 min-h-[400px]">
        <ProgressSpinner style={{ width: '60px', height: '60px' }} />
        <p className="mt-4 text-lg text-slate-600">Deleting your account...</p>
        <p className="text-sm text-slate-500">This may take a moment.</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Delete Confirmation Dialog */}
      <Dialog
        visible={showDeleteDialog}
        onHide={() => setShowDeleteDialog(false)}
        header={
          <div className="flex items-center gap-3">
            <i className="pi pi-exclamation-triangle text-red-500 text-2xl"></i>
            <span>Delete Account Permanently?</span>
          </div>
        }
        footer={deleteDialogFooter}
        className="w-full max-w-lg mx-4"
        modal
        draggable={false}
      >
        <div className="py-4">
          <p className="text-slate-700 mb-4">
            This action <span className="font-semibold text-red-600">cannot be undone</span>. Deleting your account will permanently remove:
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

      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-800 mb-2">Profile</h2>
            <p className="text-slate-500">Manage your account settings</p>
          </div>
          <Button
            label="Back"
            icon="pi pi-arrow-left"
            className="p-button-outlined p-button-sm w-full sm:w-auto"
            onClick={onBack}
          />
        </div>
      </div>

      {error && (
        <Message severity="error" text={error} className="w-full mb-6" />
      )}

      {/* Account Information Section */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <i className="pi pi-user text-blue-600 text-xl"></i>
          <h3 className="text-lg font-semibold text-slate-700">Account Information</h3>
        </div>
        <div className="bg-slate-50 rounded-xl p-4 md:p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
            <span className="text-slate-500 text-sm sm:w-32 font-medium">Email</span>
            <span className="font-medium text-slate-800 break-all">{profile?.email}</span>
          </div>
          {profile?.created_at && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
              <span className="text-slate-500 text-sm sm:w-32 font-medium">Member since</span>
              <span className="font-medium text-slate-800">
                {new Date(profile.created_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Usage Statistics Section */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <i className="pi pi-chart-bar text-blue-600 text-xl"></i>
          <h3 className="text-lg font-semibold text-slate-700">Usage Statistics</h3>
        </div>
        <div className="bg-blue-50 rounded-xl p-4 md:p-6 text-center border border-blue-100 w-full">
          <p className="text-2xl md:text-3xl font-bold text-blue-600">{profile?.total_runs || 0}</p>
          <p className="text-slate-600 text-xs md:text-sm mt-1">Analysis Runs</p>
        </div>
      </div>

      {/* Shared Results Section */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <i className="pi pi-share-alt text-blue-600 text-xl"></i>
          <h3 className="text-lg font-semibold text-slate-700">Shared Results</h3>
        </div>
        {sharedLoading ? (
          <div className="bg-slate-50 rounded-xl p-6 text-center">
            <ProgressSpinner style={{ width: '30px', height: '30px' }} />
          </div>
        ) : sharedRuns.length === 0 ? (
          <div className="bg-slate-50 rounded-xl p-6 text-center border border-slate-200">
            <i className="pi pi-inbox text-slate-300 text-3xl mb-2"></i>
            <p className="text-slate-500">No shared results yet</p>
            <p className="text-sm text-slate-400 mt-1">Share a completed analysis to see it here</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Dataset</th>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Target</th>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Type</th>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Created</th>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Share Link</th>
                    <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sharedRuns.map((run, idx) => (
                    <tr key={run.id} className={idx !== sharedRuns.length - 1 ? 'border-b border-slate-100' : ''}>
                      <td className="px-4 py-3 text-slate-700 text-sm">
                        <span className="font-mono truncate max-w-[150px] inline-block" title={run.csv_filename}>
                          {run.csv_filename}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-800 font-mono text-sm">
                        {run.target_variable || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium px-2 py-1 rounded-full ${run.analysis_type === 'deep' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>
                          {run.analysis_type === 'deep' ? 'Deep' : 'Quick'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-sm">
                        {run.created_at ? new Date(run.created_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <code className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded truncate max-w-[120px]">
                            {run.share_url}
                          </code>
                          <Button
                            icon="pi pi-copy"
                            className="p-button-text p-button-sm !text-slate-400 hover:!text-blue-600"
                            onClick={() => handleCopyUrl(run.share_url)}
                            tooltip="Copy link"
                            tooltipOptions={{ position: 'top' }}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {onSelectRun && (
                            <Button
                              icon="pi pi-eye"
                              className="p-button-text p-button-sm !text-slate-400 hover:!text-blue-600"
                              onClick={() => onSelectRun(run.id)}
                              tooltip="View results"
                              tooltipOptions={{ position: 'top' }}
                            />
                          )}
                          <Button
                            icon="pi pi-trash"
                            className="p-button-text p-button-sm p-button-danger"
                            onClick={() => setRevokeRunId(run.id)}
                            tooltip="Revoke share link"
                            tooltipOptions={{ position: 'top' }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Danger Zone Section */}
      <div className="mt-8">
        <div className="flex items-center gap-2 mb-4">
          <i className="pi pi-exclamation-triangle text-red-500 text-xl"></i>
          <h3 className="text-lg font-semibold text-red-700">Danger Zone</h3>
        </div>
        <div className="border-2 border-red-200 bg-red-50 rounded-xl p-4 md:p-6">
          <p className="text-slate-700 mb-4 text-sm md:text-base">
            Once you delete your account, there is no going back. All your data will be permanently removed from our servers.
          </p>
          <Button
            label="Delete Account"
            icon="pi pi-trash"
            className="p-button-danger w-full sm:w-auto"
            onClick={() => setShowDeleteDialog(true)}
          />
        </div>
      </div>

      {/* Revoke Confirmation Dialog */}
      <Dialog
        visible={!!revokeRunId}
        onHide={() => setRevokeRunId(null)}
        header="Revoke Share Link?"
        className="w-full max-w-md mx-4"
        modal
        footer={
          <div className="flex gap-3 justify-end">
            <Button label="Cancel" className="p-button-text" onClick={() => setRevokeRunId(null)} />
            <Button label="Revoke" className="p-button-danger" onClick={handleRevokeShare} />
          </div>
        }
      >
        <p className="text-slate-600">This will remove public access. Anyone with the link will no longer be able to view this result.</p>
      </Dialog>

      <Toast ref={toast} />
    </div>
  );
};

export default ProfileView;
