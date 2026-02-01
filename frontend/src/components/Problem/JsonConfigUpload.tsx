/**
 * JsonConfigUpload Component
 * JSON configuration upload and preview section
 */

import React from 'react';
import { InputTextarea } from 'primereact/inputtextarea';
import HelpButton from '@components/HelpButton';

interface JsonConfigUploadProps {
  jsonContent: string;
  onChange: (content: string) => void;
}

export const JsonConfigUpload: React.FC<JsonConfigUploadProps> = ({ jsonContent, onChange }) => {
  const handleJsonUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          onChange(event.target.result as string);
        }
      };
      reader.readAsText(e.target.files[0]);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="border-2 border-dashed border-slate-300 rounded-2xl p-12 text-center hover:border-blue-400 hover:bg-slate-50 transition-colors cursor-pointer relative group">
        <input
          type="file"
          accept=".json"
          onChange={handleJsonUpload}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
          id="json-upload"
        />
        <div className="bg-slate-100 p-4 rounded-full inline-block mb-4 group-hover:bg-white group-hover:shadow-sm transition-all">
          <i className="pi pi-file text-4xl text-slate-400 group-hover:text-blue-500 transition-colors"></i>
        </div>
        <p className="text-lg font-semibold text-slate-700">Click to upload JSON configuration</p>
        <p className="text-sm text-slate-500 mt-1">or drag and drop here</p>
      </div>

      <div className="relative">
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-bold text-slate-700 ml-1">
            Configuration Preview
          </label>
          <HelpButton title="Example Configuration">
            <p className="text-sm text-slate-600 mb-3">
              Your JSON file should follow this structure:
            </p>
            <pre className="bg-slate-800 text-slate-100 p-3 rounded text-xs font-mono overflow-x-auto">
              {`{
  "project_description": "Predicting house prices based on features.",
  "target_variable": "price",
  "features": {
    "sqft": "Total square footage",
    "bedrooms": "Number of bedrooms",
    "location": "Zip code"
  }
}`}
            </pre>
          </HelpButton>
        </div>
        <InputTextarea
          className="w-full font-mono text-sm bg-slate-50"
          rows={12}
          value={jsonContent}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Paste your JSON configuration here..."
        />
      </div>
    </div>
  );
};

export default JsonConfigUpload;
