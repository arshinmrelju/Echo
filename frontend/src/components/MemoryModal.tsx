import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Archive,
  ArchiveRestore,
  Brain,
  Clock,
  Database,
  Download,
  Eraser,
  Lock,
  Pencil,
  Pin,
  PinOff,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Tag,
  Trash2,
  X,
} from 'lucide-react';
import { MemoryCategory, MemoryItem, MemoryStats } from '../types';
import { ApiError, apiClient } from '../api/client';

interface MemoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type CategoryFilter = MemoryCategory | 'all';

const CATEGORIES: { key: CategoryFilter; label: string; hint: string }[] = [
  { key: 'all', label: 'ALL', hint: 'Every stored entry' },
  { key: 'fact', label: 'FACTS', hint: 'Verified facts' },
  { key: 'preference', label: 'PREFERENCES', hint: 'How you like things' },
  { key: 'project', label: 'PROJECTS', hint: 'Paths, stack, progress' },
  { key: 'task', label: 'TASKS', hint: 'Past and pending work' },
  { key: 'conversation', label: 'CONVERSATIONS', hint: 'Rolling summaries' },
  { key: 'context', label: 'CONTEXT', hint: 'Loose background' },
];

const CATEGORY_TONE: Record<MemoryCategory, string> = {
  fact: 'border-echo-blue/40 bg-echo-blue/10 text-echo-blue',
  preference: 'border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan',
  project: 'border-echo-purple/40 bg-echo-purple/10 text-echo-purple',
  task: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
  conversation: 'border-echo-success/40 bg-echo-success/10 text-echo-success',
  context: 'border-echo-muted/30 bg-echo-muted/10 text-echo-muted',
};

const SOURCE_LABEL: Record<string, string> = {
  user: 'YOU',
  assistant: 'ECHO',
  task: 'TASK ENGINE',
  conversation: 'CHAT SUMMARY',
  system: 'SYSTEM',
};

const formatDate = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

interface Draft {
  category: MemoryCategory;
  key: string;
  content: string;
  confidence: number;
  tags: string;
  pinned: boolean;
  allowSensitive: boolean;
}

const emptyDraft = (): Draft => ({
  category: 'fact',
  key: '',
  content: '',
  confidence: 1,
  tags: '',
  pinned: false,
  allowSensitive: false,
});

const Chip: React.FC<{ label: string; className?: string; icon?: React.ReactNode }> = ({
  label,
  className,
  icon,
}) => (
  <span
    className={`inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded-sm border tracking-wider ${className}`}
  >
    {icon}
    {label}
  </span>
);

