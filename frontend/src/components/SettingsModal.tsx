import React, { useState, useEffect } from 'react';
import { X, Check, Key, Sliders, Server, Save } from 'lucide-react';
import { AppSettings } from '../types';
import { apiClient } from '../api/client';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [provider, setProvider] = useState('mock');
  const [model, setModel] = useState('echo-fast-v1');
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (isOpen) {
      apiClient.getSettings().then((s) => {
        setSettings(s);
        setProvider(s.ai_provider);
        setModel(s.ai_model);
        setApiBase(s.ai_api_base || '');
        setTemperature(s.ai_temperature);
        setMaxTokens(s.ai_max_tokens);
      });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const payload: Partial<AppSettings> = {
        ai_provider: provider,
        ai_model: model,
        ai_api_base: apiBase.trim() || undefined,
        ai_temperature: Number(temperature),
        ai_max_tokens: Number(maxTokens),
      };
      if (apiKey.trim()) {
        payload.ai_api_key = apiKey.trim();
      }
      await apiClient.updateSettings(payload);
      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        if (onSaved) onSaved();
        onClose();
      }, 1000);
    } catch (e) {
      alert('Failed to save settings: ' + String(e));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm select-none p-4">
      <div className="w-full max-w-lg rounded-2xl border border-echo-border bg-[#0B0E14] shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-echo-border flex items-center justify-between bg-[#0F1420]">
          <div className="flex items-center gap-2 text-white font-semibold">
            <Sliders className="w-4 h-4 text-echo-cyan" />
            <span>ECHO Configuration & AI Providers</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 overflow-y-auto max-h-[75vh] text-xs">
          {/* Provider Selection */}
          <div className="space-y-1.5">
            <label className="font-semibold text-gray-200">AI Model Provider</label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: 'mock', name: 'Mock / Offline', desc: 'Fast, deterministic test engine' },
                { id: 'ollama', name: 'Local Ollama', desc: '127.0.0.1:11434 local models' },
                { id: 'openai', name: 'OpenAI / Compatible', desc: 'OpenAI, OpenRouter, LM Studio' },
              ].map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setProvider(p.id);
                    if (p.id === 'ollama' && model === 'echo-fast-v1') setModel('llama3.2');
                    if (p.id === 'openai' && model === 'echo-fast-v1') setModel('gpt-4o-mini');
                  }}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    provider === p.id
                      ? 'border-echo-cyan bg-echo-cyan/10 text-white shadow-[0_0_10px_rgba(0,240,255,0.15)]'
                      : 'border-echo-border bg-[#07090E] text-gray-400 hover:border-gray-600'
                  }`}
                >
                  <div className="font-medium text-white mb-0.5">{p.name}</div>
                  <div className="text-[10px] text-echo-muted leading-tight">{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Model Name */}
          <div className="space-y-1.5">
            <label className="font-semibold text-gray-200">Model Identifier</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o, llama3.2, mistral"
              className="w-full px-3 py-2 rounded-lg border border-echo-border bg-[#07090E] text-white focus:outline-none focus:border-echo-cyan font-mono"
            />
          </div>

          {/* API Key */}
          {provider === 'openai' && (
            <div className="space-y-1.5">
              <label className="font-semibold text-gray-200 flex items-center justify-between">
                <span>API Key</span>
                {settings?.ai_api_key_configured && (
                  <span className="text-[10px] text-echo-success flex items-center gap-1 font-mono">
                    <Check className="w-3 h-3" /> Key is configured
                  </span>
                )}
              </label>
              <div className="relative">
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={settings?.ai_api_key_configured ? '••••••••••••••••••••••••' : 'sk-...'}
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-echo-border bg-[#07090E] text-white focus:outline-none focus:border-echo-cyan font-mono"
                />
                <Key className="w-4 h-4 text-echo-muted absolute left-3 top-2.5" />
              </div>
              <div className="text-[11px] text-echo-muted">
                Keys are stored securely in local database settings and never exposed in logs.
              </div>
            </div>
          )}

          {/* API Base URL */}
          {(provider === 'openai' || provider === 'ollama') && (
            <div className="space-y-1.5">
              <label className="font-semibold text-gray-200">API Endpoint Base URL (Optional)</label>
              <div className="relative">
                <input
                  type="text"
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder={provider === 'ollama' ? 'http://127.0.0.1:11434' : 'https://api.openai.com/v1'}
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-echo-border bg-[#07090E] text-white focus:outline-none focus:border-echo-cyan font-mono"
                />
                <Server className="w-4 h-4 text-echo-muted absolute left-3 top-2.5" />
              </div>
            </div>
          )}

          {/* Temperature & Token Controls */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <div className="flex justify-between font-semibold text-gray-200">
                <span>Temperature</span>
                <span className="text-echo-cyan font-mono">{temperature}</span>
              </div>
              <input
                type="range"
                min="0"
                max="1.5"
                step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-echo-cyan cursor-pointer"
              />
            </div>

            <div className="space-y-1.5">
              <label className="font-semibold text-gray-200">Max Tokens</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 1024)}
                className="w-full px-3 py-1.5 rounded-lg border border-echo-border bg-[#07090E] text-white focus:outline-none focus:border-echo-cyan font-mono"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-echo-border flex items-center justify-between bg-[#0F1420]">
          <div className="text-[11px] text-echo-muted font-mono truncate max-w-[240px]">
            Data Dir: {settings?.data_dir || 'Default'}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-echo-border hover:bg-echo-border text-gray-300 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-echo-cyan text-echo-void font-semibold hover:bg-echo-cyan/90 transition-all shadow-[0_0_12px_rgba(0,240,255,0.3)] disabled:opacity-50"
            >
              {saveSuccess ? (
                <>
                  <Check className="w-4 h-4" />
                  <span>Saved!</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{isSaving ? 'Saving...' : 'Apply Changes'}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

