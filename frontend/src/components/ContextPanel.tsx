import React, { useEffect, useState } from 'react';
import { Activity, Cpu, HardDrive, MemoryStick, Clock, ShieldCheck, X } from 'lucide-react';
import { SystemMetrics, SystemStatus } from '../types';
import { apiClient } from '../api/client';

interface ContextPanelProps {
  status: SystemStatus | null;
  onClose: () => void;
}

export const ContextPanel: React.FC<ContextPanelProps> = ({ status, onClose }) => {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchMetrics = async () => {
      try {
        const data = await apiClient.getMetrics();
        if (isMounted) setMetrics(data);
      } catch (e) {
        // quiet fallback
      }
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const formatUptime = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const hours = Math.floor(mins / 60);
    if (hours > 0) return `${hours}h ${mins % 60}m`;
    return `${mins}m ${Math.floor(sec % 60)}s`;
  };

  return (
    <aside className="w-72 flex flex-col bg-[#080B10] border-l border-echo-border select-none text-xs">
      <div className="p-3.5 border-b border-echo-border flex items-center justify-between">
        <div className="flex items-center gap-2 text-white font-medium">
          <Activity className="w-4 h-4 text-echo-cyan" />
          <span>System Telemetry</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Core Daemon Status */}
        <div className="p-3 rounded-lg border border-echo-border bg-[#0B0E14] space-y-2">
          <div className="font-semibold text-white flex items-center justify-between">
            <span>Daemon Core</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-echo-success/10 text-echo-success font-mono border border-echo-success/30">
              Active
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px] text-echo-muted font-mono">
            <div>DB Engine: <span className="text-gray-300">SQLite (WAL)</span></div>
            <div>Version: <span className="text-gray-300">{status?.version || '0.1.0'}</span></div>
            <div>Active AI: <span className="text-echo-cyan">{status?.ai_provider || 'Mock'}</span></div>
            <div>AI State: <span className={status?.ai_available ? 'text-echo-success' : 'text-echo-warning'}>
              {status?.ai_available ? 'Ready' : 'Checking'}
            </span></div>
          </div>
        </div>

        {/* Live Metrics */}
        {metrics && (
          <div className="space-y-3">
            <div className="text-[11px] font-mono uppercase tracking-wider text-echo-muted">
              Workstation Resources
            </div>

            {/* CPU */}
            <div className="p-2.5 rounded-lg border border-echo-border bg-[#0B0E14]">
              <div className="flex items-center justify-between text-gray-300 mb-1.5">
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-echo-cyan" /> CPU Load
                </span>
                <span className="font-mono text-echo-cyan">{metrics.cpu_percent}%</span>
              </div>
              <div className="w-full bg-[#161B22] h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-echo-cyan h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(metrics.cpu_percent, 100)}%` }}
                />
              </div>
            </div>

            {/* RAM */}
            <div className="p-2.5 rounded-lg border border-echo-border bg-[#0B0E14]">
              <div className="flex items-center justify-between text-gray-300 mb-1.5">
                <span className="flex items-center gap-1.5">
                  <MemoryStick className="w-3.5 h-3.5 text-echo-blue" /> RAM Used
                </span>
                <span className="font-mono text-echo-blue">
                  {metrics.memory_percent}% ({metrics.memory_used_mb} MB)
                </span>
              </div>
              <div className="w-full bg-[#161B22] h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-echo-blue h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(metrics.memory_percent, 100)}%` }}
                />
              </div>
            </div>

            {/* Disk */}
            <div className="p-2.5 rounded-lg border border-echo-border bg-[#0B0E14]">
              <div className="flex items-center justify-between text-gray-300 mb-1.5">
                <span className="flex items-center gap-1.5">
                  <HardDrive className="w-3.5 h-3.5 text-echo-purple" /> Primary Disk
                </span>
                <span className="font-mono text-echo-purple">{metrics.disk_percent}%</span>
              </div>
              <div className="w-full bg-[#161B22] h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-echo-purple h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(metrics.disk_percent, 100)}%` }}
                />
              </div>
            </div>

            {/* Uptime */}
            <div className="p-2.5 rounded-lg border border-echo-border bg-[#0B0E14] flex items-center justify-between text-echo-muted">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" /> Uptime
              </span>
              <span className="font-mono text-gray-200">{formatUptime(metrics.uptime_seconds)}</span>
            </div>
          </div>
        )}

        {/* Security Invariants */}
        <div className="p-3 rounded-lg border border-echo-border bg-[#0B0E14] space-y-2">
          <div className="font-semibold text-white flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-echo-success" />
            <span>Security Boundaries</span>
          </div>
          <ul className="text-[11px] text-echo-muted space-y-1 list-disc pl-4 font-mono">
            <li>Loopback only (127.0.0.1)</li>
            <li>No arbitrary code execution</li>
            <li>Approval required for T2+</li>
            <li>Tainted context fencing active</li>
          </ul>
        </div>
      </div>
    </aside>
  );
};

