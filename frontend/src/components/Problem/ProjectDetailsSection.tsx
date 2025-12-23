/**
 * ProjectDetailsSection Component
 * Card for entering project description
 */

import React from 'react';
import { InputTextarea } from 'primereact/inputtextarea';

interface ProjectDetailsSectionProps {
  projectDescription: string;
  onChange: (value: string) => void;
}

export const ProjectDetailsSection: React.FC<ProjectDetailsSectionProps> = ({
  projectDescription,
  onChange,
}) => (
  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
    <div className="flex items-center mb-4">
      <div className="bg-blue-100 p-2 rounded-lg mr-3 flex-shrink-0">
        <i className="pi pi-info-circle text-blue-600 text-lg"></i>
      </div>
      <div>
        <h3 className="text-lg font-bold text-slate-800">Project Details</h3>
        <p className="text-sm text-slate-500">Provide context for the AI to generate better explanations.</p>
      </div>
    </div>

    <div className="pl-0 md:pl-12">
      <label className="block text-sm font-semibold text-slate-700 mb-2">Project Description</label>
      <InputTextarea
        className="w-full bg-slate-50 border-slate-200 focus:border-blue-500 focus:ring-blue-500 resize-none h-30"
        rows={6}
        value={projectDescription}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g., We want to predict soil phosphorus content based on chemical properties..."
      />
    </div>
  </div>
);

export default ProjectDetailsSection;
