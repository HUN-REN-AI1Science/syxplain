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
import HelpButton from '@components/HelpButton';
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
  const { user: authUser, signOut, hasHunrenAccess, isAdmin } = useAuth();

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
    } catch (e: unknown) {
      console.error('Failed to delete account:', e);
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to delete account. Please try again.');
      setDeleting(false);
    }
  };

  const handleRevokeShare = async () => {
    if (!revokeRunId) return;
    try {
      await sharingService.revokeShareLink(revokeRunId);
      setSharedRuns((prev) => prev.filter((r) => r.id !== revokeRunId));
      toast.current?.show({
        severity: 'success',
        summary: 'Revoked',
        detail: 'Share link removed',
      });
    } catch (e) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to revoke share link',
      });
    } finally {
      setRevokeRunId(null);
    }
  };

  const handleCopyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${url}`);
      toast.current?.show({
        severity: 'success',
        summary: 'Copied',
        detail: 'Link copied to clipboard',
        life: 2000,
      });
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-6 min-h-[400px]">
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        <p className="mt-4 text-secondary">Loading profile...</p>
      </div>
    );
  }

  if (deleting) {
    return (
      <div className="flex flex-col items-center justify-center p-6 min-h-[400px]">
        <ProgressSpinner style={{ width: '60px', height: '60px' }} />
        <p className="mt-4 text-lg text-primary">Deleting your account...</p>
        <p className="text-sm text-secondary">This may take a moment.</p>
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
            <div className="flex items-center gap-2 mb-2">
              <h2 className="font-heading text-2xl font-bold text-primary">Profile</h2>
              <HelpButton title="Your Profile">
                <h4>Usage Statistics</h4>
                <p>
                  Track your analysis activity including total runs, quick vs deep analysis
                  distribution, and account creation date.
                </p>

                <h4>Shared Runs</h4>
                <p>
                  Manage your publicly shared analysis results. You can copy share links or revoke
                  access at any time.
                </p>

                <h4>Danger Zone</h4>
                <p>
                  <strong>Delete Account</strong> permanently removes your account and all
                  associated data including runs and shared links. This action cannot be undone.
                </p>
              </HelpButton>
            </div>
            <p className="text-secondary">Manage your account settings</p>
          </div>
          <Button
            label="Back"
            icon="pi pi-arrow-left"
            className="p-button-outlined p-button-sm w-full sm:w-auto"
            onClick={onBack}
          />
        </div>
      </div>

      {error && <Message severity="error" text={error} className="w-full mb-6" />}

      <AccountInfoSection
        profile={profile}
        hasHunrenAccess={hasHunrenAccess}
        isAdmin={isAdmin}
        userName={authUser?.name}
      />
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
