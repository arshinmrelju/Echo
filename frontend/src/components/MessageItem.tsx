import React, { useState } from 'react';
import { Copy, Check, RotateCcw, User, Bot } from 'lucide-react';
import { Message } from '../types';
import { CodeBlock } from './CodeBlock';

interface MessageItemProps {
  message: Message;
  onRetry?: () => void;
  isLastAssistant?: boolean;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onRetry,
  isLastAssistant,
}) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatTimestamp = (iso: string) => {
    try {
      const date = new Date(iso);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  // Render markdown with code block parsing
  const renderFormattedContent = (text: string) => {
    const parts = [];
    const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: text.slice(lastIndex, match.index),
        });
      }
      parts.push({
        type: 'code',
        language: match[1] || 'text',
        content: match[2].trimEnd(),
      });
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
      parts.push({
        type: 'text',
        content: text.slice(lastIndex),
      });
    }

    return parts.map((part, idx) => {
      if (part.type === 'code') {
        return <CodeBlock key={idx} language={part.language} code={part.content} />;
      }

      // Simple formatting for bold, inline code, and lists
      const lines = part.content.split('\n');
      return (
        <div key={idx} className="space-y-1">
          {lines.map((line, lIdx) => {
            if (!line.trim()) return <div key={lIdx} className="h-2" />;

            // Bullet list
            if (line.startsWith('- ') || line.startsWith('* ')) {
              return (
                <div key={lIdx} className="flex items-start gap-2 pl-2">
                  <span className="text-echo-cyan mt-1">•</span>
                  <span>{renderInlineStyles(line.slice(2))}</span>
                </div>
              );
            }

            return <div key={lIdx}>{renderInlineStyles(line)}</div>;
          })}
        </div>
      );
    });
  };

  const renderInlineStyles = (line: string) => {
    // Basic bold and inline code matching
    const elements: React.ReactNode[] = [];
    const inlineRegex = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
    let last = 0;
    let m;

    while ((m = inlineRegex.exec(line)) !== null) {
      if (m.index > last) {
        elements.push(line.slice(last, m.index));
      }
      if (m[2]) {
        elements.push(<strong key={m.index} className="text-white font-semibold">{m[2]}</strong>);
      } else if (m[3]) {
        elements.push(
          <code key={m.index} className="px-1.5 py-0.5 rounded bg-[#1A2234] text-echo-cyan text-xs font-mono">
            {m[3]}
          </code>
        );
      }
      last = m.index + m[0].length;
    }

    if (last < line.length) {
      elements.push(line.slice(last));
    }

    return elements;
  };

  return (
    <div className={`group flex gap-4 px-4 py-3 rounded-lg transition-colors ${isUser ? 'bg-[#0E131E]/60' : 'bg-transparent hover:bg-[#0E131E]/30'}`}>
      {/* Role Avatar */}
      <div className="flex-shrink-0 pt-0.5">
        {isUser ? (
          <div className="w-7 h-7 rounded-md bg-[#1C2538] border border-echo-border flex items-center justify-center text-echo-muted">
            <User className="w-4 h-4" />
          </div>
        ) : (
          <div className="w-7 h-7 rounded-md bg-[#002D3D] border border-echo-cyan/30 flex items-center justify-center text-echo-cyan shadow-[0_0_8px_rgba(0,240,255,0.2)]">
            <Bot className="w-4 h-4" />
          </div>
        )}
      </div>

      {/* Message Body */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center justify-between text-xs text-echo-muted">
          <div className="flex items-center gap-2">
            <span className={`font-medium ${isUser ? 'text-gray-300' : 'text-echo-cyan font-mono'}`}>
              {isUser ? 'You' : 'ECHO'}
            </span>
            <span className="text-[11px] text-gray-500">{formatTimestamp(message.created_at)}</span>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleCopy}
              className="p-1 hover:text-echo-text rounded hover:bg-echo-border"
              title="Copy message text"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-echo-success" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
            {!isUser && isLastAssistant && onRetry && (
              <button
                onClick={onRetry}
                className="p-1 hover:text-echo-text rounded hover:bg-echo-border"
                title="Retry response"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="text-sm leading-relaxed text-gray-200">
          {renderFormattedContent(message.content)}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-1 bg-echo-cyan animate-pulse align-middle" />
          )}
        </div>
      </div>
    </div>
  );
};

