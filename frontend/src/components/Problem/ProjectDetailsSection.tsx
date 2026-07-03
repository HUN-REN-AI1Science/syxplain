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
  onBlur?: () => void;
}

export const ProjectDetailsSection: React.FC<ProjectDetailsSectionProps> = ({
  projectDescription,
  onChange,
  onBlur,
}) => (
  <div className="bg-surface p-6 rounded-xl border border-[var(--color-border)] shadow-sm">
    <div className="flex items-start gap-3 mb-4">
      <i className="pi pi-pencil text-muted text-lg mt-1 shrink-0"></i>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-heading font-bold text-primary">Project Details</h3>
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
        <p className="text-sm text-secondary">
          Provide context for the AI to generate better explanations.
        </p>
      </div>
    </div>

    <div>
      <label className="block text-sm font-semibold text-secondary mb-2">Project Description</label>
      <InputTextarea
        className="w-full bg-surface-alt border-[var(--color-border)] focus:border-blue-500 focus:ring-blue-500 resize-none h-30"
        rows={6}
        value={projectDescription}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder="e.g., We want to predict soil phosphorus content based on chemical properties..."
      />
    </div>
  </div>
);

export default ProjectDetailsSection;
