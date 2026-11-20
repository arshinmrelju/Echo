import React, { useEffect, useRef } from 'react';
import { Message } from '../types';
import { MessageItem } from './MessageItem';
import { Bot, Sparkles } from 'lucide-react';

interface MessageListProps {
  messages: Message[];
  onRetry?: () => void;
  isLoading?: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  onRetry,
  isLoading,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, messages.length, messages[messages.length - 1]?.content]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center select-none">
        <div className="w-14 h-14 rounded-2xl bg-echo-surface border border-echo-border flex items-center justify-center text-echo-cyan shadow-cyan-glow mb-4">
          <Bot className="w-7 h-7" />
        </div>
        <h2 className="text-lg font-semibold text-white tracking-wide mb-1">
          ECHO Command Center
        </h2>
        <p className="text-sm text-echo-muted max-w-md mb-6">
          Your personal autonomous AI assistant. Ready to help with system operations, task automation, and persistent memory.
        </p>
        <div className="grid grid-cols-2 gap-3 max-w-lg text-left text-xs">
          <div className="p-3 rounded-lg border border-echo-border bg-[#0B0E14] hover:border-echo-cyan/40 transition-colors">
            <div className="font-semibold text-echo-cyan mb-1 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" /> Recall Context
            </div>
            <div className="text-echo-muted">Ask what ECHO remembers about your projects or preferences.</div>
          </div>
          <div className="p-3 rounded-lg border border-echo-border bg-[#0B0E14] hover:border-echo-cyan/40 transition-colors">
            <div className="font-semibold text-echo-cyan mb-1 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" /> Check Status
            </div>
            <div className="text-echo-muted">Verify core daemon health, database, and active AI model.</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
      {messages.map((message, idx) => (
        <MessageItem
          key={message.id || idx}
          message={message}
          onRetry={onRetry}
          isLastAssistant={idx === messages.length - 1 && message.role === 'assistant'}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

