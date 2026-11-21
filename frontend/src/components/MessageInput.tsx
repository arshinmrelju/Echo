import React, { useState, useRef, useEffect } from 'react';
import { Mic, MicOff, Send, Square } from 'lucide-react';
import { VoiceState } from '../types';

interface MessageInputProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  voiceRunning?: boolean;
  voiceState?: VoiceState;
  isVoiceOpen?: boolean;
  onToggleVoice?: () => void;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  voiceRunning = false,
  voiceState = 'idle',
  isVoiceOpen = false,
  onToggleVoice,
}) => {
  const [content, setContent] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [content]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (isStreaming && onStop) {
      onStop();
      return;
    }
    const trimmed = content.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setContent('');
  };

  return (
    <div className="p-4 border-t border-echo-border bg-[#080B10]/95 backdrop-blur-md">
      <div className="relative flex items-end gap-2 p-2 rounded-xl border border-echo-border bg-echo-surface focus-within:border-echo-cyan/60 transition-colors shadow-inner">
        {onToggleVoice && (
          <button
            onClick={onToggleVoice}
            className={`relative p-2 rounded-lg border transition-colors ${
              isVoiceOpen
                ? 'bg-echo-cyan/20 border-echo-cyan/60 text-echo-cyan'
                : voiceRunning
                ? 'bg-echo-cyan/10 border-echo-cyan/30 text-echo-cyan'
                : 'border-echo-border text-echo-muted hover:text-white hover:border-gray-600'
            }`}
            title={
              voiceRunning
                ? `Voice ${voiceState} · open voice console`
                : 'Open voice console (microphone stays closed until enabled)'
            }
          >
            {voiceRunning && voiceState === 'muted' ? (
              <MicOff className="w-4 h-4" />
            ) : (
              <Mic className="w-4 h-4" />
            )}
            {voiceRunning && (voiceState === 'listening' || voiceState === 'speaking') && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-echo-cyan animate-pulse" />
            )}
          </button>
        )}
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "ECHO is generating response..." : "Ask ECHO anything... (Enter to send, Shift+Enter for newline)"}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent text-sm text-echo-text placeholder-echo-muted focus:outline-none resize-none px-2 py-1 max-h-40 leading-relaxed font-sans"
        />

        {isStreaming ? (
          <button
            onClick={onStop}
            className="p-2 rounded-lg bg-echo-danger/20 border border-echo-danger/40 text-echo-danger hover:bg-echo-danger/30 transition-colors"
            title="Stop generation"
          >
            <Square className="w-4 h-4 fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!content.trim() || disabled}
            className="p-2 rounded-lg bg-echo-cyan/20 border border-echo-cyan/40 text-echo-cyan hover:bg-echo-cyan/30 disabled:opacity-40 disabled:hover:bg-echo-cyan/20 transition-colors"
            title="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};