export const MemoryModal: React.FC<MemoryModalProps> = ({ isOpen, onClose }) => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [query, setQuery] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [sensitivePrompt, setSensitivePrompt] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [items, nextStats] = await Promise.all([
        apiClient.listMemories({
          category,
          query: query.trim() || undefined,
          includeArchived,
          limit: 300,
        }),
        apiClient.getMemoryStats(),
      ]);
      setMemories(items);
      setStats(nextStats);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load memory.');
    } finally {
      setLoading(false);
    }
  }, [category, query, includeArchived]);

  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(load, query ? 220 : 0);
    return () => clearTimeout(timer);
  }, [isOpen, load, query]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 3600);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!isOpen) {
      setDraft(null);
      setEditingId(null);
      setConfirmClear(false);
      setConfirmDeleteId(null);
      setError(null);
    }
  }, [isOpen]);

  const categoryCount = useMemo(() => {
    const counts: Record<string, number> = { all: stats?.total ?? 0 };
    Object.entries(stats?.by_category ?? {}).forEach(([key, value]) => {
      counts[key] = value;
    });
    return counts;
  }, [stats]);

  if (!isOpen) return null;

  const openCreate = () => {
    setEditingId(null);
    setDraft(emptyDraft());
    setSensitivePrompt(false);
    setError(null);
  };

  const openEdit = (item: MemoryItem) => {
    setEditingId(item.id);
    setDraft({
      category: item.category,
      key: item.key,
      content: item.content,
      confidence: item.confidence,
      tags: item.tags.join(', '),
      pinned: item.pinned,
      allowSensitive: item.permission_granted,
    });
    setSensitivePrompt(false);
    setError(null);
  };

  const parseTags = (value: string) =>
    value
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 12);

  const handleSave = async () => {
    if (!draft) return;
    if (!draft.key.trim() || !draft.content.trim()) {
      setError('A memory needs both a key and content.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        category: draft.category,
        key: draft.key.trim(),
        content: draft.content.trim(),
        confidence: Math.min(1, Math.max(0, draft.confidence)),
        tags: parseTags(draft.tags),
        pinned: draft.pinned,
        allow_sensitive: draft.allowSensitive,
      };
      if (editingId) {
        await apiClient.updateMemory(editingId, payload);
        setNotice('Memory updated.');
      } else {
        await apiClient.createMemory({ ...payload, source: 'user' });
        setNotice('Memory stored.');
      }
      setDraft(null);
      setEditingId(null);
      setSensitivePrompt(false);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        setSensitivePrompt(true);
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : 'Could not save this memory.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleTogglePin = async (item: MemoryItem) => {
    try {
      await apiClient.updateMemory(item.id, { pinned: !item.pinned });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update pin.');
    }
  };

  const handleToggleArchive = async (item: MemoryItem) => {
    try {
      await apiClient.updateMemory(item.id, { archived: !item.archived });
      setNotice(item.archived ? 'Memory restored.' : 'Memory archived.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not archive memory.');
    }
  };

  const handleDelete = async (id: string) => {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id);
      return;
    }
    setBusy(true);
    try {
      await apiClient.deleteMemory(id);
      setConfirmDeleteId(null);
      setNotice('Memory forgotten.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete memory.');
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    try {
      const data = await apiClient.exportMemories();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `echo-memory-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice(`Exported ${data.count} memories.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed.');
    }
  };

  const handleClear = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setBusy(true);
    try {
      const result = await apiClient.clearMemories(category === 'all' ? undefined : category);
      setConfirmClear(false);
      setNotice(`Cleared ${result.removed} memories${category === 'all' ? '' : ` from ${category}`}.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not clear memory.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3">
      <div className="w-full max-w-[1180px] h-[90vh] flex flex-col rounded-lg border border-echo-border bg-[#07090E] shadow-2xl overflow-hidden">
        <header className="border-b border-echo-border bg-[#0B0E14]">
          <div className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-sm border border-echo-blue/40 bg-echo-blue/5 flex items-center justify-center text-echo-blue">
                <Brain className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-mono text-sm tracking-[0.18em] text-white">MEMORY EXPLORER</h2>
                  <Chip label="SQLITE" className="border-echo-muted/30 bg-echo-muted/10 text-echo-muted" icon={<Database className="w-3 h-3" />} />
                  <Chip label="FTS5" className="border-echo-cyan/30 bg-echo-cyan/5 text-echo-cyan" />
                </div>
                <p className="mt-1 font-mono text-[10px] text-echo-muted truncate">
                  ECHO can only recall what is stored here. Inspect, edit, export or forget any entry.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleExport}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-cyan/40 transition-colors font-mono text-[11px]"
                title="Export all memory as JSON"
              >
                <Download className="w-3.5 h-3.5" />
                EXPORT
              </button>
              <button
                onClick={load}
                className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-muted/50 transition-colors"
                title="Reload"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-danger/40 transition-colors"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 border-t border-echo-border text-[10px] font-mono">
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">ENTRIES</span>
              <span className="text-white">{stats?.total ?? memories.length}</span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">PINNED</span>
              <span className="text-echo-cyan">{stats?.pinned ?? 0}</span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">SENSITIVE</span>
              <span className={stats?.sensitive ? 'text-echo-warning' : 'text-echo-success'}>
                {stats?.sensitive ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5">
              <span className="text-echo-muted">UPDATED</span>
              <span className="text-echo-muted">{formatDate(stats?.last_updated_at)}</span>
            </div>
          </div>
        </header>

        <div className="flex-1 flex min-h-0">
          {/* Category rail */}
          <aside className="w-52 border-r border-echo-border bg-[#090C12] flex flex-col">
            <div className="px-3 py-2 border-b border-echo-border font-mono text-[10px] tracking-wider text-echo-muted">
              MEMORY CLASSES
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {CATEGORIES.map((entry) => (
                <button
                  key={entry.key}
                  onClick={() => setCategory(entry.key)}
                  title={entry.hint}
                  className={`w-full flex items-center justify-between px-2 py-1.5 rounded-sm border text-left transition-colors ${
                    category === entry.key
                      ? 'border-echo-cyan/40 bg-echo-cyan/5 text-echo-cyan'
                      : 'border-transparent text-gray-400 hover:text-white hover:bg-[#0F1420]'
                  }`}
                >
                  <span className="font-mono text-[10px] tracking-wider">{entry.label}</span>
                  <span className="font-mono text-[10px] text-echo-muted">{categoryCount[entry.key] ?? 0}</span>
                </button>
              ))}
            </div>
            <div className="p-3 border-t border-echo-border space-y-2">
              <label className="flex items-center gap-2 text-[11px] text-echo-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeArchived}
                  onChange={(event) => setIncludeArchived(event.target.checked)}
                  className="accent-echo-cyan"
                />
                Show archived
              </label>
              {confirmClear ? (
                <div className="rounded-sm border border-echo-danger/40 bg-echo-danger/5 p-2 space-y-2">
                  <p className="text-[10px] text-echo-danger font-mono leading-relaxed">
                    Clear {category === 'all' ? 'ALL memory' : `all ${category} memory`}? Export first if unsure.
                  </p>
                  <div className="flex gap-1">
                    <button
                      onClick={handleClear}
                      disabled={busy}
                      className="flex-1 px-2 py-1 rounded-sm bg-echo-danger/20 border border-echo-danger/50 text-echo-danger font-mono text-[10px] hover:bg-echo-danger/30 disabled:opacity-50"
                    >
                      CONFIRM
                    </button>
                    <button
                      onClick={() => setConfirmClear(false)}
                      className="px-2 py-1 rounded-sm border border-echo-border text-echo-muted font-mono text-[10px] hover:text-white"
                    >
                      CANCEL
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleClear}
                  className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-echo-danger hover:border-echo-danger/40 font-mono text-[10px] tracking-wider transition-colors"
                >
                  <Eraser className="w-3 h-3" />
                  CLEAR MEMORY
                </button>
              )}
            </div>
          </aside>

          {/* Explorer */}
          <section className="flex-1 flex flex-col min-w-0">
            <div className="p-3 border-b border-echo-border bg-[#080B10] flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search keys, content and tags…"
                  className="w-full pl-9 pr-3 py-1.5 rounded-sm border border-echo-border bg-[#0F1420] text-xs text-white placeholder-echo-muted focus:outline-none focus:border-echo-cyan font-mono"
                />
                <Search className="w-3.5 h-3.5 text-echo-muted absolute left-3 top-2.5" />
              </div>
              <button
                onClick={draft ? () => setDraft(null) : openCreate}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-echo-cyan/10 border border-echo-cyan/40 text-echo-cyan text-xs font-medium hover:bg-echo-cyan/20 transition-colors"
              >
                {draft ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                {draft ? 'Discard' : 'New memory'}
              </button>
            </div>

            <div className="px-3 py-1.5 border-b border-echo-border flex items-center gap-3 min-h-[26px]">
              {error && <span className="font-mono text-[10px] text-echo-danger truncate">{error}</span>}
              {!error && notice && <span className="font-mono text-[10px] text-echo-success truncate">{notice}</span>}
              {!error && !notice && (
                <span className="font-mono text-[10px] text-echo-muted">
                  {memories.length} shown · sorted pinned first
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {draft && (
                <div className="rounded-sm border border-echo-cyan/40 bg-[#0B1118] p-3 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] tracking-wider text-echo-cyan">
                      {editingId ? 'EDIT MEMORY' : 'NEW MEMORY'}
                    </span>
                    <span className="font-mono text-[10px] text-echo-muted">
                      Stored in SQLite · visible to you
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-[160px_1fr] gap-2">
                    <select
                      value={draft.category}
                      onChange={(event) =>
                        setDraft({ ...draft, category: event.target.value as MemoryCategory })
                      }
                      className="px-2.5 py-1.5 rounded-sm border border-echo-border bg-[#07090E] text-xs text-echo-cyan font-mono focus:outline-none focus:border-echo-cyan"
                    >
                      {CATEGORIES.filter((entry) => entry.key !== 'all').map((entry) => (
                        <option key={entry.key} value={entry.key}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                    <input
                      value={draft.key}
                      onChange={(event) => setDraft({ ...draft, key: event.target.value })}
                      placeholder="Key (e.g. preferred_editor, project.echo.stack)"
                      className="px-3 py-1.5 rounded-sm border border-echo-border bg-[#07090E] text-xs text-white focus:outline-none focus:border-echo-cyan font-mono"
                    />
                  </div>
                  <textarea
                    value={draft.content}
                    onChange={(event) => setDraft({ ...draft, content: event.target.value })}
                    rows={3}
                    placeholder="What should ECHO remember?"
                    className="w-full px-3 py-1.5 rounded-sm border border-echo-border bg-[#07090E] text-xs text-white focus:outline-none focus:border-echo-cyan resize-y"
                  />
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <label className="block">
                      <span className="font-mono text-[10px] text-echo-muted">CONFIDENCE {Math.round(draft.confidence * 100)}%</span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={draft.confidence}
                        onChange={(event) => setDraft({ ...draft, confidence: Number(event.target.value) })}
                        className="w-full accent-echo-cyan"
                      />
                    </label>
                    <label className="block sm:col-span-2">
                      <span className="font-mono text-[10px] text-echo-muted">TAGS (comma separated)</span>
                      <input
                        value={draft.tags}
                        onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
                        placeholder="work, preference"
                        className="w-full px-2.5 py-1.5 rounded-sm border border-echo-border bg-[#07090E] text-xs text-white focus:outline-none focus:border-echo-cyan font-mono"
                      />
                    </label>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-1.5 text-[11px] text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={draft.pinned}
                        onChange={(event) => setDraft({ ...draft, pinned: event.target.checked })}
                        className="accent-echo-cyan"
                      />
                      Pin to always include in context
                    </label>
                    <label
                      className={`flex items-center gap-1.5 text-[11px] cursor-pointer ${
                        sensitivePrompt ? 'text-echo-warning' : 'text-gray-300'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={draft.allowSensitive}
                        onChange={(event) =>
                          setDraft({ ...draft, allowSensitive: event.target.checked })
                        }
                        className="accent-echo-warning"
                      />
                      Explicit permission for sensitive storage
                    </label>
                  </div>
                  {sensitivePrompt && (
                    <div className="rounded-sm border border-echo-warning/40 bg-echo-warning/5 p-2 text-[11px] text-echo-warning flex items-start gap-2">
                      <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <span>
                        This entry looks like a secret or sensitive personal detail. ECHO refuses to store
                        those unless you explicitly permit it. Tick the permission above, or remove the
                        sensitive detail.
                      </span>
                    </div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setDraft(null);
                        setEditingId(null);
                        setSensitivePrompt(false);
                      }}
                      className="px-3 py-1 rounded-sm border border-echo-border text-echo-muted text-xs hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={busy || !draft.key.trim() || !draft.content.trim()}
                      className="px-3 py-1 rounded-sm bg-echo-cyan text-echo-void text-xs font-semibold hover:bg-echo-cyan/90 disabled:opacity-50 shadow-[0_0_8px_rgba(0,240,255,0.3)]"
                    >
                      {editingId ? 'Save changes' : 'Store memory'}
                    </button>
                  </div>
                </div>
              )}

              {memories.length === 0 && !loading ? (
                <div className="py-16 text-center space-y-2">
                  <Brain className="w-8 h-8 text-echo-muted/40 mx-auto" />
                  <p className="text-xs text-echo-muted">
                    {query ? 'No memory matches this search.' : 'Nothing stored in this class yet.'}
                  </p>
                  {!query && (
                    <p className="text-[10px] font-mono text-echo-muted/70">
                      ECHO will not claim to remember anything that is not here.
                    </p>
                  )}
                </div>
              ) : (
                memories.map((item) => (
                  <article
                    key={item.id}
                    className={`group rounded-sm border bg-[#080B10] p-3 space-y-2 transition-colors ${
                      item.archived
                        ? 'border-echo-border/60 opacity-60'
                        : item.pinned
                        ? 'border-echo-cyan/30'
                        : 'border-echo-border hover:border-echo-cyan/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap min-w-0">
                        {item.pinned && <Pin className="w-3 h-3 text-echo-cyan flex-shrink-0" />}
                        <Chip label={item.category.toUpperCase()} className={CATEGORY_TONE[item.category]} />
                        <span className="font-semibold text-white font-mono text-xs truncate">
                          {item.key}
                        </span>
                        {item.sensitivity === 'high' && (
                          <Chip
                            label="SENSITIVE"
                            className="border-echo-warning/40 bg-echo-warning/10 text-echo-warning"
                            icon={<ShieldAlert className="w-3 h-3" />}
                          />
                        )}
                        {item.permission_granted && (
                          <Chip
                            label="PERMITTED"
                            className="border-echo-danger/40 bg-echo-danger/10 text-echo-danger"
                            icon={<Lock className="w-3 h-3" />}
                          />
                        )}
                        {item.archived && (
                          <Chip label="ARCHIVED" className="border-echo-muted/30 bg-echo-muted/10 text-echo-muted" />
                        )}
                      </div>
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        <button
                          onClick={() => handleTogglePin(item)}
                          className={`p-1 rounded-sm transition-colors ${
                            item.pinned
                              ? 'text-echo-cyan hover:text-white'
                              : 'text-echo-muted opacity-0 group-hover:opacity-100 hover:text-echo-cyan'
                          }`}
                          title={item.pinned ? 'Unpin' : 'Pin'}
                        >
                          {item.pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={() => openEdit(item)}
                          className="p-1 text-echo-muted opacity-0 group-hover:opacity-100 hover:text-white rounded-sm transition-colors"
                          title="Edit"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleToggleArchive(item)}
                          className="p-1 text-echo-muted opacity-0 group-hover:opacity-100 hover:text-white rounded-sm transition-colors"
                          title={item.archived ? 'Restore' : 'Archive'}
                        >
                          {item.archived ? (
                            <ArchiveRestore className="w-3.5 h-3.5" />
                          ) : (
                            <Archive className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          className={`p-1 rounded-sm transition-colors ${
                            confirmDeleteId === item.id
                              ? 'text-echo-danger bg-echo-danger/10'
                              : 'text-echo-muted opacity-0 group-hover:opacity-100 hover:text-echo-danger'
                          }`}
                          title={confirmDeleteId === item.id ? 'Click again to forget' : 'Forget'}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {item.content}
                    </p>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-echo-muted border-t border-echo-border/60 pt-1.5">
                      <span className="flex items-center gap-1" title="Where this memory came from">
                        <Database className="w-3 h-3" />
                        {SOURCE_LABEL[item.source] || item.source.toUpperCase()}
                      </span>
                      <span className="flex items-center gap-1" title="When this memory was last updated">
                        <Clock className="w-3 h-3" />
                        UPD {formatDate(item.updated_at)}
                      </span>
                      <span>CONF {Math.round(item.confidence * 100)}%</span>
                      <span>USED {item.use_count}×</span>
                      {item.tags.length > 0 && (
                        <span className="flex items-center gap-1 min-w-0">
                          <Tag className="w-3 h-3" />
                          <span className="truncate">{item.tags.join(', ')}</span>
                        </span>
                      )}
                    </div>
                  </article>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
