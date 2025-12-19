import React, { useState, useRef } from 'react';

import { InputTextarea } from 'primereact/inputtextarea';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { SelectButton } from 'primereact/selectbutton';
import { Dialog } from 'primereact/dialog';
import { Toast } from 'primereact/toast';
import { Menu } from 'primereact/menu';

interface ProblemFormProps {
  columns: string[];
  excludedColumns?: string[];
  nanCounts?: Record<string, number>;
  onSubmit: (data: any) => void;
}

const ProblemForm: React.FC<ProblemFormProps> = ({ columns, excludedColumns, nanCounts, onSubmit }) => {
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [jsonContent, setJsonContent] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const toast = useRef<Toast>(null);
  const analysisMenuRef = useRef<Menu>(null);

  // Analysis type state
  const [analysisType, setAnalysisType] = useState<'quick' | 'deep'>('quick');

  // Form state
  const [projectDescription, setProjectDescription] = useState('');
  const [targetVariable, setTargetVariable] = useState('');
  const [featureDescriptions, setFeatureDescriptions] = useState<Record<string, string>>({});

  const handleJsonUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          setJsonContent(event.target.result as string);
        }
      };
      reader.readAsText(e.target.files[0]);
    }
  };

  const validateAndGetPayload = () => {
    if (!projectDescription.trim()) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'Project Description is required.' });
      return null;
    }
    if (!targetVariable) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'Target Variable is required.' });
      return null;
    }

    // Check if target variable has NaN values
    if (nanCounts && nanCounts[targetVariable] > 0) {
      toast.current?.show({
        severity: 'error',
        summary: 'Invalid Target Variable',
        detail: `The target variable "${targetVariable}" contains ${nanCounts[targetVariable]} missing (NaN) values. Please clean your data or select a different target.`
      });
      return null;
    }

    const activeColumns = columns.filter(col =>
      col !== targetVariable &&
      (!excludedColumns || !excludedColumns.includes(col))
    );

    const missingDescriptions = activeColumns.filter(col => !featureDescriptions[col] || featureDescriptions[col].trim() === '');

    if (missingDescriptions.length > 0) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: `Please provide descriptions for all features. Missing: ${missingDescriptions.join(', ')}` });
      return null;
    }

    const features: Record<string, string> = {};
    activeColumns.forEach(col => {
      features[col] = featureDescriptions[col];
    });

    return {
      project_description: projectDescription,
      target_variable: targetVariable,
      features: features
    };
  };

  const handleExportJson = () => {
    const payload = validateAndGetPayload();
    if (!payload) return;

    // Export
    const jsonString = JSON.stringify(payload, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'problem_config.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleSubmit = () => {
    if (mode === 'json') {
      try {
        if (!jsonContent.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON content is empty.' });
          return;
        }
        const parsed = JSON.parse(jsonContent);

        // Validate JSON structure
        if (!parsed.project_description || typeof parsed.project_description !== 'string' || !parsed.project_description.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain a valid "project_description".' });
          return;
        }
        if (!parsed.target_variable || typeof parsed.target_variable !== 'string' || !parsed.target_variable.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain a valid "target_variable".' });
          return;
        }
        if (!parsed.features || typeof parsed.features !== 'object' || Array.isArray(parsed.features) || Object.keys(parsed.features).length === 0) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain "features" object with at least one feature.' });
          return;
        }

        // Validate that target_variable exists in columns
        if (!columns.includes(parsed.target_variable)) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" does not exist in the uploaded dataset.`
          });
          return;
        }

        // Validate that all feature names exist in columns
        const invalidFeatures = Object.keys(parsed.features).filter(feature => !columns.includes(feature));
        if (invalidFeatures.length > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Features',
            detail: `The following features do not exist in the dataset: ${invalidFeatures.join(', ')}`
          });
          return;
        }

        // Check if target variable has NaN values
        if (nanCounts && nanCounts[parsed.target_variable] > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" contains missing (NaN) values. Please clean your data or select a different target.`
          });
          return;
        }

        onSubmit({ ...parsed, analysis_type: analysisType });
      } catch (e) {
        toast.current?.show({ severity: 'error', summary: 'Invalid JSON', detail: (e as Error).message });
      }
    } else {
      // Validation for Form Mode
      const payload = validateAndGetPayload();
      if (payload) {
        onSubmit({ ...payload, analysis_type: analysisType });
      }
    }
  };

  const modeOptions = [
    { label: 'Interactive Form', value: 'form' },
    { label: 'Upload JSON', value: 'json' }
  ];

  return (
    <div className="p-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 mb-2">Define the Problem</h2>
          <p className="text-slate-500">Tell the AI what you want to predict and explain.</p>
        </div>

        <div className="mt-4 md:mt-0">
          <SelectButton value={mode} onChange={(e: any) => setMode(e.value)} options={modeOptions} />
        </div>
      </div>

      {excludedColumns && excludedColumns.length > 0 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-start">
            <i className="pi pi-exclamation-triangle text-yellow-600 text-xl mr-3 mt-0.5"></i>
            <div>
              <h4 className="font-semibold text-yellow-800 text-sm">Columns Excluded</h4>
              <p className="text-sm text-yellow-700 mt-1">
                The following columns were automatically excluded because they contain non-numeric data:
                <span className="font-mono ml-1 font-medium">{excludedColumns.join(', ')}</span>
              </p>
            </div>
          </div>
        </div>
      )}

      {mode === 'json' ? (
        <div className="space-y-6 animate-fade-in">
          <div className="border-2 border-dashed border-slate-300 rounded-2xl p-12 text-center hover:border-blue-400 hover:bg-slate-50 transition-colors cursor-pointer relative group">
            <input type="file" accept=".json" onChange={handleJsonUpload} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" id="json-upload" />
            <div className="bg-slate-100 p-4 rounded-full inline-block mb-4 group-hover:bg-white group-hover:shadow-sm transition-all">
                <i className="pi pi-file text-4xl text-slate-400 group-hover:text-blue-500 transition-colors"></i>
            </div>
            <p className="text-lg font-semibold text-slate-700">Click to upload JSON configuration</p>
            <p className="text-sm text-slate-500 mt-1">or drag and drop here</p>
          </div>

          <div className="relative">
            <div className="flex justify-between items-center mb-2">
              <label className="block text-sm font-bold text-slate-700 ml-1">Configuration Preview</label>
              <div>
                <div>
                  <Button
                    icon="pi pi-question-circle"
                    className="p-button-rounded p-button-text p-button-sm"
                    onClick={() => setShowHelp(true)}
                    tooltip="View Example JSON"
                    tooltipOptions={{ position: 'left' }}
                  />
                  <Dialog
                    header="Example Configuration"
                    visible={showHelp}
                    onHide={() => setShowHelp(false)}
                    className="w-[90vw] max-w-[600px]"
                    draggable={false}
                    resizable={false}
                  >
                    <div className="pt-2">
                      <p className="text-xs text-slate-600 mb-3">Your JSON file should follow this structure:</p>
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
                    </div>
                  </Dialog>
                </div>
              </div>
            </div>
            <InputTextarea
              className="w-full font-mono text-sm bg-slate-50"
              rows={12}
              value={jsonContent}
              onChange={(e) => setJsonContent(e.target.value)}
              placeholder='Paste your JSON configuration here...'
            />
          </div>
        </div>
      ) : (
        <div className="space-y-8 animate-fade-in">
          {/* Project Details Group */}
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
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="e.g., We want to predict soil phosphorus content based on chemical properties..."
                />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Target Variable Group */}
            <div className="lg:col-span-1">
                <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm h-full">
                    <div className="flex items-center mb-4">
                    <div className="bg-green-100 p-2 rounded-lg mr-3 flex-shrink-0">
                            <i className="pi pi-compass text-green-600 text-lg"></i>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-800">Target</h3>
                            <p className="text-sm text-slate-500">What to predict?</p>
                        </div>
                    </div>

                    <div className="mt-4">
                        <label className="block text-sm font-semibold text-slate-700 mb-2">Target Variable</label>
                        <Dropdown
                value={targetVariable}
                onChange={(e: any) => setTargetVariable(e.value)}
                options={columns.map(col => ({ label: col, value: col }))}
                placeholder="Select Target..."
                className="w-full bg-slate-50 border-slate-200"
              />
                    {targetVariable && nanCounts && nanCounts[targetVariable] > 0 && (
                      <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 flex items-start animate-fade-in">
                        <i className="pi pi-exclamation-circle text-red-500 mr-2 mt-0.5"></i>
                        <div className="text-sm text-red-700">
                          <strong>Warning:</strong> This column contains missing values.
                          Analysis cannot proceed with a target containing missing data.
                        </div>
                      </div>
                    )}
                    </div>
                </div>
            </div>

            {/* Features Group */}
            <div className="lg:col-span-2">
                <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm h-full">
                    <div className="flex items-center mb-4">
                    <div className="bg-purple-100 p-2 rounded-lg mr-3 flex-shrink-0">
                            <i className="pi pi-list text-purple-600 text-lg"></i>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-800">Features</h3>
                            <p className="text-sm text-slate-500">Describe your data columns.</p>
                        </div>
                    </div>

                    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                        {columns.map(col => (
                        col !== targetVariable && (
                            <div key={col} className="flex flex-col sm:flex-row sm:items-start space-y-2 sm:space-y-0 sm:space-x-4 p-3 bg-slate-50 rounded-lg border border-slate-100 hover:border-blue-200 transition-colors">
                                <div className="w-full sm:w-1/3 flex items-center sm:self-center">
                                <div key={`${col}-icon`} className="bg-slate-100 p-2 rounded-lg mr-3 flex-shrink-0 w-8 h-8 flex items-center justify-center">
                                  <i className="pi pi-database text-slate-400 text-sm"></i>
                                </div>
                                    <span className="text-sm font-mono font-semibold text-slate-700 truncate" title={col}>{col}</span>
                                </div>
                                <div className="w-full sm:w-2/3">
                                    <InputTextarea
                                  className="w-full p-inputtext-sm bg-white border-slate-200 resize-none"
                                        placeholder={`Description for ${col}`}
                                        value={featureDescriptions[col] || ''}
                                        onChange={(e) => setFeatureDescriptions({ ...featureDescriptions, [col]: e.target.value })}
                                  rows={2}
                                    />
                                </div>
                            </div>
                        )
                        ))}
                    </div>
                </div>
            </div>
          </div>
        </div>
      )}

      <Toast ref={toast} />

      <div className="mt-6 pt-4 flex justify-end space-x-4">
        {mode === 'form' && (
          <Button
            label="Export JSON"
            icon="pi pi-download"
            onClick={handleExportJson}
            className="p-button-outlined p-button-secondary font-bold py-3 px-6 text-xl"
          />
        )}

        {/* Analysis Menu */}
        <Menu
          ref={analysisMenuRef}
          popup
          model={[
            {
              label: 'Quick Analysis',
              icon: 'pi pi-bolt',
              command: () => setAnalysisType('quick'),
              className: analysisType === 'quick' ? 'bg-blue-50' : ''
            },
            {
              label: 'Deep Analysis',
              icon: 'pi pi-search',
              command: () => setAnalysisType('deep'),
              className: analysisType === 'deep' ? 'bg-blue-50' : ''
            }
          ]}
        />

        {/* Split Button for Analysis Type Selection */}
        <div className="flex">
          <Button
            label={analysisType === 'quick' ? 'Quick Analysis' : 'Deep Analysis'}
            icon={analysisType === 'quick' ? 'pi pi-bolt' : 'pi pi-search'}
            iconPos="left"
            onClick={handleSubmit}
            size="large"
            disabled={mode === 'form' && Boolean(targetVariable && nanCounts && nanCounts[targetVariable] > 0)}
            className={`font-bold py-3 px-6 text-xl shadow-lg transition-all rounded-r-none ${mode === 'form' && targetVariable && nanCounts && nanCounts[targetVariable] > 0
              ? 'bg-slate-300 border-slate-300 text-slate-500 cursor-not-allowed'
              : 'bg-blue-500 hover:bg-blue-600 border-blue-500 text-white hover:shadow-xl'
              }`}
          />
          <Button
            icon="pi pi-chevron-down"
            onClick={(e) => analysisMenuRef.current?.toggle(e)}
            size="large"
            disabled={mode === 'form' && Boolean(targetVariable && nanCounts && nanCounts[targetVariable] > 0)}
            className={`font-bold py-3 px-3 text-xl shadow-lg transition-all rounded-l-none border-l-0 ${mode === 'form' && targetVariable && nanCounts && nanCounts[targetVariable] > 0
              ? 'bg-slate-300 border-slate-300 text-slate-500 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700 border-blue-500 text-white'
              }`}
          />
        </div>
      </div>

      {/* Deep Analysis Pricing Warning - shown at bottom */}
      {analysisType === 'deep' && (
        <div className="mt-4 animate-fade-in">
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start">
            <i className="pi pi-exclamation-triangle text-amber-600 text-xl mr-3 mt-0.5"></i>
            <div>
              <h4 className="font-semibold text-amber-800 text-sm">Deep Analysis Notice</h4>
              <p className="text-sm text-amber-700 mt-1">
                Deep Analysis is more expensive to run as it performs additional scientific literature research.
                This system is currently in <strong>experimental mode</strong> and is open for use,
                but this feature may be behind a paywall in the future.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProblemForm;
