/**
 * UploadView Page
 * Handles CSV and Excel file upload with drag & drop support
 */

import React, { useState } from 'react';
import { Message } from 'primereact/message';
import { uploadService } from '@services/api';
import { UploadDropZone, UploadProgressOverlay } from '@components/Upload';

interface UploadViewProps {
  onUploadComplete: (filename: string, columns: string[], excludedColumns?: string[], nanCounts?: Record<string, number>) => void;
}

const UploadView: React.FC<UploadViewProps> = ({ onUploadComplete }) => {
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    setError(null);

    try {
      const response = await uploadService.uploadFile(file);

      if (response.data.error) {
        setError(response.data.error);
        setUploading(false);
      } else {
        // Upload complete, start processing transition
        setProcessing(true);

        // Add a delay for the "Processing..." UX before transitioning
        setTimeout(() => {
          // Filter out non-numeric columns
          const columnTypes: Record<string, string> = { ...(response.data.column_types || {}) };
          const allColumns = response.data.columns;

          // If column_types is empty but we have columns, warn or fall back to treating all as numeric
          if (allColumns.length > 0 && Object.keys(columnTypes).length === 0) {
            console.warn('column_types missing from backend response, treating all columns as numeric');
            allColumns.forEach((col: string) => columnTypes[col] = 'numeric');
          }

          const numericColumns = allColumns.filter((col: string) =>
            columnTypes[col] === 'numeric'
          );
          const excludedColumns = allColumns.filter((col: string) =>
            columnTypes[col] !== 'numeric'
          );

          onUploadComplete(response.data.filename, numericColumns, excludedColumns, response.data.nan_counts);
        }, 1500);
      }
    } catch (err) {
      setError('Failed to upload file. Please check your connection.');
      console.error(err);
      setUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
      e.target.value = '';
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center p-6 relative min-h-[400px]">
      <div className={`transition-all duration-500 ease-in-out w-full max-w-2xl flex flex-col items-center ${processing ? 'opacity-20 blur-sm scale-95 pointer-events-none' : 'opacity-100'}`}>
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold text-slate-800 mb-2">Upload your Dataset</h2>
          <p className="text-slate-500">Supported formats: .csv, .xlsx, .xls</p>
        </div>

        <UploadDropZone
          dragActive={dragActive}
          uploading={uploading}
          processing={processing}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onFileChange={handleFileChange}
        />
      </div>

      <UploadProgressOverlay uploading={uploading} processing={processing} />

      {error && (
        <div className="w-full max-w-2xl mt-6 z-10">
          <Message severity="error" text={error} className="w-full" />
        </div>
      )}
    </div>
  );
};

export default UploadView;
