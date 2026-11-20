import React from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  Brain,
  CheckSquare,
  Cpu,
  Settings as SettingsIcon,
  Zap,
  Activity,
} from 'lucide-react';
import { Conversation, SystemStatus } from '../types';
import { StatusOrb } from './StatusOrb';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
  onOpenMemory: () => void;
  onOpenTasks: () => void;
  onOpenSettings: () => void;
  onToggleContext: () => void;
  isContextOpen: boolean;
  status: SystemStatus | null;
  isConnected: boolean;
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
  onToggleContext,
  isContextOpen,
  status,
  isConnected,
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
                v0.1
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
        <span>{status?.database === 'connected' ? 'WAL' : 'ERR'}</span>
      </div>
    </aside>
  );
};

