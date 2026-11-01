/**
 * Header of the Run Configuration panel (owner and public views): the whole header opens and
 * closes the panel, not only the chevron.
 */

import type { PanelHeaderTemplateOptions } from 'primereact/panel';

export const runSettingsHeader = (options: PanelHeaderTemplateOptions) => (
  <button
    type="button"
    onClick={options.onTogglerClick}
    aria-expanded={!options.collapsed}
    className="flex items-center justify-between w-full px-4 py-3 bg-transparent border-0 cursor-pointer text-left hover:bg-surface-alt transition-colors"
  >
    <span className="flex items-center">
      <i className="pi pi-cog text-muted text-lg mr-3" aria-hidden="true"></i>
      <span className="text-lg font-bold text-primary font-heading">Run Configuration</span>
    </span>
    <span className="w-8 h-8 rounded-lg bg-surface-alt flex items-center justify-center">
      <i
        className={`pi ${options.collapsed ? 'pi-chevron-down' : 'pi-chevron-up'} text-secondary text-sm`}
        aria-hidden="true"
      ></i>
    </span>
  </button>
);
