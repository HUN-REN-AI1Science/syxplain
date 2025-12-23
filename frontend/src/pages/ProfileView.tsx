/**
 * ProfileView Component
 * Displays user profile and account management options
 */

import React, { useEffect, useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Toast } from 'primereact/toast';
import { useAuth } from '@contexts/AuthContext';
import { profileService, sharingService, type SharedRunInfo } from '@services/api';
import {
  AccountInfoSection,
  UsageStatsSection,
  SharedRunsTable,
  DangerZoneSection,
  DeleteAccountDialog,
  RevokeShareDialog,
} from '@components/Profile';
import type { ProfileData } from '@/types';

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
      <DeleteAccountDialog
        visible={showDeleteDialog}
        onHide={() => setShowDeleteDialog(false)}
        onConfirm={handleDeleteAccount}
      />

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

      <AccountInfoSection profile={profile} />
      <UsageStatsSection profile={profile} />
      <SharedRunsTable
        sharedRuns={sharedRuns}
        loading={sharedLoading}
        onCopyUrl={handleCopyUrl}
        onViewRun={onSelectRun}
        onRevokeShare={setRevokeRunId}
      />
      <DangerZoneSection onDeleteClick={() => setShowDeleteDialog(true)} />

      <RevokeShareDialog
        visible={!!revokeRunId}
        onHide={() => setRevokeRunId(null)}
        onConfirm={handleRevokeShare}
      />

      <Toast ref={toast} />
    </div>
  );
};

export default ProfileView;
