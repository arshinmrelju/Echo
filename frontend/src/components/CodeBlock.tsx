import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

interface CodeBlockProps {
  language?: string;
  code: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ language = 'text', code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 rounded-lg border border-echo-border overflow-hidden bg-[#0A0D14]">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0F1420] border-b border-echo-border text-xs text-echo-muted font-mono">
        <span className="uppercase text-echo-cyan">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 hover:text-echo-text transition-colors"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-echo-success" />
              <span className="text-echo-success">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-xs font-mono leading-relaxed text-gray-200">
        <code>{code}</code>
      </pre>
    </div>
  );
};

