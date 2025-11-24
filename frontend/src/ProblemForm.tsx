import React, { useState } from 'react';

import { InputTextarea } from 'primereact/inputtextarea';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { SelectButton } from 'primereact/selectbutton';
import { Dialog } from 'primereact/dialog';

interface ProblemFormProps {
  columns: string[];
  onSubmit: (data: any) => void;
}

const ProblemForm: React.FC<ProblemFormProps> = ({ columns, onSubmit }) => {
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [jsonContent, setJsonContent] = useState('');
  const [showHelp, setShowHelp] = useState(false);

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

  const handleSubmit = () => {
    if (mode === 'json') {
      try {
        const parsed = JSON.parse(jsonContent);
        onSubmit(parsed);
      } catch (e) {
        alert(`Invalid JSON format: ${(e as Error).message}`);
      }
    } else {
      // Filter out target variable from features
      const features: Record<string, string> = {};
      columns.forEach(col => {
        if (col !== targetVariable && featureDescriptions[col]) {
          features[col] = featureDescriptions[col];
        }
      });

      const payload = {
        project_description: projectDescription,
        target_variable: targetVariable,
        features: features
      };
      onSubmit(payload);
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

      <div className="mt-10 pt-6 border-t border-slate-100 flex justify-end">
        <Button
          label="Start Analysis"
          icon="pi pi-arrow-right"
          iconPos="right"
          onClick={handleSubmit}
          size="large"
          className="bg-blue-500 hover:bg-blue-600 border-blue-500 text-white font-bold py-3 px-6 text-xl shadow-lg hover:shadow-xl transition-all transform hover:-translate-y-0.5"
        />
      </div>
    </div>
  );
};

export default ProblemForm;
