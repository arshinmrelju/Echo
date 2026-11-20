import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Sparkles } from 'lucide-react';

interface MessageInputProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
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

