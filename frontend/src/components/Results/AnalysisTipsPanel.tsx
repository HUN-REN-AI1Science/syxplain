/**
 * AnalysisTipsPanel Component
 * Displays helpful tips during the queue/waiting phase of analysis
 */

import React, { useState, useEffect } from 'react';

interface Tip {
  icon: string;
  title: string;
  text: string;
}

const ANALYSIS_TIPS: Tip[] = [
  {
    icon: 'pi-chart-line',
    title: 'What happens next?',
    text: 'Our system will discover mathematical equations that explain patterns in your data.',
  },
  {
    icon: 'pi-clock',
    title: 'Why the wait?',
    text: 'Complex analyses require powerful computing resources. Your turn is coming up!',
  },
  {
    icon: 'pi-check-circle',
    title: 'You can leave',
    text: 'Feel free to close this page. Your results will be saved in History.',
  },
  {
    icon: 'pi-cog',
    title: 'Behind the scenes',
    text: 'We use symbolic regression to find interpretable equations, not black-box models.',
  },
];

interface AnalysisTipsPanelProps {
  /** Whether to show the panel */
  visible?: boolean;
  /** Rotation interval in milliseconds */
  rotationInterval?: number;
}

export const AnalysisTipsPanel: React.FC<AnalysisTipsPanelProps> = ({
  visible = true,
  rotationInterval = 8000,
}) => {
  const [currentTipIndex, setCurrentTipIndex] = useState(0);
  const [animationKey, setAnimationKey] = useState(0);

  useEffect(() => {
    if (!visible) return;

    const interval = setInterval(() => {
      setCurrentTipIndex((prev) => (prev + 1) % ANALYSIS_TIPS.length);
      setAnimationKey((prev) => prev + 1);
    }, rotationInterval);

    return () => clearInterval(interval);
  }, [visible, rotationInterval]);

  if (!visible) return null;

  const currentTip = ANALYSIS_TIPS[currentTipIndex];

  return (
    <div className="mt-8 max-w-md mx-auto">
      <div
        key={animationKey}
        className="tip-animate bg-blue-50 border border-blue-100 rounded-lg p-4"
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
            <i className={`pi ${currentTip.icon} text-blue-600 text-lg`}></i>
          </div>
          <div>
            <h4 className="font-semibold text-slate-800 mb-1">{currentTip.title}</h4>
            <p className="text-sm text-slate-600">{currentTip.text}</p>
          </div>
        </div>
      </div>

      {/* Tip indicator dots */}
      <div className="flex justify-center gap-1.5 mt-3">
        {ANALYSIS_TIPS.map((_, index) => (
          <div
            key={index}
            className={`w-1.5 h-1.5 rounded-full transition-colors duration-300 ${
              index === currentTipIndex ? 'bg-blue-500' : 'bg-slate-300'
            }`}
          />
        ))}
      </div>
    </div>
  );
};

export default AnalysisTipsPanel;
