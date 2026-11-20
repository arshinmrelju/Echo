import React, { useState, useEffect } from 'react';
import {
  X,
  Sliders,
  Monitor,
  MousePointer,
  Keyboard,
  AppWindow,
  FolderTree,
  Clipboard,
  Shield,
  Play,
  CheckCircle2,
  AlertTriangle,
  History,
  Camera,
  RotateCw,
} from 'lucide-react';
import { ActionLogItem, ActiveWindowInfo, ApprovalRequest, ToolItem } from '../types';
import { apiClient } from '../api/client';

interface ControlPanelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTriggerApproval: (req: ApprovalRequest) => void;
}

export const ControlPanelModal: React.FC<ControlPanelModalProps> = ({
  isOpen,
  onClose,
  onTriggerApproval,
}) => {
  const [activeTab, setActiveTab] = useState<'tools' | 'window' | 'approvals' | 'logs'>('tools');
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [activeWindow, setActiveWindow] = useState<ActiveWindowInfo | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [logs, setLogs] = useState<ActionLogItem[]>([]);
  const [executingTool, setExecutingTool] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<any | null>(null);
  const [screenshotPreview, setScreenshotPreview] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const loadData = async () => {
    try {
      const [tData, aData, lData, wData] = await Promise.all([
        apiClient.listTools(),
        apiClient.listApprovals(),
        apiClient.getToolLogs(30),
        apiClient.getActiveWindow(),
      ]);
      setTools(tData.tools);
      setApprovals(aData);
      setLogs(lData);
      setActiveWindow(wData);
    } catch (e) {
      console.error('Failed to load control panel data', e);
    }
  };

  if (!isOpen) return null;

  const handleRunTool = async (tool: ToolItem) => {
    setExecutingTool(tool.name);
    setExecutionResult(null);
    try {
      const res = await apiClient.executeTool(tool.name, {});
      setExecutionResult(res);
      if (res.requires_approval && res.approval_request_id) {
        const pending = await apiClient.listApprovals();
        const found = pending.find((p) => p.id === res.approval_request_id);
        if (found) onTriggerApproval(found);
      }
      if (tool.name.includes('capture') && res.success && res.data?.preview_base64) {
        setScreenshotPreview(res.data.preview_base64);
      }
      loadData();
    } catch (e) {
      setExecutionResult({ success: false, error: String(e) });
    } finally {
      setExecutingTool(null);
    }
  };

  const handleResolveApproval = async (id: string, approved: boolean) => {
    try {
      await apiClient.resolveApproval(id, approved);
      loadData();
    } catch (e) {
      alert('Failed to resolve approval: ' + String(e));
    }
  };

  const filteredTools =
    activeCategory === 'all'
      ? tools
      : tools.filter((t) => t.category === activeCategory);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm select-none p-4">
      <div className="w-full max-w-4xl rounded-2xl border border-echo-border bg-[#0B0E14] shadow-2xl flex flex-col overflow-hidden h-[85vh]">
        {/* Header */}
        <div className="p-4 border-b border-echo-border flex items-center justify-between bg-[#0F1420]">
          <div className="flex items-center gap-2.5 text-white font-semibold">
            <Sliders className="w-5 h-5 text-echo-cyan" />
            <span>ECHO Desktop Control & Tool System</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan font-mono">
              Stage 2
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              className="p-1.5 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
              title="Refresh"
            >
              <RotateCw className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-echo-border bg-[#080B10] px-4 text-xs font-medium">
          {[
            { id: 'tools', label: `Tools Catalog (${tools.length})`, icon: Sliders },
            { id: 'window', label: 'Active Window', icon: Monitor },
            { id: 'approvals', label: `Approvals (${approvals.length})`, icon: Shield, badge: approvals.length },
            { id: 'logs', label: `Action Log (${logs.length})`, icon: History },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all ${
                  isActive
                    ? 'border-echo-cyan text-echo-cyan bg-echo-cyan/5 font-semibold'
                    : 'border-transparent text-echo-muted hover:text-white'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {tab.badge && tab.badge > 0 ? (
                  <span className="px-1.5 py-0.2 rounded-full bg-echo-warning text-echo-void text-[10px] font-bold">
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 text-xs">
          {/* 1. Tools Catalog Tab */}
          {activeTab === 'tools' && (
            <div className="space-y-4">
              {/* Category Filter Pills */}
              <div className="flex items-center gap-1.5 flex-wrap">
                {['all', 'screen', 'window', 'mouse', 'keyboard', 'application', 'filesystem', 'clipboard', 'system'].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setActiveCategory(cat)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-mono transition-colors uppercase ${
                      activeCategory === cat
                        ? 'bg-echo-cyan/20 text-echo-cyan border border-echo-cyan/40'
                        : 'text-echo-muted hover:text-white bg-[#0F1420] border border-echo-border'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              {/* Execution Feedback Banner */}
              {executionResult && (
                <div
                  className={`p-3 rounded-lg border flex items-start gap-2.5 ${
                    executionResult.success
                      ? 'bg-echo-success/10 border-echo-success/30 text-echo-success'
                      : 'bg-echo-danger/10 border-echo-danger/30 text-echo-danger'
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 font-mono text-[11px] overflow-x-auto">
                    <div>Status: {executionResult.success ? 'Success' : 'Failed'}</div>
                    {executionResult.error && <div>Error: {executionResult.error}</div>}
                    {executionResult.data && (
                      <pre className="mt-1 text-gray-300 max-h-24 overflow-y-auto">
                        {JSON.stringify(executionResult.data, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              )}

              {/* Tools Grid */}
              <div className="grid grid-cols-2 gap-3">
                {filteredTools.map((tool) => (
                  <div
                    key={tool.name}
                    className="p-3.5 rounded-xl border border-echo-border bg-[#080B10] hover:border-echo-cyan/40 transition-all flex flex-col justify-between space-y-3"
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-semibold text-white text-[13px]">{tool.name}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase border ${
                            tool.permission_level === 'automatic'
                              ? 'bg-echo-success/10 text-echo-success border-echo-success/30'
                              : 'bg-echo-warning/10 text-echo-warning border-echo-warning/30'
                          }`}
                        >
                          {tool.permission_level === 'automatic' ? 'Auto' : 'Approval'}
                        </span>
                      </div>
                      <p className="text-echo-muted text-[11px] leading-relaxed">{tool.description}</p>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-echo-border/50 text-[10px] text-echo-muted font-mono">
                      <span>Timeout: {tool.timeout_seconds}s</span>
                      <button
                        onClick={() => handleRunTool(tool)}
                        disabled={executingTool === tool.name}
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan hover:bg-echo-cyan/20 transition-all disabled:opacity-50"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>{executingTool === tool.name ? 'Running...' : 'Execute'}</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. Active Window & Screenshot Tab */}
          {activeTab === 'window' && (
            <div className="space-y-5">
              <div className="p-4 rounded-xl border border-echo-border bg-[#080B10] space-y-3">
                <div className="text-sm font-semibold text-white flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Monitor className="w-4 h-4 text-echo-cyan" /> Foreground Window Details
                  </span>
                  <button
                    onClick={async () => {
                      const res = await apiClient.executeTool('screen.capture_desktop', {});
                      if (res.success && res.data?.preview_base64) {
                        setScreenshotPreview(res.data.preview_base64);
                      }
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan hover:bg-echo-cyan/20 transition-colors"
                  >
                    <Camera className="w-3.5 h-3.5" />
                    <span>Capture Screen</span>
                  </button>
                </div>

                {activeWindow ? (
                  <div className="grid grid-cols-2 gap-3 font-mono text-[11px]">
                    <div className="p-2.5 rounded-lg bg-[#0F1420] border border-echo-border">
                      <span className="text-echo-muted">Title:</span>
                      <div className="text-white truncate font-sans text-xs mt-0.5">{activeWindow.title || 'Untitled'}</div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-[#0F1420] border border-echo-border">
                      <span className="text-echo-muted">Process Name:</span>
                      <div className="text-echo-cyan text-xs mt-0.5">{activeWindow.process_name}</div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-[#0F1420] border border-echo-border">
                      <span className="text-echo-muted">Handle (HWND):</span>
                      <div className="text-gray-300 text-xs mt-0.5">{activeWindow.handle}</div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-[#0F1420] border border-echo-border">
                      <span className="text-echo-muted">PID:</span>
                      <div className="text-gray-300 text-xs mt-0.5">{activeWindow.pid}</div>
                    </div>
                  </div>
                ) : (
                  <div className="text-echo-muted">Querying active window...</div>
                )}
              </div>

              {screenshotPreview && (
                <div className="space-y-2">
                  <div className="font-semibold text-white flex items-center justify-between">
                    <span>Recent Screen Capture Preview</span>
                    <button
                      onClick={() => setScreenshotPreview(null)}
                      className="text-[11px] text-echo-muted hover:text-echo-danger"
                    >
                      Clear
                    </button>
                  </div>
                  <div className="rounded-xl border border-echo-border overflow-hidden bg-black p-1 shadow-inner">
                    <img src={screenshotPreview} alt="Desktop Preview" className="w-full max-h-80 object-contain rounded-lg" />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 3. Approvals Tab */}
          {activeTab === 'approvals' && (
            <div className="space-y-3">
              {approvals.length === 0 ? (
                <div className="py-16 text-center text-echo-muted flex flex-col items-center justify-center">
                  <Shield className="w-10 h-10 text-echo-muted/40 mb-2" />
                  <div>No pending approval requests.</div>
                </div>
              ) : (
                approvals.map((req) => (
                  <div
                    key={req.id}
                    className="p-4 rounded-xl border border-echo-warning/40 bg-[#0E121B] flex flex-col justify-between space-y-3 shadow-[0_0_15px_rgba(255,179,0,0.1)]"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-echo-cyan font-bold">{req.tool_name}</span>
                          <span className="px-2 py-0.5 rounded text-[10px] bg-echo-warning/20 text-echo-warning font-mono uppercase">
                            {req.category}
                          </span>
                        </div>
                        <div className="text-echo-muted text-[11px] mt-1">{req.description}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleResolveApproval(req.id, false)}
                          className="px-3 py-1 rounded-lg border border-echo-danger/40 text-echo-danger hover:bg-echo-danger/20 transition-all font-medium"
                        >
                          Deny
                        </button>
                        <button
                          onClick={() => handleResolveApproval(req.id, true)}
                          className="px-3 py-1 rounded-lg bg-echo-warning text-echo-void font-bold hover:bg-echo-warning/90 transition-all shadow-[0_0_10px_rgba(255,179,0,0.3)]"
                        >
                          Approve
                        </button>
                      </div>
                    </div>
                    <pre className="p-2.5 rounded-lg bg-[#05070A] border border-echo-border text-echo-cyan font-mono text-[10px] overflow-x-auto">
                      {JSON.stringify(req.args, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>
          )}

          {/* 4. Action Logs Tab */}
          {activeTab === 'logs' && (
            <div className="space-y-2">
              {logs.length === 0 ? (
                <div className="py-16 text-center text-echo-muted">No tool actions recorded yet.</div>
              ) : (
                logs.map((log) => (
                  <div
                    key={log.id}
                    className="p-3 rounded-lg border border-echo-border bg-[#080B10] flex items-center justify-between text-xs font-mono"
                  >
                    <div className="flex items-center gap-3 truncate">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          log.status === 'success'
                            ? 'bg-echo-success'
                            : log.status === 'timeout'
                            ? 'bg-echo-warning'
                            : 'bg-echo-danger'
                        }`}
                      />
                      <span className="font-semibold text-white">{log.action}</span>
                      <span className="text-echo-muted truncate max-w-sm">{log.details}</span>
                    </div>
                    <span className="text-[10px] text-gray-500">{new Date(log.created_at).toLocaleTimeString()}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
