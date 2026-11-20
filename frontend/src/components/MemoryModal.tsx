import React, { useState, useEffect } from 'react';
import { X, Brain, Search, Plus, Trash2, ShieldAlert, Sparkles, Filter } from 'lucide-react';
import { MemoryItem } from '../types';
import { apiClient } from '../api/client';

interface MemoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MemoryModal: React.FC<MemoryModalProps> = ({ isOpen, onClose }) => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [isAdding, setIsAdding] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<'fact' | 'project' | 'preference' | 'context'>('fact');

  const loadMemories = async () => {
    try {
      const cat = activeCategory === 'all' ? undefined : activeCategory;
      const data = await apiClient.listMemories(cat, searchQuery.trim() || undefined);
      setMemories(data);
    } catch (e) {
      console.error('Failed to load memories', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadMemories();
    }
  }, [isOpen, activeCategory, searchQuery]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newKey.trim() || !newContent.trim()) return;
    try {
      await apiClient.createMemory({
        category: newCategory,
        key: newKey.trim(),
        content: newContent.trim(),
      });
      setNewKey('');
      setNewContent('');
      setIsAdding(false);
      loadMemories();
    } catch (e) {
      alert('Failed to save memory: ' + String(e));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.deleteMemory(id);
      loadMemories();
    } catch (e) {
      alert('Failed to delete memory: ' + String(e));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm select-none p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-echo-border bg-[#0B0E14] shadow-2xl flex flex-col overflow-hidden max-h-[85vh]">
        {/* Header */}
        <div className="p-4 border-b border-echo-border flex items-center justify-between bg-[#0F1420]">
          <div className="flex items-center gap-2 text-white font-semibold">
            <Brain className="w-4 h-4 text-echo-blue" />
            <span>Persistent Memory & Context Vault</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="p-4 border-b border-echo-border bg-[#080B10] space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search memories via FTS5..."
                className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-echo-border bg-[#0F1420] text-xs text-white placeholder-echo-muted focus:outline-none focus:border-echo-cyan font-mono"
              />
              <Search className="w-3.5 h-3.5 text-echo-muted absolute left-3 top-2.5" />
            </div>
            <button
              onClick={() => setIsAdding(!isAdding)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan text-xs font-medium hover:bg-echo-cyan/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{isAdding ? 'Cancel' : 'Add Memory'}</span>
            </button>
          </div>

          {/* Categories */}
          <div className="flex items-center gap-1.5 text-xs">
            {['all', 'fact', 'project', 'preference', 'context'].map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  activeCategory === cat
                    ? 'bg-echo-cyan/20 text-echo-cyan border border-echo-cyan/40'
                    : 'text-echo-muted hover:text-white bg-[#0F1420] border border-echo-border'
                }`}
              >
                {cat.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Inline Add Form */}
          {isAdding && (
            <div className="p-3 rounded-lg border border-echo-cyan/30 bg-[#0F1420] space-y-2.5 animate-fadeIn">
              <div className="flex gap-2">
                <select
                  value={newCategory}
                  onChange={(e: any) => setNewCategory(e.target.value)}
                  className="px-2.5 py-1.5 rounded-md border border-echo-border bg-[#0B0E14] text-xs text-echo-cyan font-mono focus:outline-none"
                >
                  <option value="fact">Fact</option>
                  <option value="project">Project</option>
                  <option value="preference">Preference</option>
                  <option value="context">Context</option>
                </select>
                <input
                  type="text"
                  placeholder="Key (e.g. project_name, preferred_ide)"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  className="flex-1 px-3 py-1.5 rounded-md border border-echo-border bg-[#0B0E14] text-xs text-white focus:outline-none focus:border-echo-cyan font-mono"
                />
              </div>
              <textarea
                placeholder="Content details to remember..."
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                rows={2}
                className="w-full px-3 py-1.5 rounded-md border border-echo-border bg-[#0B0E14] text-xs text-white focus:outline-none focus:border-echo-cyan resize-none"
              />
              <div className="flex justify-end">
                <button
                  onClick={handleCreate}
                  className="px-3 py-1 rounded-md bg-echo-cyan text-echo-void text-xs font-semibold hover:bg-echo-cyan/90 transition-all shadow-[0_0_8px_rgba(0,240,255,0.3)]"
                >
                  Save Entry
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Memory Items List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 text-xs">
          {memories.length === 0 ? (
            <div className="py-12 text-center text-echo-muted">
              No memories recorded yet in this category.
            </div>
          ) : (
            memories.map((m) => (
              <div
                key={m.id}
                className="group p-3 rounded-lg border border-echo-border bg-[#080B10] hover:border-echo-cyan/30 transition-all space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-echo-blue/20 text-echo-blue font-mono border border-echo-blue/30 uppercase">
                      {m.category}
                    </span>
                    <span className="font-semibold text-white font-mono">{m.key}</span>
                    {m.sensitivity === 'high' && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-echo-danger/20 text-echo-danger font-mono border border-echo-danger/30 flex items-center gap-1">
                        <ShieldAlert className="w-3 h-3" /> Sensitive
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => handleDelete(m.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 text-echo-muted hover:text-echo-danger rounded transition-opacity"
                    title="Forget / Delete memory"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="text-gray-300 leading-relaxed font-sans">{m.content}</div>
                <div className="text-[10px] text-gray-500 font-mono">
                  Updated: {new Date(m.updated_at).toLocaleString()}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

