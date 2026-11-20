import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { MessageInput } from './components/MessageInput';
import { ContextPanel } from './components/ContextPanel';
import { SettingsModal } from './components/SettingsModal';
import { MemoryModal } from './components/MemoryModal';
import { TasksModal } from './components/TasksModal';
import { Conversation, Message, SystemStatus } from './types';
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
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Initial Load
  useEffect(() => {
    loadStatus();
    loadConversations();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
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
        case 'message_received':
          if (!activeConversationId) {
            setActiveConversationId(data.conversation_id);
            loadConversations();
          }
          break;
        case 'stream_start':
          setIsStreaming(true);
          setMessages((prev) => [
            ...prev,
            {
              id: data.message_id,
              conversation_id: data.conversation_id,
              role: 'assistant',
              content: '',
              created_at: data.created_at,
              isStreaming: true,
            },
          ]);
          break;
        case 'stream_chunk':
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant' && last.isStreaming) {
              copy[copy.length - 1] = {
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
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = {
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
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = {
                ...last,
                isStreaming: false,
                content: `⚠️ **AI Error:** ${data.error}`,
              };
            }
            return copy;
          });
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
        onToggleContext={() => setIsContextOpen(!isContextOpen)}
        isContextOpen={isContextOpen}
        status={systemStatus}
        isConnected={isConnected}
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

        {/* Bottom Prompt Bar */}
        <MessageInput
          onSend={handleSendMessage}
          onStop={handleStopGeneration}
          isStreaming={isStreaming}
          disabled={!isConnected}
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

      <MemoryModal
        isOpen={isMemoryOpen}
        onClose={() => setIsMemoryOpen(false)}
      />

      <TasksModal
        isOpen={isTasksOpen}
        onClose={() => setIsTasksOpen(false)}
      />
    </div>
  );
};
export default App;

