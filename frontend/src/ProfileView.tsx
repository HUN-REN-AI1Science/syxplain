/**
 * ProfileView Component
 * Displays user profile and account management options
 */

import React, { useEffect, useState } from 'react';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { useAuth } from './contexts/AuthContext';
import { profileService } from './services/api';
import type { ProfileData } from './types';

interface ProfileViewProps {
  onBack: () => void;
}

const ProfileView: React.FC<ProfileViewProps> = ({ onBack }) => {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    </div>
  );
};

export default ProfileView;
