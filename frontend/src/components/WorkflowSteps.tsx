/**
 * WorkflowSteps Component
 * Desktop and mobile step indicators for the workflow wizard
 */

import React from 'react';
import { Steps } from 'primereact/steps';

interface WorkflowStepsProps {
  activeIndex: number;
  items: Array<{ label: string }>;
}

export const WorkflowSteps: React.FC<WorkflowStepsProps> = ({ activeIndex, items }) => (
  <div className="px-4 pt-4">
    {/* Desktop Steps */}
    <div className="hidden md:block">
      <Steps model={items} activeIndex={activeIndex} readOnly={true} className="mb-8 custom-steps" />
    </div>

    {/* Mobile Steps */}
    <div className="md:hidden mb-6 text-center">
      <span className="text-sm font-semibold text-blue-600 uppercase tracking-wider">
        Step {activeIndex + 1} of {items.length}
      </span>
      <h2 className="text-xl font-bold text-slate-800 mt-1">{items[activeIndex].label}</h2>
      <div className="w-full bg-slate-200 h-1.5 mt-3 rounded-full overflow-hidden">
        <div
          className="bg-blue-600 h-full transition-all duration-300"
          style={{ width: `${((activeIndex + 1) / items.length) * 100}%` }}
        ></div>
      </div>
    </div>
  </div>
);

export default WorkflowSteps;
