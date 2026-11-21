import React from 'react';
import {
  Plus,
  FolderSearch,
  MessageSquare,
  Trash2,
  Brain,
  CheckSquare,
  Cpu,
  Settings as SettingsIcon,
  Zap,
  Activity,
  Sliders,
  ShieldAlert,
  Mic,
  MicOff,
  Radar,
  Satellite,
} from 'lucide-react';
import { Conversation, MonitorSeverity, SystemStatus } from '../types';
import { StatusOrb } from './StatusOrb';

const MONITOR_BADGE: Record<MonitorSeverity, string> = {
  info: 'bg-echo-muted/20 text-echo-muted border border-echo-muted/30',
  notice: 'bg-echo-blue/20 text-echo-blue border border-echo-blue/40',
  warning: 'bg-echo-warning text-echo-void',
  critical: 'bg-echo-danger text-white animate-pulse',
};

const REMOTE_TONE: Record<'LINKED' | 'OFFLINE' | 'IDLE' | 'PAUSED', { chip: string; dot: string }> = {
  LINKED: { chip: 'text-echo-success', dot: 'bg-echo-success animate-pulse' },
  OFFLINE: { chip: 'text-echo-danger', dot: 'bg-echo-danger' },
  PAUSED: { chip: 'text-echo-warning', dot: 'bg-echo-warning' },
  IDLE: { chip: 'text-echo-muted', dot: 'bg-echo-muted' },
};

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
  onOpenMemory: () => void;
  onOpenTasks: () => void;
  onOpenSettings: () => void;
  onOpenControlPanel: () => void;
  onOpenMonitor: () => void;
  onOpenRemote: () => void;
  onOpenFiles: () => void;
  onToggleContext: () => void;
  isContextOpen: boolean;
  status: SystemStatus | null;
  isConnected: boolean;
  pendingApprovalsCount?: number;
  voiceRunning?: boolean;
  voiceMuted?: boolean;
  monitorRunning?: boolean;
  monitorAlertCount?: number;
  monitorSeverity?: MonitorSeverity;
  remoteState?: 'LINKED' | 'OFFLINE' | 'IDLE' | 'PAUSED';
  remoteQueueCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onOpenMemory,
  onOpenTasks,
  onOpenSettings,
  onOpenControlPanel,
  onOpenMonitor,
  onOpenRemote,
  onOpenFiles,
  onToggleContext,
  isContextOpen,
  status,
  isConnected,
  pendingApprovalsCount = 0,
  voiceRunning = false,
  voiceMuted = false,
  monitorRunning = false,
  monitorAlertCount = 0,
  monitorSeverity = 'info',
  remoteState = 'IDLE',
  remoteQueueCount = 0,
}) => {
  return (
    <aside className="w-64 flex flex-col bg-[#07090E] border-r border-echo-border select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-echo-border flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <StatusOrb state={!isConnected ? 'disconnected' : status?.status === 'healthy' ? 'idle' : 'error'} />
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold tracking-wider text-white text-base">ECHO</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan font-mono">
                v0.2
              </span>
            </div>
            <div className="text-[11px] text-echo-muted font-mono">Personal AI Agent</div>
          </div>
        </div>

        <button
          onClick={onToggleContext}
          className={`p-1.5 rounded-lg border transition-colors ${
            isContextOpen
              ? 'bg-echo-cyan/20 border-echo-cyan text-echo-cyan shadow-[0_0_8px_rgba(0,240,255,0.2)]'
              : 'border-echo-border text-echo-muted hover:text-white'
          }`}
          title="Toggle System Context Panel"
        >
          <Activity className="w-4 h-4" />
        </button>
      </div>

      {/* New Conversation Button */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#0F1420] border border-echo-border hover:border-echo-cyan/50 text-sm font-medium text-white shadow-sm hover:shadow-cyan-glow transition-all"
        >
          <Plus className="w-4 h-4 text-echo-cyan" />
          <span>New Conversation</span>
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        <div className="px-2 py-1 text-[11px] font-mono uppercase tracking-wider text-echo-muted">
          Recent Conversations
        </div>
        {conversations.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-echo-muted">
            No conversations yet.
          </div>
        ) : (
          conversations.map((conv) => {
            const isActive = conv.id === activeId;
            return (
              <div
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-xs transition-colors ${
                  isActive
                    ? 'bg-[#121824] border border-echo-cyan/30 text-white shadow-[0_0_8px_rgba(0,240,255,0.1)]'
                    : 'text-gray-400 hover:bg-[#0E121B] hover:text-gray-200 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-echo-cyan' : 'text-echo-muted'}`} />
                  <span className="truncate">{conv.title}</span>
                </div>
                <button
                  onClick={(e) => onDelete(conv.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-echo-danger rounded transition-opacity"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Navigation Tools */}
      <div className="p-2 border-t border-echo-border space-y-1 text-xs">
        <button
          onClick={onOpenControlPanel}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-gray-300 hover:text-white hover:bg-[#0F1420] transition-colors border border-echo-border/50"
        >
          <div className="flex items-center gap-2.5">
            <Sliders className="w-4 h-4 text-echo-cyan" />
            <span className="font-medium text-white">Desktop Control</span>
          </div>
          {pendingApprovalsCount > 0 ? (
            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-echo-warning text-echo-void text-[10px] font-bold animate-pulse">
              <ShieldAlert className="w-3 h-3" /> {pendingApprovalsCount}
            </span>
          ) : (
            <span className="text-[10px] px-1 rounded bg-[#161B22] text-echo-cyan font-mono">20 Tools</span>
          )}
        </button>

        <button
          onClick={onOpenMonitor}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors border ${
            monitorAlertCount > 0
              ? 'bg-[#141007] border-echo-warning/30 text-white hover:border-echo-warning/60'
              : 'text-gray-400 hover:text-white hover:bg-[#0F1420] border-transparent'
          }`}
          title="Open the system monitoring dashboard"
        >
          <div className="flex items-center gap-2.5">
            <Radar
              className={`w-4 h-4 ${
                monitorAlertCount > 0
                  ? monitorSeverity === 'critical'
                    ? 'text-echo-danger'
                    : 'text-echo-warning'
                  : 'text-echo-cyan'
              }`}
            />
            <span>System Monitor</span>
          </div>
          {monitorAlertCount > 0 ? (
            <span
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold font-mono ${MONITOR_BADGE[monitorSeverity]}`}
            >
              <ShieldAlert className="w-3 h-3" /> {monitorAlertCount}
            </span>
          ) : (
            <span
              className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[#161B22] font-mono ${
                monitorRunning ? 'text-echo-success' : 'text-echo-muted'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  monitorRunning ? 'bg-echo-success animate-pulse' : 'bg-echo-muted'
                }`}
              />
              {monitorRunning ? 'LIVE' : 'IDLE'}
            </span>
          )}
        </button>

        <button
          onClick={onOpenRemote}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors border ${
            remoteState === 'PAUSED'
              ? 'bg-[#141007] border-echo-warning/30 text-white hover:border-echo-warning/60'
              : 'text-gray-400 hover:text-white hover:bg-[#0F1420] border-transparent'
          }`}
          title="Open the Telegram remote relay"
        >
          <div className="flex items-center gap-2.5">
            <Satellite
              className={`w-4 h-4 ${
                remoteState === 'PAUSED'
                  ? 'text-echo-warning'
                  : remoteState === 'LINKED'
                  ? 'text-echo-cyan'
                  : 'text-echo-muted'
              }`}
            />
            <span>Remote Relay</span>
          </div>
          <span
            className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[#161B22] font-mono ${REMOTE_TONE[remoteState].chip}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${REMOTE_TONE[remoteState].dot}`} />
            {remoteState}
            {remoteQueueCount > 0 && <span className="text-echo-cyan">·{remoteQueueCount}</span>}
          </span>
        </button>

        <button
          onClick={onOpenFiles}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#0F1420] transition-colors"
          title="Open file intelligence"
        >
          <div className="flex items-center gap-2.5">
            <FolderSearch className="w-4 h-4 text-echo-cyan" />
            <span>File Intelligence</span>
          </div>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#161B22] text-echo-cyan font-mono">
            LOCAL
          </span>
        </button>

        <button
          onClick={onOpenTasks}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#0F1420] transition-colors"
        >
          <CheckSquare className="w-4 h-4 text-echo-cyan" />
          <span>Tasks & Goals</span>
        </button>

        <button
          onClick={onOpenMemory}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#0F1420] transition-colors"
        >
          <Brain className="w-4 h-4 text-echo-blue" />
          <span>Persistent Memory</span>
        </button>

        <div className="flex items-center justify-between px-3 py-1.5 text-gray-500 hover:text-gray-400 text-xs cursor-not-allowed">
          <div className="flex items-center gap-2.5">
            <Zap className="w-4 h-4 text-echo-purple opacity-70" />
            <span>Automations</span>
          </div>
          <span className="text-[10px] px-1 rounded bg-[#161B22] text-gray-500 font-mono">Stage 11</span>
        </div>

        <button
          onClick={onOpenSettings}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#0F1420] transition-colors"
        >
          <SettingsIcon className="w-4 h-4 text-echo-muted" />
          <span>Settings</span>
        </button>
      </div>

      {/* Status Bar */}
      <div className="p-3 border-t border-echo-border bg-[#05070A] text-[11px] font-mono text-echo-muted flex items-center justify-between">
        <div className="flex items-center gap-1.5 truncate">
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-echo-success' : 'bg-echo-danger'}`} />
          <span>{isConnected ? status?.ai_provider || 'Connected' : 'Offline'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`flex items-center gap-1 ${monitorRunning ? 'text-echo-cyan' : 'text-echo-muted'}`}
            title={monitorRunning ? 'System monitoring active' : 'System monitoring idle'}
          >
            <Radar className="w-3 h-3" />
            {monitorRunning ? 'MON' : '—'}
          </span>
          <span
            className={`flex items-center gap-1 ${
              voiceMuted ? 'text-echo-warning' : voiceRunning ? 'text-echo-cyan' : 'text-echo-muted'
            }`}
            title={
              voiceMuted
                ? 'Microphone muted'
                : voiceRunning
                ? 'Microphone open'
                : 'Microphone closed'
            }
          >
            {voiceMuted ? <MicOff className="w-3 h-3" /> : <Mic className="w-3 h-3" />}
            {voiceRunning ? (voiceMuted ? 'MUTED' : 'MIC') : 'OFF'}
          </span>
          <span>{status?.database === 'connected' ? 'WAL' : 'ERR'}</span>
        </div>
      </div>
    </aside>
  );
};
