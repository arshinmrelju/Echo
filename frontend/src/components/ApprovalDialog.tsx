import React from 'react';
import { ShieldAlert, Check, X, AlertTriangle, Terminal } from 'lucide-react';
import { ApprovalRequest } from '../types';

interface ApprovalDialogProps {
  request: ApprovalRequest | null;
  onResolve: (requestId: string, approved: boolean) => void;
  onClose: () => void;
}

export const ApprovalDialog: React.FC<ApprovalDialogProps> = ({ request, onResolve, onClose }) => {
  if (!request) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md select-none p-4 animate-fadeIn">
      <div className="w-full max-w-lg rounded-2xl border border-echo-warning/50 bg-[#0E121B] shadow-[0_0_30px_rgba(255,179,0,0.2)] flex flex-col overflow-hidden">
        {/* Urgent Warning Header */}
        <div className="p-4 border-b border-echo-warning/30 bg-[#161B26] flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-echo-warning font-semibold">
            <ShieldAlert className="w-5 h-5 text-echo-warning" />
            <span className="tracking-wide">Security Gate: Action Approval Required</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 space-y-4 text-xs">
          <div className="flex items-start gap-3 p-3 rounded-lg bg-echo-warning/10 border border-echo-warning/20 text-gray-200">
            <AlertTriangle className="w-4 h-4 text-echo-warning flex-shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              ECHO is requesting permission to execute an action with persistent or external operating system effects.
            </div>
          </div>

          {/* Action Details */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-echo-muted">Requested Tool</div>
            <div className="p-2.5 rounded-lg border border-echo-border bg-[#07090E] flex items-center justify-between">
              <span className="font-mono text-echo-cyan font-semibold text-sm">{request.tool_name}</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-echo-warning/20 text-echo-warning border border-echo-warning/30">
                {request.category}
              </span>
            </div>
            <div className="text-echo-muted text-[11px]">{request.description}</div>
          </div>

          {/* Arguments Inspection */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-echo-muted flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5" /> Parameters & Target
            </div>
            <pre className="p-3 rounded-lg border border-echo-border bg-[#05070A] text-echo-cyan font-mono text-[11px] overflow-x-auto max-h-48 leading-relaxed">
              {JSON.stringify(request.args, null, 2)}
            </pre>
          </div>
        </div>

        {/* Decision Footer */}
        <div className="p-4 border-t border-echo-border flex items-center justify-end gap-3 bg-[#0A0D14]">
          <button
            onClick={() => onResolve(request.id, false)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-echo-danger/40 text-echo-danger hover:bg-echo-danger/20 transition-all font-medium"
          >
            <X className="w-4 h-4" />
            <span>Deny Action</span>
          </button>
          <button
            onClick={() => onResolve(request.id, true)}
            className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-echo-warning text-echo-void font-bold hover:bg-echo-warning/90 transition-all shadow-[0_0_15px_rgba(255,179,0,0.3)]"
          >
            <Check className="w-4 h-4" />
            <span>Approve & Execute</span>
          </button>
        </div>
      </div>
    </div>
  );
};
