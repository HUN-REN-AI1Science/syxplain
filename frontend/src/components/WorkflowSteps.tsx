/**
 * WorkflowSteps Component
 * Custom step indicator replacing PrimeReact Steps, eliminating !important overrides
 */

import React from 'react';
import { Check } from 'lucide-react';

interface WorkflowStepsProps {
  activeIndex: number;
  items: Array<{ label: string }>;
}

export const WorkflowSteps: React.FC<WorkflowStepsProps> = ({ activeIndex, items }) => (
  <div className="px-4 pt-4">
    {/* Desktop Steps */}
    <div className="hidden md:block mb-8">
      <div className="flex items-center justify-center">
        {items.map((item, index) => {
          const isCompleted = index < activeIndex;
          const isActive = index === activeIndex;
          const isLast = index === items.length - 1;

          return (
            <React.Fragment key={index}>
              <div className="flex flex-col items-center relative">
                {/* Circle */}
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm transition-all ${
                    isCompleted
                      ? 'bg-brand-500 text-white'
                      : isActive
                        ? 'bg-brand-500 text-white ring-4 ring-brand-100'
                        : 'bg-surface-alt text-muted border border-[var(--color-border)]'
                  }`}
                >
                  {isCompleted ? <Check className="w-5 h-5" /> : index + 1}
                </div>
                {/* Label */}
                <span
                  className={`mt-2 text-sm font-medium whitespace-nowrap ${
                    isCompleted || isActive ? 'text-brand-500 font-semibold' : 'text-muted'
                  }`}
                >
                  {item.label}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div className="flex-1 mx-3 mt-[-20px]">
                  <div
                    className={`h-0.5 w-full transition-colors ${
                      index < activeIndex ? 'bg-brand-500' : 'bg-[var(--color-border)]'
                    }`}
                  />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>

    {/* Mobile Steps */}
    <div className="md:hidden mb-6 text-center">
      <span className="text-sm font-semibold text-brand-500 uppercase tracking-wider">
        Step {activeIndex + 1} of {items.length}
      </span>
      <h2 className="text-xl font-bold text-primary font-heading mt-1">
        {items[activeIndex].label}
      </h2>
      <div className="w-full bg-[var(--color-border)] h-1.5 mt-3 rounded-full overflow-hidden">
        <div
          className="bg-brand-500 h-full transition-all duration-300"
          style={{ width: `${((activeIndex + 1) / items.length) * 100}%` }}
        />
      </div>
    </div>
  </div>
);

export default WorkflowSteps;
