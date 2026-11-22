/**
 * LiteratureSection Component
 * Optional card for the user's own literature on the problem
 */

import React from 'react';
import { Checkbox } from 'primereact/checkbox';
import { InputTextarea } from 'primereact/inputtextarea';
import HelpButton from '@components/HelpButton';

/** The backend's limit: the text travels in the prompt of one LLM call */
export const MAX_LITERATURE_CHARS = 60000;

interface LiteratureSectionProps {
  literatureText: string;
  onChange: (value: string) => void;
  /** Web literature research; it can be turned off only when a text is given */
  webLiterature: boolean;
  onWebLiteratureChange: (value: boolean) => void;
}

export const LiteratureSection: React.FC<LiteratureSectionProps> = ({
  literatureText,
  onChange,
  webLiterature,
  onWebLiteratureChange,
}) => {
  const hasText = literatureText.trim().length > 0;
  const tooLong = literatureText.length > MAX_LITERATURE_CHARS;
  return (
    <div className="bg-surface p-6 rounded-xl border border-[var(--color-border)] shadow-sm">
      <div className="flex items-start gap-3 mb-4">
        <i className="pi pi-book text-muted text-lg mt-1 shrink-0"></i>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-heading font-bold text-primary">
              Your Literature <span className="text-sm font-normal text-muted">(optional)</span>
            </h3>
            <HelpButton title="Your Literature">
              <h4>What is this for?</h4>
              <p>
                Paste what is known about the problem: passages of papers, lab notes, published
                equations. It is read in addition to the web literature research. Either kind of
                research can be turned off, but one of them is always used.
              </p>

              <h4>How it is used</h4>
              <ul>
                <li>
                  The text is read once, after the equations are discovered. The discovery itself
                  does not see it.
                </li>
                <li>
                  Its statements are tested on every equation: which variables are not causes, the
                  direction of an effect, where an equation must be defined, what happens in a
                  limit.
                </li>
                <li>
                  The recommended equation is chosen among those <strong>coherent</strong> with the
                  text. The equation with the lowest error is shown beside it when it conflicts with
                  the text, so you can judge which one to trust.
                </li>
                <li>
                  Equations of the literature among your other variables are measured against your
                  data. One that does not hold is a hint that the literature describes another
                  context than yours.
                </li>
              </ul>
            </HelpButton>
          </div>
          <p className="text-sm text-secondary">
            Papers or notes on the problem. The recommendation is then chosen among the equations
            coherent with them.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-sm font-semibold text-secondary mb-2">Literature Text</label>
        <InputTextarea
          className="w-full bg-surface-alt border-[var(--color-border)] focus:border-blue-500 focus:ring-blue-500"
          rows={6}
          value={literatureText}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g., The chamber is sealed, so the humidity of the laboratory air does not reach the film. The rate rises with the precursor pressure and saturates..."
        />
        <p className={`text-xs mt-1 ${tooLong ? 'text-red-500' : 'text-muted'}`}>
          {literatureText.length.toLocaleString()} / {MAX_LITERATURE_CHARS.toLocaleString()}{' '}
          characters{tooLong ? ': too long, shorten the text' : ''}
        </p>
        <div className="flex items-center gap-2 mt-3">
          <Checkbox
            inputId="web-literature"
            checked={webLiterature || !hasText}
            disabled={!hasText}
            onChange={(e) => onWebLiteratureChange(!!e.checked)}
          />
          <label htmlFor="web-literature" className="text-sm text-secondary">
            Web literature research
            {!hasText && (
              <span className="text-muted"> (can be turned off when you give your own text)</span>
            )}
          </label>
        </div>
      </div>
    </div>
  );
};

export default LiteratureSection;
