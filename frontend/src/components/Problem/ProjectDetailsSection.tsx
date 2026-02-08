/**
 * ProjectDetailsSection Component
 * Card for entering project description
 */

import React from 'react';
import { InputTextarea } from 'primereact/inputtextarea';
import HelpButton from '@components/HelpButton';

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
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-bold text-slate-800">Project Details</h3>
          <HelpButton title="Project Description">
            <h4>What is this for?</h4>
            <p>
              The project description provides context for the AI to understand your research domain
              and generate more accurate, scientifically relevant explanations.
            </p>

            <h4>Writing a Good Description</h4>
            <ul>
              <li>
                Describe the <strong>scientific domain</strong> (e.g., soil chemistry, materials
                science)
              </li>
              <li>
                Explain your <strong>research goal</strong> and what you're trying to understand
              </li>
              <li>
                Mention any <strong>known relationships</strong> or hypotheses you're testing
              </li>
            </ul>

            <h4>Example</h4>
            <p>
              <em>
                "We are studying soil health indicators to predict phosphorus availability. The data
                comes from agricultural fields with varying fertilization histories. We expect pH
                and organic matter to be key drivers."
              </em>
            </p>
          </HelpButton>
        </div>
        <p className="text-sm text-slate-500">
          Provide context for the AI to generate better explanations.
        </p>
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
