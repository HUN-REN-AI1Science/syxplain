import React, { useState } from 'react';
import api from './api';
import { ProgressBar } from 'primereact/progressbar';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';

interface FileUploadProps {
  onUploadComplete: (filename: string, columns: string[], excludedColumns?: string[]) => void;
}

const FileUpload: React.FC<FileUploadProps> = ({ onUploadComplete }) => {
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

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

          onUploadComplete(response.data.filename, numericColumns, excludedColumns);
        }, 1500);
      }
    } catch (err) {
      setError('Failed to upload file. Please check your connection.');
      console.error(err);
      setUploading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
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
            <p className="text-slate-500">Supported format: .csv</p>
          </div>

          <div
          className={`w-full relative border-2 border-dashed rounded-2xl p-6 md:p-12 text-center transition-all duration-300 ease-in-out group ${
              dragActive
                ? 'border-blue-500 bg-blue-50 scale-[1.01] shadow-inner'
                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept=".csv"
              onChange={handleChange}
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
                  {uploading ? 'Uploading...' : 'Drag & Drop your CSV file here'}
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
      </div>

      {/* Overlay for Uploading / Processing */}
      {(uploading || processing) && (
        <div className="absolute inset-0 flex items-center justify-center z-20">
            <div className="bg-white/90 backdrop-blur-md p-8 rounded-2xl shadow-2xl w-full max-w-md flex flex-col items-center animate-fade-in-up border border-slate-100">
                <div className="w-full mb-4">
                    <ProgressBar
                        mode="indeterminate"
                        style={{ height: '8px' }}
                        className="w-full"
                color="#0052cc"
                    ></ProgressBar>
                </div>
                <div className="flex items-center space-x-3">
                    {processing ? (
                        <i className="pi pi-cog pi-spin text-blue-600 text-xl"></i>
                    ) : (
                        <i className="pi pi-upload text-blue-600 text-xl"></i>
                    )}
                    <span className="text-slate-700 font-semibold text-lg">
                        {processing ? 'Processing file...' : 'Uploading...'}
                    </span>
                </div>
                <p className="text-slate-500 text-sm mt-2">
                    {processing ? 'Analyzing columns and structure' : 'Please wait while we upload your data'}
                </p>
            </div>
        </div>
      )}

      {error && (
        <div className="w-full max-w-2xl mt-6 z-10">
          <Message severity="error" text={error} className="w-full" />
        </div>
      )}
    </div>
  );
};

export default FileUpload;
