/**
 * DangerZoneSection Component
 * Delete account warning and action button
 */

import React from 'react';
import { Button } from 'primereact/button';

interface DangerZoneSectionProps {
  onDeleteClick: () => void;
}

export const DangerZoneSection: React.FC<DangerZoneSectionProps> = ({ onDeleteClick }) => (
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
        onClick={onDeleteClick}
      />
    </div>
  </div>
);

export default DangerZoneSection;
