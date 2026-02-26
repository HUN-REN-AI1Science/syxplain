/**
 * UploadDropZone Component
 * Drag & drop zone for file uploads with visual feedback
 */

import React from 'react';
import { Upload } from 'lucide-react';

interface UploadDropZoneProps {
  dragActive: boolean;
  uploading: boolean;
  processing: boolean;
  onDragEnter: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export const UploadDropZone: React.FC<UploadDropZoneProps> = ({
  dragActive,
  uploading,
  processing,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
  onFileChange,
}) => (
  <div
    className={`w-full relative border-2 border-dashed rounded-2xl p-8 md:p-14 text-center transition-all duration-300 ease-in-out group ${
      dragActive
        ? 'border-brand-500 bg-brand-50 scale-[1.02] shadow-inner'
        : 'border-[var(--color-border-hover)] hover:border-brand-400 hover:bg-surface-alt'
    }`}
    onDragEnter={onDragEnter}
    onDragLeave={onDragLeave}
    onDragOver={onDragOver}
    onDrop={onDrop}
  >
    <input
      type="file"
      accept=".csv,.xlsx,.xls"
      onChange={onFileChange}
      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
      id="csv-upload"
      disabled={uploading || processing}
    />

    <div className="flex flex-col items-center justify-center space-y-5 pointer-events-none">
      <div
        className={`p-5 rounded-full transition-all duration-300 ${
          dragActive
            ? 'bg-brand-100'
            : 'bg-surface-alt group-hover:bg-surface group-hover:shadow-md'
        }`}
      >
        <Upload
          className={`w-12 h-12 transition-colors duration-300 ${
            dragActive ? 'text-brand-500' : 'text-muted group-hover:text-brand-500'
          }`}
          strokeWidth={1.5}
        />
      </div>

      <div className="space-y-2">
        <p className="font-heading text-2xl font-semibold text-primary">
          {uploading ? 'Uploading...' : 'Drag & Drop your file here'}
        </p>
        <p className="text-sm text-secondary">
          or <span className="underline underline-offset-2 text-brand-500">click to browse</span>{' '}
          from your computer
        </p>
      </div>

      <p className="text-xs text-muted">
        Supports CSV, XLSX, XLS &middot; Maximum 50MB
      </p>
    </div>
  </div>
);

export default UploadDropZone;
