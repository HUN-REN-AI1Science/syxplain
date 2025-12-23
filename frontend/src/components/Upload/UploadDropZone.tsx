/**
 * UploadDropZone Component
 * Drag & drop zone for file uploads with visual feedback
 */

import React from 'react';
import { Button } from 'primereact/button';

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
    className={`w-full relative border-2 border-dashed rounded-2xl p-6 md:p-12 text-center transition-all duration-300 ease-in-out group ${dragActive
      ? 'border-blue-500 bg-blue-50 scale-[1.01] shadow-inner'
      : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
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

    <div className="flex flex-col items-center justify-center space-y-6 pointer-events-none">
      <div className={`p-6 rounded-full transition-colors duration-300 ${dragActive ? 'bg-blue-100' : 'bg-slate-100 group-hover:bg-white group-hover:shadow-md'}`}>
        <i className={`pi pi-cloud-upload text-5xl ${dragActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-blue-500'} transition-colors duration-300`}></i>
      </div>

      <div className="space-y-2">
        <p className="text-xl font-semibold text-slate-700">
          {uploading ? 'Uploading...' : 'Drag & Drop your file here'}
        </p>
        <p className="text-sm text-slate-500">
          or click to browse from your computer
        </p>
      </div>

      <div className="pt-2">
        <Button label="Browse Files" icon="pi pi-folder-open" className="p-button-outlined p-button-rounded" />
      </div>

      <p className="text-xs text-slate-400 mt-4">
        Maximum file size: 50MB
      </p>
    </div>
  </div>
);

export default UploadDropZone;
