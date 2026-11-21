import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { MessageInput } from './components/MessageInput';
import { ContextPanel } from './components/ContextPanel';
import { SettingsModal } from './components/SettingsModal';
import { MemoryModal } from './components/MemoryModal';
import { TasksModal } from './components/TasksModal';
import { ControlPanelModal } from './components/ControlPanelModal';
import { SystemDashboard } from './components/SystemDashboard';
import { RemoteRelay } from './components/RemoteRelay';
import { FileIntelligence } from './components/FileIntelligence';
import { ApprovalDialog } from './components/ApprovalDialog';
import { VoiceConsole, VoiceNotice } from './components/VoiceConsole';
import { VoiceSettingsModal } from './components/VoiceSettingsModal';
import {
  ApprovalRequest,
  Conversation,
  Message,
  MonitorCounts,
  MonitorSeverity,
  MonitorStatus,
  RemoteStatus,
  SystemStatus,
  VoiceMode,
  VoiceState,
  VoiceStatus,
  VoiceTranscript,
} from './types';
import { apiClient } from './api/client';
import { echoWs } from './api/ws';
import { AlertCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isContextOpen, setIsContextOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  const [isTasksOpen, setIsTasksOpen] = useState(false);
  const [isControlPanelOpen, setIsControlPanelOpen] = useState(false);
  const [isMonitorOpen, setIsMonitorOpen] = useState(false);
  const [isRemoteOpen, setIsRemoteOpen] = useState(false);
  const [isFilesOpen, setIsFilesOpen] = useState(false);
  const [activeApproval, setActiveApproval] = useState<ApprovalRequest | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [remoteStatus, setRemoteStatus] = useState<RemoteStatus | null>(null);
  const [monitorCounts, setMonitorCounts] = useState<MonitorCounts>({
    info: 0,
    notice: 0,
    warning: 0,
    critical: 0,
    total: 0,
    unacknowledged: 0,
  });
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Voice state
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [voiceTranscript, setVoiceTranscript] = useState<VoiceTranscript | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<VoiceNotice | null>(null);
  const [isVoiceConsoleOpen, setIsVoiceConsoleOpen] = useState(false);
  const [isVoiceSettingsOpen, setIsVoiceSettingsOpen] = useState(false);
  const noticeTimer = useRef<any>(null);
  const activeConversationRef = useRef<string | null>(null);

  useEffect(() => {
    activeConversationRef.current = activeConversationId;
  }, [activeConversationId]);

  // Bind spoken turns to the conversation the user is looking at.
  useEffect(() => {
    if (activeConversationId && voiceStatus?.running) {
      echoWs.voiceSetConversation(activeConversationId);
    }
  }, [activeConversationId, voiceStatus?.running]);

  const showVoiceNotice = useCallback((kind: VoiceNotice['kind'], text: string, ttl = 4200) => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    setVoiceNotice({ kind, text });
    noticeTimer.current = setTimeout(() => setVoiceNotice(null), ttl);
  }, []);

  const handleMonitorBadgeChange = useCallback((counts: MonitorCounts, running: boolean) => {
    setMonitorCounts(counts);
    setMonitorRunning(running);
  }, []);

  // Initial Load
  useEffect(() => {
    loadStatus();
    loadVoiceStatus();
    loadMonitoringBadge();
    loadRemoteBadge();
    loadConversations();
    checkPendingApprovals();
    const interval = setInterval(() => {
      loadStatus();
      loadVoiceStatus();
      checkPendingApprovals();
    }, 5000);
    const monitorInterval = setInterval(loadMonitoringBadge, 30000);
    const remoteInterval = setInterval(loadRemoteBadge, 30000);
    return () => {
      clearInterval(interval);
      clearInterval(monitorInterval);
      clearInterval(remoteInterval);
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    };
  }, []);

  const loadStatus = async () => {
    try {
      const s = await apiClient.getStatus();
      setSystemStatus(s);
      setIsConnected(true);
      setErrorMessage(null);
    } catch {
      setIsConnected(false);
      setErrorMessage('Backend daemon is offline. Please launch the ECHO backend service.');
    }
  };

  const loadVoiceStatus = async () => {
    try {
      const status = await apiClient.getVoiceStatus();
      setVoiceStatus(status);
      if (!status.running) setVoiceLevel(0);
    } catch {
      // Voice status is optional while the daemon is starting or offline.
    }
  };

  const loadMonitoringBadge = async () => {
    try {
      const monitor = await apiClient.getMonitoringStatus();
      setMonitorCounts(monitor.counts);
      setMonitorRunning(monitor.running);
    } catch {
      // Monitoring status is optional while the daemon is starting or offline.
    }
  };

  const loadRemoteBadge = async () => {
    try {
      const remote = await apiClient.getRemoteStatus();
      setRemoteStatus(remote);
    } catch {
      // Remote relay status is optional while the daemon is starting or offline.
    }
  };

  const checkPendingApprovals = async () => {
    try {
      const list = await apiClient.listApprovals();
      setPendingApprovals(list);
      // Auto-popup first pending approval if not currently open
      if (list.length > 0 && !activeApproval) {
        setActiveApproval(list[0]);
      }
    } catch {
      // quiet fallback
    }
  };

  const loadConversations = async () => {
    try {
      const list = await apiClient.listConversations();
      setConversations(list);
      if (list.length > 0 && !activeConversationId) {
        selectConversation(list[0].id);
      }
    } catch (e) {
      console.error('Failed to load conversations', e);
    }
  };

  const selectConversation = async (id: string) => {
    activeConversationRef.current = id;
    setActiveConversationId(id);
    try {
      const detail = await apiClient.getConversation(id);
      setMessages(detail.messages || []);
    } catch (e) {
      console.error('Failed to load messages', e);
    }
  };

  const handleNewConversation = async () => {
    try {
      const conv = await apiClient.createConversation('New Chat');
      setConversations((prev) => [conv, ...prev]);
      activeConversationRef.current = conv.id;
      setActiveConversationId(conv.id);
      setMessages([]);
    } catch (e) {
      console.error('Failed to create new conversation', e);
    }
  };

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiClient.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConversationId === id) {
        const remaining = conversations.filter((c) => c.id !== id);
        if (remaining.length > 0) {
          selectConversation(remaining[0].id);
        } else {
          activeConversationRef.current = null;
          setActiveConversationId(null);
          setMessages([]);
        }
      }
    } catch (e) {
      console.error('Failed to delete conversation', e);
    }
  };

  // WebSocket Message Handling
  useEffect(() => {
    const unsubscribe = echoWs.subscribe((data) => {
      switch (data.type) {
        case 'ws_connected':
          setIsConnected(true);
          break;
        case 'ws_disconnected':
          setIsConnected(false);
          break;
        case 'message_received': {
          const incoming: Message | undefined = data.message;
          const incomingConv: string | undefined = data.conversation_id;
          const convChanged = Boolean(incomingConv && incomingConv !== activeConversationRef.current);
          if (convChanged && incomingConv) {
            activeConversationRef.current = incomingConv;
            setActiveConversationId(incomingConv);
            loadConversations();
            setMessages(incoming ? [incoming] : []);
            if (data.source === 'voice') setIsVoiceConsoleOpen(true);
          } else if (data.source === 'voice' && incoming) {
            setMessages((prev) =>
              prev.some((m) => m.id === incoming.id) ? prev : [...prev, incoming]
            );
          }
          break;
        }
        case 'stream_start': {
          setIsStreaming(true);
          const bubble: Message = {
            id: data.message_id,
            conversation_id: data.conversation_id,
            role: 'assistant',
            content: '',
            created_at: data.created_at,
            isStreaming: true,
          };
          if (data.conversation_id && data.conversation_id !== activeConversationRef.current) {
            activeConversationRef.current = data.conversation_id;
            setActiveConversationId(data.conversation_id);
            loadConversations();
            setMessages([bubble]);
          } else {
            setMessages((prev) => [...prev, bubble]);
          }
          break;
        }
        case 'stream_chunk':
          if (data.conversation_id && data.conversation_id !== activeConversationRef.current) break;
          setMessages((prev) => {
            const copy = [...prev];
            const idx = copy.findIndex(
              (m) => m.id === data.message_id && m.role === 'assistant' && m.isStreaming
            );
            const target = idx >= 0 ? idx : copy.length - 1;
            const last = copy[target];
            if (last && last.role === 'assistant' && last.isStreaming) {
              copy[target] = {
                ...last,
                content: last.content + data.content,
              };
            }
            return copy;
          });
          break;
        case 'stream_end':
        case 'stream_cancelled':
          setIsStreaming(false);
          if (data.conversation_id && data.conversation_id !== activeConversationRef.current) {
            loadConversations();
            break;
          }
          setMessages((prev) => {
            const copy = [...prev];
            const idx = copy.findIndex((m) => m.id === data.message_id);
            const target = idx >= 0 ? idx : copy.length - 1;
            const last = copy[target];
            if (last && last.role === 'assistant') {
              copy[target] = {
                ...last,
                isStreaming: false,
                content: data.full_content || data.partial_content || last.content,
              };
            }
            return copy;
          });
          loadConversations();
          break;
        case 'stream_error':
          setIsStreaming(false);
          if (data.conversation_id && data.conversation_id !== activeConversationRef.current) break;
          setMessages((prev) => {
            const copy = [...prev];
            const idx = copy.findIndex((m) => m.id === data.message_id);
            const target = idx >= 0 ? idx : copy.length - 1;
            const last = copy[target];
            if (last && last.role === 'assistant') {
              copy[target] = {
                ...last,
                isStreaming: false,
                content: `⚠️ **AI Error:** ${data.error}`,
              };
            }
            return copy;
          });
          break;

        // --- System monitoring --------------------------------------------
        case 'monitor_status': {
          const next = data as MonitorStatus;
          if (next.counts) setMonitorCounts(next.counts);
          setMonitorRunning(Boolean(next.running));
          break;
        }
        case 'monitor_snapshot': {
          const counts = data.snapshot?.alert_counts as MonitorCounts | undefined;
          if (counts) setMonitorCounts(counts);
          setMonitorRunning(true);
          break;
        }

        // --- Remote relay ------------------------------------------------
        case 'remote_status':
          setRemoteStatus(data as RemoteStatus);
          break;
        case 'remote_command':
        case 'remote_notification_queued':
        case 'remote_delivery':
        case 'remote_approval_requested':
          loadRemoteBadge();
          break;

        // --- Voice events -------------------------------------------------
        case 'voice_status':
          setVoiceStatus(data as VoiceStatus);
          break;
        case 'voice_state': {
          const next = data.state as VoiceState;
          setVoiceStatus((prev) =>
            prev
              ? {
                  ...prev,
                  state: next,
                  capturing: next === 'listening',
                  speaking: next === 'speaking',
                  muted: next === 'muted',
                }
              : prev
          );
          break;
        }
        case 'voice_session':
          setVoiceStatus((prev) =>
            prev
              ? {
                  ...prev,
                  running: Boolean(data.active),
                  enabled: Boolean(data.active),
                  wake_active:
                    Boolean(data.active) && (data.mode ?? prev.mode) === 'wake_word',
                  mode: data.mode ?? prev.mode,
                  muted: false,
                }
              : prev
          );
          if (!data.active) {
            setVoiceLevel(0);
          }
          break;
        case 'voice_level':
          setVoiceLevel(Number(data.level) || 0);
          break;
        case 'voice_transcript':
          setVoiceTranscript({
            text: data.cleared ? '' : data.text || '',
            isPartial: Boolean(data.is_partial),
            confidence: data.confidence,
            dropped: Boolean(data.dropped),
            cleared: Boolean(data.cleared),
            receivedAt: Date.now(),
          });
          break;
        case 'voice_wake_word':
          showVoiceNotice(
            'wake',
            data.command
              ? `Wake word detected — command captured.`
              : `Wake word detected — listening.`
          );
          setVoiceTranscript(null);
          break;
        case 'voice_speaking':
          setVoiceStatus((prev) =>
            prev ? { ...prev, speaking: Boolean(data.active) } : prev
          );
          break;
        case 'voice_interrupted':
          showVoiceNotice('interrupted', 'Interrupted — listening again.');
          break;
        case 'voice_conversation':
          if (data.conversation_id) {
            setIsVoiceConsoleOpen(true);
          }
          break;
        case 'voice_conversation_dismissed':
          setVoiceTranscript(null);
          showVoiceNotice('info', 'Conversation ended. Microphone is waiting.');
          break;
        case 'voice_conversation_timeout':
          showVoiceNotice('info', `Conversation paused after ${data.seconds}s of silence.`);
          break;
        case 'voice_listen_timeout':
          setVoiceTranscript(null);
          showVoiceNotice('info', 'No command heard — back to standby.');
          break;
        case 'voice_privacy':
          showVoiceNotice('info', data.message || 'Recording storage changed.');
          break;
        case 'voice_error':
          showVoiceNotice('error', data.message || 'Voice system error.', 7000);
          break;
        case 'voice_engine':
          if (data.ready === false) {
            showVoiceNotice('error', 'Speech recognition model is unavailable.', 7000);
          }
          break;
      }
    });

    return unsubscribe;
  }, [activeConversationId]);

  const handleSendMessage = (text: string) => {
    const userMsg: Message = {
      id: String(Date.now()),
      conversation_id: activeConversationId || '',
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    echoWs.sendChatMessage(text, activeConversationId || undefined);
  };

  const handleStopGeneration = () => {
    echoWs.stopGeneration(activeConversationId || undefined);
    setIsStreaming(false);
  };

  const handleRetry = () => {
    if (messages.length < 2) return;
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUserMsg) {
      handleSendMessage(lastUserMsg.content);
    }
  };

  const handleResolveApproval = async (requestId: string, approved: boolean) => {
    try {
      await apiClient.resolveApproval(requestId, approved);
      setActiveApproval(null);
      checkPendingApprovals();
    } catch (e) {
      alert('Error resolving approval: ' + String(e));
    }
  };

  // ------------------------------------------------------------------
  // Voice controls
  // ------------------------------------------------------------------

  const handleVoiceStart = async () => {
    setIsVoiceConsoleOpen(true);
    setVoiceTranscript(null);
    try {
      const res = await apiClient.startVoice();
      setVoiceStatus(res.status);
      if (!res.success) {
        showVoiceNotice('error', res.error || 'Microphone could not be opened.', 8000);
      } else {
        showVoiceNotice('info', 'Microphone open. ECHO can hear you.');
      }
    } catch (e) {
      showVoiceNotice('error', 'Could not reach the voice service.', 8000);
    }
  };

  const handleVoiceStop = async () => {
    try {
      const res = await apiClient.stopVoice();
      setVoiceStatus(res.status);
    } catch {
      // Keep the last known state; polling will reconcile.
    }
    setVoiceLevel(0);
    setVoiceTranscript(null);
    showVoiceNotice('info', 'Microphone closed.');
  };

  const handleVoiceMute = async () => {
    try {
      const res = await apiClient.muteVoice();
      setVoiceStatus(res.status);
      setVoiceLevel(0);
      showVoiceNotice('info', 'Microphone muted. Nothing is being captured.');
    } catch {
      showVoiceNotice('error', 'Could not mute the microphone.');
    }
  };

  const handleVoiceUnmute = async () => {
    try {
      const res = await apiClient.unmuteVoice();
      setVoiceStatus(res.status);
      if (!res.success) {
        showVoiceNotice('error', res.error || 'Could not reopen the microphone.');
      }
    } catch {
      showVoiceNotice('error', 'Could not unmute the microphone.');
    }
  };

  const handleVoiceStopSpeaking = async () => {
    try {
      const res = await apiClient.stopSpeaking();
      setVoiceStatus(res.status);
      showVoiceNotice('info', 'Speech output interrupted.');
    } catch {
      showVoiceNotice('error', 'Could not stop speech output.');
    }
  };

  const handleVoiceDismiss = async () => {
    try {
      const res = await apiClient.dismissVoice();
      setVoiceStatus(res.status);
    } catch {
      // no-op
    }
    setVoiceTranscript(null);
  };

  const handleVoiceModeChange = async (mode: VoiceMode) => {
    const label =
      mode === 'push_to_talk' ? 'Push to talk' : mode === 'wake_word' ? 'Wake word' : 'Continuous';
    try {
      const res = await apiClient.updateVoiceSettings({ mode });
      setVoiceStatus(res.status);
      showVoiceNotice('info', `Voice mode: ${label}.`);
    } catch {
      showVoiceNotice('error', 'Could not change the voice mode.');
    }
  };

  const handlePttStart = () => {
    setIsVoiceConsoleOpen(true);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    setVoiceNotice(null);
    setVoiceTranscript({ text: '', isPartial: false, receivedAt: Date.now() });
    echoWs.voicePushToTalkStart(activeConversationRef.current || undefined);
  };

  const handlePttStop = () => {
    echoWs.voicePushToTalkStop();
  };

  const handleVoiceSaved = (status: VoiceStatus) => {
    setVoiceStatus(status);
  };

  const voiceMuted = voiceStatus?.muted ?? false;

  const monitorSeverity: MonitorSeverity =
    monitorCounts.critical > 0
      ? 'critical'
      : monitorCounts.warning > 0
      ? 'warning'
      : monitorCounts.notice > 0
      ? 'notice'
      : 'info';
  const monitorAlertCount = monitorCounts.unacknowledged || monitorCounts.total;

  const remoteState: 'LINKED' | 'OFFLINE' | 'IDLE' | 'PAUSED' = remoteStatus?.paused
    ? 'PAUSED'
    : remoteStatus?.running && remoteStatus?.connected
    ? 'LINKED'
    : remoteStatus?.enabled
    ? 'OFFLINE'
    : 'IDLE';
  const remoteQueueCount = remoteStatus?.queue?.queued ?? 0;

  return (
    <div className="flex h-screen w-screen bg-echo-void text-echo-text overflow-hidden font-sans">
      {/* Left Sidebar */}
      <Sidebar
        conversations={conversations}
        activeId={activeConversationId}
        onSelect={selectConversation}
        onNew={handleNewConversation}
        onDelete={handleDeleteConversation}
        onOpenMemory={() => setIsMemoryOpen(true)}
        onOpenTasks={() => setIsTasksOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenControlPanel={() => setIsControlPanelOpen(true)}
        onOpenMonitor={() => setIsMonitorOpen(true)}
        onOpenRemote={() => setIsRemoteOpen(true)}
        onOpenFiles={() => setIsFilesOpen(true)}
        onToggleContext={() => setIsContextOpen(!isContextOpen)}
        isContextOpen={isContextOpen}
        status={systemStatus}
        isConnected={isConnected}
        pendingApprovalsCount={pendingApprovals.length}
        voiceRunning={voiceStatus?.running ?? false}
        voiceMuted={voiceMuted}
        monitorRunning={monitorRunning}
        monitorAlertCount={monitorAlertCount}
        monitorSeverity={monitorSeverity}
        remoteState={remoteState}
        remoteQueueCount={remoteQueueCount}
      />

      {/* Main Chat Stage */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#06080D]">
        {/* Connection Offline Banner */}
        {!isConnected && (
          <div className="px-4 py-2 bg-echo-danger/10 border-b border-echo-danger/30 text-echo-danger text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMessage || 'Connection lost to daemon. Retrying...'}</span>
          </div>
        )}

        {/* Message Stream */}
        <MessageList
          messages={messages}
          onRetry={handleRetry}
          isLoading={isStreaming}
        />

        {/* Voice Console */}
        {isVoiceConsoleOpen && (
          <VoiceConsole
            status={voiceStatus}
            level={voiceLevel}
            transcript={voiceTranscript}
            notice={voiceNotice}
            isConnected={isConnected}
            onStart={handleVoiceStart}
            onStop={handleVoiceStop}
            onMute={handleVoiceMute}
            onUnmute={handleVoiceUnmute}
            onStopSpeaking={handleVoiceStopSpeaking}
            onDismiss={handleVoiceDismiss}
            onOpenSettings={() => setIsVoiceSettingsOpen(true)}
            onModeChange={handleVoiceModeChange}
            onPttStart={handlePttStart}
            onPttStop={handlePttStop}
            onClose={() => setIsVoiceConsoleOpen(false)}
          />
        )}

        {/* Bottom Prompt Bar */}
        <MessageInput
          onSend={handleSendMessage}
          onStop={handleStopGeneration}
          isStreaming={isStreaming}
          disabled={!isConnected}
          voiceRunning={voiceStatus?.running ?? false}
          voiceState={voiceStatus?.state ?? 'idle'}
          isVoiceOpen={isVoiceConsoleOpen}
          onToggleVoice={() => setIsVoiceConsoleOpen((v) => !v)}
        />
      </main>

      {/* Right Telemetry / Context Drawer */}
      {isContextOpen && (
        <ContextPanel
          status={systemStatus}
          onClose={() => setIsContextOpen(false)}
        />
      )}

      {/* Modals */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSaved={loadStatus}
      />

      <VoiceSettingsModal
        isOpen={isVoiceSettingsOpen}
        onClose={() => setIsVoiceSettingsOpen(false)}
        onSaved={handleVoiceSaved}
      />

      <MemoryModal
        isOpen={isMemoryOpen}
        onClose={() => setIsMemoryOpen(false)}
      />

      <TasksModal
        isOpen={isTasksOpen}
        onClose={() => setIsTasksOpen(false)}
      />

      <ControlPanelModal
        isOpen={isControlPanelOpen}
        onClose={() => setIsControlPanelOpen(false)}
        onTriggerApproval={(req) => setActiveApproval(req)}
      />

      <SystemDashboard
        isOpen={isMonitorOpen}
        onClose={() => setIsMonitorOpen(false)}
        onBadgeChange={handleMonitorBadgeChange}
      />

      <RemoteRelay
        isOpen={isRemoteOpen}
        onClose={() => setIsRemoteOpen(false)}
        onBadgeChange={setRemoteStatus}
      />

      <FileIntelligence
        isOpen={isFilesOpen}
        onClose={() => setIsFilesOpen(false)}
      />

      <ApprovalDialog
        request={activeApproval}
        onResolve={handleResolveApproval}
        onClose={() => setActiveApproval(null)}
      />
    </div>
  );
};
export default App;
