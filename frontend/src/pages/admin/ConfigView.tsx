/**
 * ConfigView Component
 * Read-only view of system configuration
 */

import React, { useState, useEffect, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { adminService } from '@services/api';
import type { SystemConfig } from '@/types';

interface ConfigViewProps {
  toast: RefObject<Toast | null>;
}

const ConfigView: React.FC<ConfigViewProps> = ({ toast }) => {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await adminService.getConfig();
      setConfig(response.data);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load configuration',
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-blue-600" />
      </div>
    );
  }

  if (!config) {
    return (
      <div className="text-center py-8 text-slate-500">
        Failed to load configuration
      </div>
    );
  }

  const ConfigItem: React.FC<{
    label: string;
    value: string | number | boolean;
    icon?: string;
  }> = ({ label, value, icon }) => (
    <div className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
      <div className="flex items-center gap-2">
        {icon && <i className={`${icon} text-slate-400`} />}
        <span className="text-slate-600">{label}</span>
      </div>
      <div>
        {typeof value === 'boolean' ? (
          <Tag
            value={value ? 'Enabled' : 'Disabled'}
            severity={value ? 'success' : 'secondary'}
          />
        ) : (
          <span className="font-mono text-slate-800">{value}</span>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">System Configuration</h3>
          <p className="text-sm text-slate-500">Read-only view of current settings</p>
        </div>
        <Button
          icon="pi pi-refresh"
          label="Refresh"
          className="p-button-outlined p-button-sm"
          onClick={fetchConfig}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Compute Configuration */}
        <Card className="shadow-md">
          <h4 className="text-md font-semibold text-slate-700 mb-4">
            <i className="pi pi-server mr-2 text-blue-500" />
            Compute Configuration
          </h4>
          <ConfigItem
            label="Compute Backend"
            value={config.compute_backend}
            icon="pi pi-cog"
          />
          <ConfigItem
            label="Analysis Timeout"
            value={`${config.analysis_timeout_hours} hours`}
            icon="pi pi-clock"
          />
          <ConfigItem
            label="Max File Size"
            value={`${config.max_file_size_mb} MB`}
            icon="pi pi-file"
          />
        </Card>

        {/* Features */}
        <Card className="shadow-md">
          <h4 className="text-md font-semibold text-slate-700 mb-4">
            <i className="pi pi-sliders-h mr-2 text-purple-500" />
            Feature Flags
          </h4>
          <ConfigItem
            label="Slurm Connection"
            value={config.features.slurm_configured}
            icon="pi pi-sitemap"
          />
          <ConfigItem
            label="Deep Research Mode"
            value={config.features.deep_research_enabled}
            icon="pi pi-search"
          />
          <ConfigItem
            label="User API Keys"
            value={config.features.user_api_keys_enabled}
            icon="pi pi-key"
          />
        </Card>

        {/* Rate Limits */}
        <Card className="shadow-md">
          <h4 className="text-md font-semibold text-slate-700 mb-4">
            <i className="pi pi-gauge mr-2 text-orange-500" />
            Rate Limits
          </h4>
          <ConfigItem
            label="Runs per Minute"
            value={config.rate_limits.runs_per_minute}
            icon="pi pi-play"
          />
          <ConfigItem
            label="Uploads per Minute"
            value={config.rate_limits.uploads_per_minute}
            icon="pi pi-upload"
          />
          <ConfigItem
            label="Admin Requests per Minute"
            value={config.rate_limits.admin_requests_per_minute}
            icon="pi pi-shield"
          />
        </Card>

        {/* Secrets & API Keys */}
        <Card className="shadow-md">
          <h4 className="text-md font-semibold text-slate-700 mb-4">
            <i className="pi pi-lock mr-2 text-red-500" />
            Secrets & API Keys
          </h4>
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-3 border-b border-slate-100 gap-2">
              <div className="flex items-center gap-2">
                <i className="pi pi-key text-slate-400" />
                <span className="text-slate-600 text-sm">OpenAI API Key</span>
              </div>
              <div className="flex items-center gap-2 ml-6 sm:ml-0">
                {config.secrets.openai_api_key ? (
                  <>
                    <Tag value="Set" severity="success" />
                    <code className="font-mono text-xs bg-slate-100 px-2 py-1 rounded text-slate-600">
                      {config.secrets.openai_api_key}
                    </code>
                  </>
                ) : (
                  <Tag value="Not Set" severity="secondary" />
                )}
              </div>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-3 border-b border-slate-100 gap-2">
              <div className="flex items-center gap-2">
                <i className="pi pi-search text-slate-400" />
                <span className="text-slate-600 text-sm">Deep Research Key</span>
              </div>
              <div className="flex items-center gap-2 ml-6 sm:ml-0">
                {config.secrets.deep_research_api_key ? (
                  <>
                    <Tag value="Set" severity="success" />
                    <code className="font-mono text-xs bg-slate-100 px-2 py-1 rounded text-slate-600">
                      {config.secrets.deep_research_api_key}
                    </code>
                  </>
                ) : (
                  <Tag value="Not Set" severity="secondary" />
                )}
              </div>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-3 border-b border-slate-100 gap-2">
              <div className="flex items-center gap-2">
                <i className="pi pi-sitemap text-slate-400" />
                <span className="text-slate-600 text-sm">Slurm Token</span>
              </div>
              <div className="flex items-center gap-2 ml-6 sm:ml-0">
                {config.secrets.slurm_auth_token ? (
                  <>
                    <Tag value="Set" severity="success" />
                    <code className="font-mono text-xs bg-slate-100 px-2 py-1 rounded text-slate-600">
                      {config.secrets.slurm_auth_token}
                    </code>
                  </>
                ) : (
                  <Tag value="Not Set" severity="secondary" />
                )}
              </div>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-3 gap-2">
              <div className="flex items-center gap-2">
                <i className="pi pi-database text-slate-400" />
                <span className="text-slate-600 text-sm">Database Host</span>
              </div>
              <div className="flex items-center gap-2 ml-6 sm:ml-0">
                {config.secrets.database_host ? (
                  <>
                    <Tag value="OK" severity="success" />
                    <code className="font-mono text-xs bg-slate-100 px-2 py-1 rounded text-slate-600">
                      {config.secrets.database_host}
                    </code>
                  </>
                ) : (
                  <Tag value="Not Set" severity="secondary" />
                )}
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Connection Status */}
      <Card className="shadow-md">
        <h4 className="text-md font-semibold text-slate-700 mb-4">
          <i className="pi pi-wifi mr-2 text-green-500" />
          Connection Status
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
            <i className={`pi ${config.features.slurm_configured ? 'pi-check-circle text-green-500' : 'pi-exclamation-circle text-yellow-500'}`} />
            <div>
              <p className="font-medium text-slate-700">Slurm Cluster</p>
              <p className="text-sm text-slate-500">
                {config.features.slurm_configured
                  ? 'slurm.science-cloud.hu'
                  : 'Connection issue'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
            <i className={`pi ${config.features.deep_research_enabled ? 'pi-check-circle text-green-500' : 'pi-minus-circle text-slate-400'}`} />
            <div>
              <p className="font-medium text-slate-700">Deep Research</p>
              <p className="text-sm text-slate-500">
                {config.features.deep_research_enabled
                  ? 'API key configured'
                  : 'Optional - not enabled'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
            <i className="pi pi-check-circle text-green-500" />
            <div>
              <p className="font-medium text-slate-700">User API Keys</p>
              <p className="text-sm text-slate-500">
                Users can use own keys
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <i className="pi pi-info-circle text-blue-600 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-800 mb-2">Configuration Notes</h3>
            <ul className="text-sm text-blue-700 list-disc pl-5 space-y-1">
              <li>This is a read-only view of system configuration</li>
              <li>Configuration changes require updating environment variables and restarting the application</li>
              <li>API keys and secrets are masked, showing only the last 4 characters for verification</li>
              <li>Rate limits apply per-user and are enforced by the API</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigView;
