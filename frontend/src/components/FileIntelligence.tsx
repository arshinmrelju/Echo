import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  ChevronRight,
  Copy,
  CopyPlus,
  Database,
  FileScan,
  FileText,
  Files,
  FolderInput,
  FolderOpen,
  FolderPlus,
  FolderSearch,
  FolderTree,
  HardDrive,
  Hash,
  History,
  Info,
  Pencil,
  Play,
  RefreshCw,
  ScanSearch,
  ScanText,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import {
  ApprovedDirectory,
  DuplicateGroup,
  FileActionLog,
  FileCategory,
  FileDetails,
  FileEntry,
  FileOperationPlan,
  FileSettings,
  FileStats,
  FileSummary,
} from '../types';
import { ApiError, apiClient } from '../api/client';

interface FileIntelligenceProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabKey = 'search' | 'library' | 'duplicates' | 'directories' | 'activity';

interface Filters {
  query: string;
  extension: string;
  category: '' | FileCategory;
  directoryId: string;
  minSizeMb: string;
  maxSizeMb: string;
  modifiedAfter: string;
  modifiedBefore: string;
  sort: 'modified' | 'oldest' | 'name' | 'size';
}

interface PendingAction {
  title: string;
  message: string;
  confirmLabel: string;
  plan?: FileOperationPlan;
  planKind: 'organize' | 'rename' | 'quarantine' | 'overwrite';
  run: () => Promise<void>;
}

const CATEGORY_LABEL: Record<FileCategory, string> = {
  document: 'DOCUMENTS',
  spreadsheet: 'SPREADSHEETS',
  presentation: 'PRESENTATIONS',
  image: 'IMAGES',
  audio: 'AUDIO',
  video: 'VIDEO',
  code: 'CODE',
  archive: 'ARCHIVES',
  executable: 'EXECUTABLES',
  other: 'OTHER',
};

const CATEGORY_TONE: Record<FileCategory, string> = {
  document: 'border-echo-blue/40 bg-echo-blue/10 text-echo-blue',
  spreadsheet: 'border-echo-success/40 bg-echo-success/10 text-echo-success',
  presentation: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
  image: 'border-echo-purple/40 bg-echo-purple/10 text-echo-purple',
  audio: 'border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan',
  video: 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger',
  code: 'border-echo-cyan/30 bg-echo-cyan/5 text-echo-cyan',
  archive: 'border-echo-muted/30 bg-echo-muted/10 text-echo-muted',
  executable: 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger',
  other: 'border-echo-muted/30 bg-echo-muted/10 text-echo-muted',
};

const EMPTY_FILTERS: Filters = {
  query: '',
  extension: '',
  category: '',
  directoryId: '',
  minSizeMb: '',
  maxSizeMb: '',
  modifiedAfter: '',
  modifiedBefore: '',
  sort: 'modified',
};

const formatBytes = (bytes: number | null | undefined) => {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
};

const formatWhen = (value: string | number | null | undefined) => {
  if (value === null || value === undefined || value === '') return '—';
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const timeAgo = (value: string | null | undefined) => {
  if (!value) return 'never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'never';
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};

const basename = (path: string) => path.split(/[\\/]/).pop() || path;
const dirname = (path: string) => path.replace(/[\\/][^\\/]+$/, '') || path;

const Chip: React.FC<{ label: string; className?: string; icon?: React.ReactNode }> = ({
  label,
  className = 'border-echo-border bg-[#121721] text-echo-muted',
  icon,
}) => (
  <span
    className={`inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded-sm border tracking-wider whitespace-nowrap ${className}`}
  >
    {icon}
    {label}
  </span>
);

const Panel: React.FC<{
  title: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}> = ({ title, icon, actions, children, className = '' }) => (
  <section className={`rounded-sm border border-echo-border bg-[#0B0E14] ${className}`}>
    <header className="flex items-center justify-between gap-2 px-3 py-2 border-b border-echo-border">
      <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] text-echo-muted">
        {icon}
        <span>{title}</span>
      </div>
      {actions}
    </header>
    <div className="p-3">{children}</div>
  </section>
);

const Field: React.FC<{
  label: string;
  children: React.ReactNode;
  className?: string;
}> = ({ label, children, className = '' }) => (
  <label className={`block ${className}`}>
    <span className="block font-mono text-[10px] tracking-wider text-echo-muted uppercase mb-1">
      {label}
    </span>
    {children}
  </label>
);

const inputClass =
  'w-full px-2.5 py-1.5 rounded-sm border border-echo-border bg-[#07090E] text-xs text-white placeholder-echo-muted/60 focus:outline-none focus:border-echo-cyan font-mono';

const buttonClass =
  'inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-sm border font-mono text-[11px] tracking-wide transition-colors disabled:opacity-40 disabled:cursor-not-allowed';

export const FileIntelligence: React.FC<FileIntelligenceProps> = ({ isOpen, onClose }) => {
  const [tab, setTab] = useState<TabKey>('search');
  const [status, setStatus] = useState<FileStats | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [results, setResults] = useState<FileEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [selected, setSelected] = useState<FileEntry | null>(null);
  const [details, setDetails] = useState<FileDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [summary, setSummary] = useState<FileSummary | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const [destination, setDestination] = useState('');

  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([]);
  const [duplicateMinSize, setDuplicateMinSize] = useState('0');
  const [activity, setActivity] = useState<FileActionLog[]>([]);

  const [dirPath, setDirPath] = useState('');
  const [dirLabel, setDirLabel] = useState('');
  const [dirRecursive, setDirRecursive] = useState(true);
  const [dirIndexNow, setDirIndexNow] = useState(true);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const [settingsDraft, setSettingsDraft] = useState<FileSettings | null>(null);

  const [organizeDir, setOrganizeDir] = useState('');
  const [organizeDest, setOrganizeDest] = useState('');
  const [renameDir, setRenameDir] = useState('');
  const [renameFind, setRenameFind] = useState('');
  const [renameReplace, setRenameReplace] = useState('');

  const [pending, setPending] = useState<PendingAction | null>(null);

  const directories = status?.directories ?? [];

  const flashError = (e: unknown) => {
    setError(e instanceof Error ? e.message : 'Request failed.');
  };

  const refreshStatus = useCallback(async () => {
    try {
      const next = await apiClient.getFileStatus();
      setStatus(next);
      setSettingsDraft((current) => current ?? next.settings);
      setOrganizeDir((current) => current || next.directories[0]?.path || '');
      setRenameDir((current) => current || next.directories[0]?.path || '');
    } catch (e) {
      flashError(e);
    }
  }, []);

  const executeSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.searchFiles({
        query: filters.query.trim() || undefined,
        extension: filters.extension.trim() || undefined,
        category: filters.category || undefined,
        directoryId: filters.directoryId || undefined,
        minSizeMb: filters.minSizeMb ? Number(filters.minSizeMb) : undefined,
        maxSizeMb: filters.maxSizeMb ? Number(filters.maxSizeMb) : undefined,
        modifiedAfter: filters.modifiedAfter
          ? new Date(`${filters.modifiedAfter}T00:00:00`).toISOString()
          : undefined,
        modifiedBefore: filters.modifiedBefore
          ? new Date(`${filters.modifiedBefore}T23:59:59`).toISOString()
          : undefined,
        sort: filters.sort,
        limit: 250,
      });
      setResults(response.results);
      setTotal(response.total);
    } catch (e) {
      flashError(e);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadDuplicates = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.getDuplicateFiles(
        Number(duplicateMinSize) || 0,
        filters.directoryId || undefined
      );
      setDuplicates(response.groups);
    } catch (e) {
      flashError(e);
    } finally {
      setLoading(false);
    }
  }, [duplicateMinSize, filters.directoryId]);

  const loadActivity = useCallback(async () => {
    try {
      const response = await apiClient.getFileActivity(150);
      setActivity(response.actions);
    } catch (e) {
      flashError(e);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    void refreshStatus();
  }, [isOpen, refreshStatus]);

  useEffect(() => {
    if (!isOpen || tab !== 'search') return;
    const timer = setTimeout(executeSearch, filters.query ? 220 : 0);
    return () => clearTimeout(timer);
  }, [isOpen, tab, executeSearch, filters.query]);

  useEffect(() => {
    if (!isOpen || tab !== 'duplicates') return;
    void loadDuplicates();
  }, [isOpen, tab, loadDuplicates]);

  useEffect(() => {
    if (!isOpen || tab !== 'activity') return;
    void loadActivity();
  }, [isOpen, tab, loadActivity]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 4500);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (pending) setPending(null);
        else onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose, pending]);

  useEffect(() => {
    if (!isOpen) {
      setSelected(null);
      setDetails(null);
      setSummary(null);
      setPending(null);
      setConfirmRemove(null);
      setError(null);
    }
  }, [isOpen]);

  const selectFile = async (entry: FileEntry) => {
    setSelected(entry);
    setDetails(null);
    setSummary(null);
    setRenameDraft(entry.name);
    setDestination(dirname(entry.path));
    setDetailsLoading(true);
    try {
      setDetails(await apiClient.getFileDetails(entry.path));
    } catch (e) {
      flashError(e);
    } finally {
      setDetailsLoading(false);
    }
  };

  const refreshAfterChange = async () => {
    await refreshStatus();
    if (tab === 'search') await executeSearch();
    if (tab === 'duplicates') await loadDuplicates();
    await loadActivity();
  };

  const handleIndex = async (directoryId?: string) => {
    setIndexing(true);
    setError(null);
    try {
      const response = await apiClient.indexFiles(directoryId);
      const result = response.result;
      setNotice(
        `Indexed ${result.indexed} · unchanged ${result.unchanged} · skipped ${result.skipped}` +
          (result.removed ? ` · pruned ${result.removed}` : '') +
          (result.truncated ? ' · capped at max files' : '') +
          ` · ${Math.round(result.duration_ms)}ms`
      );
      await refreshAfterChange();
    } catch (e) {
      flashError(e);
    } finally {
      setIndexing(false);
    }
  };

  const handleAddDirectory = async () => {
    if (!dirPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.addFileDirectory(dirPath.trim(), {
        label: dirLabel.trim() || undefined,
        recursive: dirRecursive,
        indexNow: dirIndexNow,
      });
      setDirPath('');
      setDirLabel('');
      setNotice(
        response.index
          ? `Approved and indexed ${response.index.indexed} files.`
          : 'Directory approved. Index it when ready.'
      );
      await refreshStatus();
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveDirectory = async (directory: ApprovedDirectory) => {
    if (confirmRemove !== directory.id) {
      setConfirmRemove(directory.id);
      return;
    }
    setBusy(true);
    try {
      await apiClient.removeFileDirectory(directory.id);
      setConfirmRemove(null);
      setNotice('Directory removed from the index. Nothing on disk was touched.');
      await refreshAfterChange();
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settingsDraft) return;
    setBusy(true);
    try {
      const response = await apiClient.updateFileSettings(settingsDraft);
      setSettingsDraft(response.settings);
      setNotice('File intelligence settings saved.');
      await refreshStatus();
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const handleOpen = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await apiClient.openFile(selected.path);
      setNotice(`Opened ${selected.name}.`);
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const handleRename = async () => {
    if (!selected || !renameDraft.trim() || renameDraft === selected.name) return;
    setBusy(true);
    try {
      const response = await apiClient.renameFile(selected.path, renameDraft.trim(), false);
      setNotice(`Renamed to ${basename(response.new_path)}.`);
      await selectFile({ ...selected, path: response.new_path, name: basename(response.new_path) });
      await refreshAfterChange();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const target = e.plan?.plan?.[0]?.target || `'${renameDraft.trim()}'`;
        setPending({
          title: 'Overwrite existing file?',
          message: `${target} already exists. Renaming will replace it. This cannot be undone.`,
          confirmLabel: 'Overwrite and rename',
          planKind: 'overwrite',
          run: async () => {
            const response = await apiClient.renameFile(selected.path, renameDraft.trim(), true);
            setNotice(`Renamed to ${basename(response.new_path)}.`);
            await selectFile({ ...selected, path: response.new_path, name: basename(response.new_path) });
            await refreshAfterChange();
          },
        });
      } else {
        flashError(e);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleCopyMove = async (mode: 'copy' | 'move') => {
    if (!selected || !destination.trim()) return;
    setBusy(true);
    try {
      const response =
        mode === 'copy'
          ? await apiClient.copyFile(selected.path, destination.trim(), false)
          : await apiClient.moveFile(selected.path, destination.trim(), false);
      setNotice(
        mode === 'copy'
          ? `Copied to ${response.destination}.`
          : `Moved to ${response.destination}.`
      );
      if (mode === 'move') {
        setSelected(null);
        setDetails(null);
      }
      await refreshAfterChange();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const plan = e.plan;
        setPending({
          title: 'Overwrite existing file?',
          message: `A file already exists at the destination. ${mode === 'copy' ? 'Copying' : 'Moving'} will replace it. This cannot be undone.`,
          confirmLabel: `Overwrite and ${mode}`,
          plan,
          planKind: 'overwrite',
          run: async () => {
            const response =
              mode === 'copy'
                ? await apiClient.copyFile(selected.path, destination.trim(), true)
                : await apiClient.moveFile(selected.path, destination.trim(), true);
            setNotice(
              mode === 'copy'
                ? `Copied to ${response.destination}.`
                : `Moved to ${response.destination}.`
            );
            if (mode === 'move') {
              setSelected(null);
              setDetails(null);
            }
            await refreshAfterChange();
          },
        });
      } else {
        flashError(e);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSummarize = async () => {
    if (!selected) return;
    setSummarizing(true);
    setError(null);
    try {
      setSummary(await apiClient.summarizeFile(selected.path, true));
    } catch (e) {
      flashError(e);
    } finally {
      setSummarizing(false);
    }
  };

  const previewOrganize = async () => {
    if (!organizeDir) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await apiClient.organizeFiles(organizeDir, {
        destinationRoot: organizeDest.trim() || undefined,
        dryRun: true,
      });
      if (!plan.planned) {
        setNotice('Nothing to organize — every file already has a folder.');
        return;
      }
      setPending({
        title: 'Organize files by type',
        message: `${plan.planned} top-level files will be moved into category folders. Files are moved, never deleted.`,
        confirmLabel: `Move ${plan.planned} files`,
        plan,
        planKind: 'organize',
        run: async () => {
          await apiClient.organizeFiles(organizeDir, {
            destinationRoot: organizeDest.trim() || undefined,
            confirm: true,
            dryRun: false,
          });
          setNotice('Organize complete.');
          await refreshAfterChange();
        },
      });
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const previewBulkRename = async () => {
    if (!renameDir || !renameFind) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await apiClient.bulkRenameFiles(renameDir, renameFind, renameReplace, {
        dryRun: true,
      });
      if (!plan.planned) {
        setNotice('No file names matched that text.');
        return;
      }
      setPending({
        title: 'Bulk rename preview',
        message: `${plan.planned} files will be renamed. Review the mapping before continuing.`,
        confirmLabel: `Rename ${plan.planned} files`,
        plan,
        planKind: 'rename',
        run: async () => {
          await apiClient.bulkRenameFiles(renameDir, renameFind, renameReplace, {
            confirm: true,
            dryRun: false,
          });
          setNotice('Bulk rename complete.');
          await refreshAfterChange();
        },
      });
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const previewQuarantine = async () => {
    setBusy(true);
    setError(null);
    try {
      const plan = await apiClient.quarantineDuplicates(filters.directoryId || undefined, {
        dryRun: true,
      });
      if (!plan.planned) {
        setNotice('No duplicate files to quarantine.');
        return;
      }
      setPending({
        title: 'Quarantine duplicate copies',
        message: `${plan.planned} duplicate copies will be moved into _ECHO_DUPLICATES folders. One copy of each file always stays in place. Nothing is deleted.`,
        confirmLabel: `Quarantine ${plan.planned} copies`,
        plan,
        planKind: 'quarantine',
        run: async () => {
          await apiClient.quarantineDuplicates(filters.directoryId || undefined, {
            confirm: true,
            dryRun: false,
          });
          setNotice('Duplicates quarantined. Originals kept.');
          await refreshAfterChange();
        },
      });
    } catch (e) {
      flashError(e);
    } finally {
      setBusy(false);
    }
  };

  const runPending = async () => {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      await pending.run();
      setPending(null);
    } catch (e) {
      flashError(e);
      setPending(null);
    } finally {
      setBusy(false);
    }
  };

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
  };

  const largeFiles = useMemo(() => status?.largest ?? [], [status]);
  const maxCategoryBytes = useMemo(
    () => Math.max(1, ...(status?.by_category ?? []).map((entry) => entry.bytes)),
    [status]
  );
  const capabilities = status?.capabilities;

  if (!isOpen) return null;

  const duplicateCount = status?.duplicate_groups ?? 0;
  const directoryCount = directories.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3">
      <div className="w-full max-w-[1280px] h-[92vh] flex flex-col rounded-lg border border-echo-border bg-[#07090E] shadow-2xl overflow-hidden relative">
        <header className="border-b border-echo-border bg-[#0B0E14]">
          <div className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-sm border border-echo-cyan/40 bg-echo-cyan/5 flex items-center justify-center text-echo-cyan">
                <FolderSearch className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-mono text-sm tracking-[0.18em] text-white">FILE INTELLIGENCE</h2>
                  <Chip label="LOCAL ONLY" className="border-echo-success/40 bg-echo-success/10 text-echo-success" />
                  <Chip label={`${directoryCount} APPROVED ROOTS`} />
                  <Chip label="NO DELETE" className="border-echo-cyan/30 bg-echo-cyan/5 text-echo-cyan" icon={<ShieldCheck className="w-3 h-3" />} />
                </div>
                <p className="mt-1 font-mono text-[10px] text-echo-muted truncate">
                  Search is restricted to approved directories. Actions move or copy files — ECHO never deletes.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleIndex()}
                disabled={indexing || !directoryCount}
                className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20`}
                title="Re-index every approved directory"
              >
                <Play className={`w-3.5 h-3.5 ${indexing ? 'animate-pulse' : ''}`} />
                {indexing ? 'INDEXING…' : 'INDEX ALL'}
              </button>
              <button
                onClick={async () => {
                  await refreshStatus();
                  await refreshAfterChange();
                }}
                className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-muted/50 transition-colors"
                title="Refresh"
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
              <span className="text-echo-muted">INDEXED FILES</span>
              <span className="text-white">{status?.total_files ?? 0}</span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">TOTAL SIZE</span>
              <span className="text-echo-cyan">{formatBytes(status?.total_bytes ?? 0)}</span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">DUPLICATE GROUPS</span>
              <span className={duplicateCount ? 'text-echo-warning' : 'text-echo-success'}>
                {duplicateCount} · {formatBytes(status?.duplicate_wasted_bytes ?? 0)} wasted
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5">
              <span className="text-echo-muted">LAST INDEX</span>
              <span className="text-echo-muted">{timeAgo(status?.last_indexed_at)}</span>
            </div>
          </div>
        </header>

        <nav className="flex items-center gap-1 px-4 border-b border-echo-border bg-[#090C12]">
          {(
            [
              ['search', 'SEARCH'],
              ['library', 'LIBRARY'],
              ['duplicates', `DUPLICATES${duplicateCount ? ` ${duplicateCount}` : ''}`],
              ['directories', `DIRECTORIES${directoryCount ? ` ${directoryCount}` : ''}`],
              ['activity', 'ACTIVITY'],
            ] as [TabKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-3 py-2 font-mono text-[11px] tracking-wider border-b-2 transition-colors ${
                tab === key ? 'border-echo-cyan text-echo-cyan' : 'border-transparent text-echo-muted hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-3 py-1 min-w-0">
            {error && <span className="font-mono text-[10px] text-echo-danger truncate max-w-[460px]">{error}</span>}
            {!error && notice && (
              <span className="font-mono text-[10px] text-echo-success truncate max-w-[460px]">{notice}</span>
            )}
          </div>
        </nav>

        <div className="flex-1 flex min-h-0">
          <div className="flex-1 overflow-y-auto p-4 min-w-0">
            {/* SEARCH ------------------------------------------------------ */}
            {tab === 'search' && (
              <div className="space-y-4">
                <div className="rounded-sm border border-echo-border bg-[#0B0E14] p-3 space-y-2.5">
                  <div className="flex flex-wrap lg:flex-nowrap items-end gap-2">
                    <Field label="Query — name, path or content" className="flex-1 min-w-[220px]">
                      <div className="relative">
                        <input
                          value={filters.query}
                          onChange={(event) => setFilters({ ...filters, query: event.target.value })}
                          placeholder="e.g. invoice, budget, meeting notes"
                          className={`${inputClass} pl-8`}
                        />
                        <ScanSearch className="w-3.5 h-3.5 text-echo-muted absolute left-2.5 top-2.5" />
                      </div>
                    </Field>
                    <Field label="Category" className="w-[150px]">
                      <select
                        value={filters.category}
                        onChange={(event) =>
                          setFilters({ ...filters, category: event.target.value as Filters['category'] })
                        }
                        className={inputClass}
                      >
                        <option value="">Any type</option>
                        {(Object.keys(CATEGORY_LABEL) as FileCategory[]).map((category) => (
                          <option key={category} value={category}>
                            {CATEGORY_LABEL[category]}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Extension" className="w-[110px]">
                      <input
                        value={filters.extension}
                        onChange={(event) => setFilters({ ...filters, extension: event.target.value })}
                        placeholder=".pdf"
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Sort" className="w-[130px]">
                      <select
                        value={filters.sort}
                        onChange={(event) =>
                          setFilters({ ...filters, sort: event.target.value as Filters['sort'] })
                        }
                        className={inputClass}
                      >
                        <option value="modified">Newest first</option>
                        <option value="oldest">Oldest first</option>
                        <option value="name">Name A–Z</option>
                        <option value="size">Largest first</option>
                      </select>
                    </Field>
                    <Field label="Approved root" className="w-[190px]">
                      <select
                        value={filters.directoryId}
                        onChange={(event) => setFilters({ ...filters, directoryId: event.target.value })}
                        className={inputClass}
                      >
                        <option value="">All approved roots</option>
                        {directories.map((directory) => (
                          <option key={directory.id} value={directory.id}>
                            {directory.label || directory.path}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <Field label="Min size (MB)" className="w-[110px]">
                      <input
                        type="number"
                        min={0}
                        value={filters.minSizeMb}
                        onChange={(event) => setFilters({ ...filters, minSizeMb: event.target.value })}
                        placeholder="0"
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Max size (MB)" className="w-[110px]">
                      <input
                        type="number"
                        min={0}
                        value={filters.maxSizeMb}
                        onChange={(event) => setFilters({ ...filters, maxSizeMb: event.target.value })}
                        placeholder="—"
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Modified after" className="w-[150px]">
                      <input
                        type="date"
                        value={filters.modifiedAfter}
                        onChange={(event) => setFilters({ ...filters, modifiedAfter: event.target.value })}
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Modified before" className="w-[150px]">
                      <input
                        type="date"
                        value={filters.modifiedBefore}
                        onChange={(event) => setFilters({ ...filters, modifiedBefore: event.target.value })}
                        className={inputClass}
                      />
                    </Field>
                    <button onClick={clearFilters} className={`${buttonClass} border-echo-border text-echo-muted hover:text-white`}>
                      RESET
                    </button>
                    <button
                      onClick={() => {
                        setFilters({ ...filters, minSizeMb: '100', sort: 'size' });
                        setTab('search');
                      }}
                      className={`${buttonClass} border-echo-warning/40 bg-echo-warning/5 text-echo-warning hover:bg-echo-warning/15`}
                    >
                      <HardDrive className="w-3.5 h-3.5" />
                      FILES &gt; 100 MB
                    </button>
                    <span className="ml-auto font-mono text-[10px] text-echo-muted">
                      {loading ? 'SEARCHING…' : `${results.length} of ${total} results`}
                    </span>
                  </div>
                </div>

                {results.length === 0 && !loading ? (
                  <div className="py-16 text-center space-y-2">
                    <FileScan className="w-8 h-8 text-echo-muted/40 mx-auto" />
                    <p className="text-xs text-echo-muted">
                      {directoryCount
                        ? 'No files match these filters. Try a broader query or index again.'
                        : 'Approve a directory first — search only runs inside approved roots.'}
                    </p>
                  </div>
                ) : (
                  <div className="rounded-sm border border-echo-border overflow-hidden">
                    <div className="grid grid-cols-[1fr_110px_150px_70px] gap-2 px-3 py-1.5 bg-[#0B0E14] border-b border-echo-border font-mono text-[10px] tracking-wider text-echo-muted">
                      <span>FILE</span>
                      <span>SIZE</span>
                      <span>MODIFIED</span>
                      <span>TYPE</span>
                    </div>
                    {results.map((entry) => (
                      <button
                        key={entry.id}
                        onClick={() => selectFile(entry)}
                        className={`w-full text-left grid grid-cols-[1fr_110px_150px_70px] gap-2 px-3 py-2 border-b border-echo-border/60 last:border-b-0 hover:bg-[#0E131C] transition-colors ${
                          selected?.id === entry.id ? 'bg-[#0E131C]' : ''
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText className="w-3.5 h-3.5 text-echo-cyan flex-shrink-0" />
                            <span className="text-xs text-white font-medium truncate">{entry.name}</span>
                            {entry.content_status === 'indexed' && (
                              <Chip label="CONTENT" className="border-echo-success/30 bg-echo-success/5 text-echo-success" />
                            )}
                            {entry.content_status === 'error' && (
                              <Chip label="TEXT ERROR" className="border-echo-warning/40 bg-echo-warning/5 text-echo-warning" />
                            )}
                          </div>
                          <div className="font-mono text-[10px] text-echo-muted truncate mt-0.5">
                            {dirname(entry.path)}
                          </div>
                          {entry.snippet && (
                            <div className="mt-1 text-[11px] text-gray-400 line-clamp-2">
                              {entry.snippet}
                            </div>
                          )}
                        </div>
                        <span className="font-mono text-[11px] text-gray-300 self-center">
                          {formatBytes(entry.size_bytes)}
                        </span>
                        <span className="font-mono text-[10px] text-echo-muted self-center">
                          {formatWhen(entry.modified_at)}
                        </span>
                        <span className="self-center">
                          <Chip
                            label={CATEGORY_LABEL[entry.category] || entry.category}
                            className={CATEGORY_TONE[entry.category] || CATEGORY_TONE.other}
                          />
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* LIBRARY ----------------------------------------------------- */}
            {tab === 'library' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  {[
                    ['FILES', `${status?.total_files ?? 0}`],
                    ['TOTAL SIZE', formatBytes(status?.total_bytes ?? 0)],
                    ['DUPLICATE WASTE', formatBytes(status?.duplicate_wasted_bytes ?? 0)],
                    ['APPROVED ROOTS', `${directoryCount}`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-sm border border-echo-border bg-[#0B0E14] px-3 py-2.5">
                      <div className="font-mono text-[10px] tracking-wider text-echo-muted">{label}</div>
                      <div className="mt-1 font-mono text-lg text-white">{value}</div>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <Panel title="FILES BY CATEGORY" icon={<Database className="w-3.5 h-3.5" />}>
                    {(status?.by_category ?? []).length === 0 ? (
                      <p className="text-xs text-echo-muted py-6 text-center">Nothing indexed yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {(status?.by_category ?? []).map((entry) => (
                          <div key={entry.category} className="space-y-1">
                            <div className="flex items-center justify-between font-mono text-[10px]">
                              <span className="text-gray-300">{CATEGORY_LABEL[entry.category] || entry.category}</span>
                              <span className="text-echo-muted">
                                {entry.count} · {formatBytes(entry.bytes)}
                              </span>
                            </div>
                            <div className="h-1.5 rounded-sm bg-[#121721] overflow-hidden">
                              <div
                                className="h-full bg-echo-cyan/70"
                                style={{ width: `${Math.max(2, (entry.bytes / maxCategoryBytes) * 100)}%` }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </Panel>

                  <Panel
                    title="LARGEST FILES"
                    icon={<HardDrive className="w-3.5 h-3.5" />}
                    actions={
                      <button
                        onClick={() => {
                          setFilters({ ...EMPTY_FILTERS, minSizeMb: '100', sort: 'size' });
                          setTab('search');
                        }}
                        className="font-mono text-[10px] text-echo-cyan hover:text-white"
                      >
                        OPEN IN SEARCH
                      </button>
                    }
                  >
                    {largeFiles.length === 0 ? (
                      <p className="text-xs text-echo-muted py-6 text-center">Nothing indexed yet.</p>
                    ) : (
                      <div className="space-y-1">
                        {largeFiles.map((entry) => (
                          <button
                            key={entry.path}
                            onClick={() =>
                              selectFile({
                                id: entry.path,
                                directory_id: '',
                                path: entry.path,
                                name: entry.name,
                                extension: '',
                                category: entry.category,
                                size_bytes: entry.size_bytes,
                                modified_at: entry.modified_at,
                                created_at: null,
                                content_hash: null,
                                content_status: 'indexed',
                                indexed_at: '',
                              })
                            }
                            className="w-full flex items-center justify-between gap-2 px-1.5 py-1 rounded-sm hover:bg-[#121721] transition-colors"
                          >
                            <span className="flex items-center gap-1.5 min-w-0 text-xs text-gray-300">
                              <FileText className="w-3 h-3 text-echo-muted flex-shrink-0" />
                              <span className="truncate">{entry.name}</span>
                            </span>
                            <span className="font-mono text-[10px] text-echo-cyan flex-shrink-0">
                              {formatBytes(entry.size_bytes)}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </Panel>
                </div>

                <Panel title="CAPABILITIES" icon={<ScanText className="w-3.5 h-3.5" />}>
                  <div className="flex flex-wrap gap-1.5">
                    {capabilities &&
                      (Object.entries(capabilities) as [string, boolean][]).map(([key, value]) => (
                        <Chip
                          key={key}
                          label={`${key.toUpperCase()} ${value ? 'READY' : 'OFF'}`}
                          className={
                            value
                              ? 'border-echo-success/30 bg-echo-success/5 text-echo-success'
                              : 'border-echo-border bg-[#121721] text-echo-muted'
                          }
                        />
                      ))}
                    <span className="font-mono text-[10px] text-echo-muted self-center ml-1">
                      PDF and OCR activate automatically when optional packages are installed.
                    </span>
                  </div>
                </Panel>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <Panel title="ORGANIZE BY TYPE" icon={<FolderTree className="w-3.5 h-3.5" />}>
                    <div className="space-y-2">
                      <Field label="Directory to organize">
                        <select
                          value={organizeDir}
                          onChange={(event) => setOrganizeDir(event.target.value)}
                          className={inputClass}
                        >
                          <option value="">Select an approved directory</option>
                          {directories.map((directory) => (
                            <option key={directory.id} value={directory.path}>
                              {directory.label || directory.path}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Destination root (blank = same directory)">
                        <input
                          value={organizeDest}
                          onChange={(event) => setOrganizeDest(event.target.value)}
                          placeholder="Optional approved folder"
                          className={inputClass}
                        />
                      </Field>
                      <div className="flex items-center justify-between gap-2 pt-1">
                        <p className="text-[10px] text-echo-muted leading-relaxed">
                          Top-level files move into Documents, Images, Code… folders. Always previewed first.
                        </p>
                        <button
                          onClick={previewOrganize}
                          disabled={busy || !organizeDir}
                          className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20 flex-shrink-0`}
                        >
                          <FolderInput className="w-3.5 h-3.5" />
                          PREVIEW
                        </button>
                      </div>
                    </div>
                  </Panel>

                  <Panel title="BULK RENAME" icon={<Pencil className="w-3.5 h-3.5" />}>
                    <div className="space-y-2">
                      <Field label="Directory">
                        <select
                          value={renameDir}
                          onChange={(event) => setRenameDir(event.target.value)}
                          className={inputClass}
                        >
                          <option value="">Select an approved directory</option>
                          {directories.map((directory) => (
                            <option key={directory.id} value={directory.path}>
                              {directory.label || directory.path}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <div className="grid grid-cols-2 gap-2">
                        <Field label="Find text">
                          <input
                            value={renameFind}
                            onChange={(event) => setRenameFind(event.target.value)}
                            placeholder="IMG_"
                            className={inputClass}
                          />
                        </Field>
                        <Field label="Replace with">
                          <input
                            value={renameReplace}
                            onChange={(event) => setRenameReplace(event.target.value)}
                            placeholder="photo_"
                            className={inputClass}
                          />
                        </Field>
                      </div>
                      <div className="flex items-center justify-between gap-2 pt-1">
                        <p className="text-[10px] text-echo-muted leading-relaxed">
                          Renames only top-level files in the chosen directory. Every change is previewed.
                        </p>
                        <button
                          onClick={previewBulkRename}
                          disabled={busy || !renameDir || !renameFind}
                          className={`${buttonClass} border-echo-warning/40 bg-echo-warning/5 text-echo-warning hover:bg-echo-warning/15 flex-shrink-0`}
                        >
                          <Hash className="w-3.5 h-3.5" />
                          PREVIEW
                        </button>
                      </div>
                    </div>
                  </Panel>
                </div>
              </div>
            )}

            {/* DUPLICATES -------------------------------------------------- */}
            {tab === 'duplicates' && (
              <div className="space-y-4">
                <div className="rounded-sm border border-echo-border bg-[#0B0E14] p-3 flex flex-wrap items-end gap-3">
                  <Field label="Minimum size (MB)" className="w-[130px]">
                    <input
                      type="number"
                      min={0}
                      value={duplicateMinSize}
                      onChange={(event) => setDuplicateMinSize(event.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <button
                    onClick={loadDuplicates}
                    className={`${buttonClass} border-echo-border text-echo-muted hover:text-white`}
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    RESCAN
                  </button>
                  <div className="flex-1" />
                  <p className="text-[10px] text-echo-muted max-w-[360px] leading-relaxed">
                    Duplicates are matched by SHA-256 content hash. Quarantine moves extra copies into
                    <span className="text-echo-cyan"> _ECHO_DUPLICATES</span> and always keeps one copy.
                  </p>
                  <button
                    onClick={previewQuarantine}
                    disabled={busy || duplicates.length === 0}
                    className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20`}
                  >
                    <Copy className="w-3.5 h-3.5" />
                    PREVIEW QUARANTINE
                  </button>
                </div>

                {duplicates.length === 0 ? (
                  <div className="py-16 text-center space-y-2">
                    <CopyPlus className="w-8 h-8 text-echo-muted/40 mx-auto" />
                    <p className="text-xs text-echo-muted">No duplicate content found in the index.</p>
                  </div>
                ) : (
                  duplicates.map((group) => (
                    <div key={group.content_hash} className="rounded-sm border border-echo-border bg-[#0B0E14]">
                      <div className="flex items-center justify-between px-3 py-2 border-b border-echo-border">
                        <div className="flex items-center gap-2 font-mono text-[10px] text-echo-muted">
                          <Hash className="w-3.5 h-3.5" />
                          <span className="text-white">{group.content_hash.slice(0, 16)}</span>
                          <span>{group.count} copies · {formatBytes(group.size_bytes)} each</span>
                        </div>
                        <Chip
                          label={`WASTED ${formatBytes(Math.max(0, group.size_bytes * (group.count - 1)))}`}
                          className="border-echo-warning/40 bg-echo-warning/5 text-echo-warning"
                        />
                      </div>
                      <div className="divide-y divide-echo-border/60">
                        {group.files.map((file, index) => (
                          <button
                            key={file.id}
                            onClick={() => {
                              setTab('search');
                              selectFile({
                                ...file,
                                directory_id: '',
                                created_at: null,
                                content_hash: group.content_hash,
                                content_status: 'indexed',
                                indexed_at: '',
                              });
                            }}
                            className="w-full flex items-center justify-between gap-3 px-3 py-1.5 hover:bg-[#0E131C] text-left transition-colors"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Chip
                                label={index === 0 ? 'KEEP' : 'DUPLICATE'}
                                className={
                                  index === 0
                                    ? 'border-echo-success/40 bg-echo-success/10 text-echo-success'
                                    : 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning'
                                }
                              />
                              <span className="text-xs text-gray-300 truncate">{file.path}</span>
                            </div>
                            <span className="font-mono text-[10px] text-echo-muted flex-shrink-0">
                              {formatWhen(file.modified_at)}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* DIRECTORIES ------------------------------------------------- */}
            {tab === 'directories' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <Panel title="APPROVE A DIRECTORY" icon={<FolderPlus className="w-3.5 h-3.5" />}>
                    <div className="space-y-2">
                      <Field label="Absolute folder path">
                        <input
                          value={dirPath}
                          onChange={(event) => setDirPath(event.target.value)}
                          placeholder="C:\Users\You\Documents"
                          className={inputClass}
                        />
                      </Field>
                      <Field label="Label (optional)">
                        <input
                          value={dirLabel}
                          onChange={(event) => setDirLabel(event.target.value)}
                          placeholder="Work documents"
                          className={inputClass}
                        />
                      </Field>
                      <div className="flex flex-wrap items-center gap-4">
                        <label className="flex items-center gap-1.5 text-[11px] text-gray-300 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={dirRecursive}
                            onChange={(event) => setDirRecursive(event.target.checked)}
                            className="accent-echo-cyan"
                          />
                          Include subfolders
                        </label>
                        <label className="flex items-center gap-1.5 text-[11px] text-gray-300 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={dirIndexNow}
                            onChange={(event) => setDirIndexNow(event.target.checked)}
                            className="accent-echo-cyan"
                          />
                          Index immediately
                        </label>
                        <button
                          onClick={handleAddDirectory}
                          disabled={busy || !dirPath.trim()}
                          className={`${buttonClass} ml-auto border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20`}
                        >
                          <FolderPlus className="w-3.5 h-3.5" />
                          APPROVE
                        </button>
                      </div>
                      <p className="text-[10px] text-echo-muted leading-relaxed">
                        Drive roots and protected system paths are refused. Credential files are never indexed.
                      </p>
                    </div>
                  </Panel>

                  <Panel title="INDEXING SETTINGS" icon={<Settings2 className="w-3.5 h-3.5" />}>
                    {settingsDraft && (
                      <div className="space-y-2">
                        <div className="flex flex-wrap gap-4">
                          {(
                            [
                              ['content_indexing', 'Index contents'],
                              ['ocr_enabled', 'OCR images'],
                              ['include_hidden', 'Include hidden'],
                            ] as [keyof FileSettings, string][]
                          ).map(([key, label]) => (
                            <label key={key} className="flex items-center gap-1.5 text-[11px] text-gray-300 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={Boolean(settingsDraft[key])}
                                onChange={(event) =>
                                  setSettingsDraft({ ...settingsDraft, [key]: event.target.checked })
                                }
                                className="accent-echo-cyan"
                              />
                              {label}
                            </label>
                          ))}
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                          {(
                            [
                              ['max_file_size_mb', 'Max content MB'],
                              ['max_index_files', 'Max files'],
                              ['bulk_confirm_threshold', 'Bulk threshold'],
                            ] as [keyof FileSettings, string][]
                          ).map(([key, label]) => (
                            <Field key={key} label={label}>
                              <input
                                type="number"
                                min={1}
                                value={Number(settingsDraft[key])}
                                onChange={(event) =>
                                  setSettingsDraft({
                                    ...settingsDraft,
                                    [key]: Number(event.target.value) || 1,
                                  })
                                }
                                className={inputClass}
                              />
                            </Field>
                          ))}
                        </div>
                        <div className="flex justify-end pt-1">
                          <button
                            onClick={handleSaveSettings}
                            disabled={busy}
                            className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20`}
                          >
                            SAVE SETTINGS
                          </button>
                        </div>
                      </div>
                    )}
                  </Panel>
                </div>

                <Panel title="APPROVED ROOTS" icon={<FolderTree className="w-3.5 h-3.5" />}>
                  {directories.length === 0 ? (
                    <p className="text-xs text-echo-muted py-8 text-center">
                      No directories approved. File search is completely disabled until you add one.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {directories.map((directory) => (
                        <div
                          key={directory.id}
                          className="rounded-sm border border-echo-border bg-[#07090E] p-2.5 space-y-1.5"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <FolderOpen className="w-3.5 h-3.5 text-echo-cyan flex-shrink-0" />
                                <span className="text-xs text-white font-medium truncate">
                                  {directory.label || basename(directory.path)}
                                </span>
                                {!directory.recursive && <Chip label="TOP LEVEL" />}
                                <Chip label={`${directory.file_count} FILES`} />
                              </div>
                              <div className="font-mono text-[10px] text-echo-muted truncate mt-0.5">
                                {directory.path}
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              <button
                                onClick={() => handleIndex(directory.id)}
                                disabled={indexing}
                                className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/5 text-echo-cyan hover:bg-echo-cyan/15`}
                              >
                                <RefreshCw className={`w-3 h-3 ${indexing ? 'animate-spin' : ''}`} />
                                INDEX
                              </button>
                              <button
                                onClick={() => handleRemoveDirectory(directory)}
                                disabled={busy}
                                className={`${buttonClass} ${
                                  confirmRemove === directory.id
                                    ? 'border-echo-danger/50 bg-echo-danger/10 text-echo-danger'
                                    : 'border-echo-border text-echo-muted hover:text-echo-danger hover:border-echo-danger/40'
                                }`}
                              >
                                {confirmRemove === directory.id ? 'CONFIRM REMOVE' : 'REMOVE'}
                              </button>
                            </div>
                          </div>
                          <div className="font-mono text-[10px] text-echo-muted flex items-center gap-3">
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              indexed {timeAgo(directory.last_indexed_at)}
                            </span>
                            <span>added {formatWhen(directory.created_at)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>
            )}

            {/* ACTIVITY ---------------------------------------------------- */}
            {tab === 'activity' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="font-mono text-[10px] text-echo-muted">
                    Every file action is audited locally. Removing a directory or quarantining copies never deletes files.
                  </p>
                  <button
                    onClick={loadActivity}
                    className={`${buttonClass} border-echo-border text-echo-muted hover:text-white`}
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    REFRESH
                  </button>
                </div>
                {activity.length === 0 ? (
                  <div className="py-16 text-center space-y-2">
                    <History className="w-8 h-8 text-echo-muted/40 mx-auto" />
                    <p className="text-xs text-echo-muted">No file actions recorded yet.</p>
                  </div>
                ) : (
                  <div className="rounded-sm border border-echo-border overflow-hidden">
                    {activity.map((entry) => (
                      <div
                        key={entry.id}
                        className="grid grid-cols-[150px_70px_1fr_130px] gap-2 px-3 py-2 border-b border-echo-border/60 last:border-b-0 items-start"
                      >
                        <span className="font-mono text-[10px] text-echo-cyan">{entry.action.toUpperCase()}</span>
                        <span
                          className={`font-mono text-[10px] ${
                            entry.status === 'ok'
                              ? 'text-echo-success'
                              : entry.status === 'blocked'
                              ? 'text-echo-warning'
                              : 'text-echo-danger'
                          }`}
                        >
                          {entry.status.toUpperCase()}
                        </span>
                        <div className="min-w-0 text-[11px] text-gray-300 space-y-0.5">
                          {entry.source_path && (
                            <div className="truncate font-mono text-[10px]">{entry.source_path}</div>
                          )}
                          {entry.target_path && (
                            <div className="flex items-center gap-1 truncate font-mono text-[10px] text-echo-muted">
                              <ArrowRight className="w-3 h-3 flex-shrink-0" />
                              {entry.target_path}
                            </div>
                          )}
                          {!entry.source_path && !entry.target_path && (
                            <span className="font-mono text-[10px] text-echo-muted">
                              {Object.keys(entry.details || {}).length
                                ? JSON.stringify(entry.details)
                                : '—'}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[10px] text-echo-muted text-right">
                          {formatWhen(entry.created_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Details inspector */}
          {selected && (
            <aside className="w-[380px] border-l border-echo-border bg-[#090C12] flex flex-col min-h-0 flex-shrink-0">
              <div className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
                <span className="font-mono text-[10px] tracking-wider text-echo-cyan">FILE INSPECTOR</span>
                <button
                  onClick={() => {
                    setSelected(null);
                    setDetails(null);
                    setSummary(null);
                  }}
                  className="p-1 text-echo-muted hover:text-white"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                <div>
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-echo-cyan flex-shrink-0" />
                    <span className="text-sm text-white font-semibold break-all">{selected.name}</span>
                  </div>
                  <div className="font-mono text-[10px] text-echo-muted break-all mt-1">{selected.path}</div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    <Chip
                      label={CATEGORY_LABEL[selected.category] || selected.category}
                      className={CATEGORY_TONE[selected.category] || CATEGORY_TONE.other}
                    />
                    <Chip label={formatBytes(selected.size_bytes)} />
                    <Chip
                      label={selected.content_status.toUpperCase()}
                      className={
                        selected.content_status === 'indexed'
                          ? 'border-echo-success/30 bg-echo-success/5 text-echo-success'
                          : 'border-echo-border bg-[#121721] text-echo-muted'
                      }
                    />
                  </div>
                </div>

                <div className="rounded-sm border border-echo-border bg-[#07090E] p-2 space-y-1 font-mono text-[10px]">
                  <div className="flex justify-between gap-2">
                    <span className="text-echo-muted">MODIFIED</span>
                    <span className="text-gray-300">{formatWhen(selected.modified_at)}</span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-echo-muted">INDEXED</span>
                    <span className="text-gray-300">{formatWhen(selected.indexed_at)}</span>
                  </div>
                  {details?.content_hash && (
                    <div className="flex justify-between gap-2">
                      <span className="text-echo-muted">SHA-256</span>
                      <span className="text-gray-300 truncate max-w-[210px]" title={details.content_hash}>
                        {details.content_hash.slice(0, 24)}…
                      </span>
                    </div>
                  )}
                  {details?.metadata &&
                    Object.entries(details.metadata)
                      .filter(([, value]) => value !== null && value !== undefined && value !== '')
                      .slice(0, 10)
                      .map(([key, value]) => (
                        <div key={key} className="flex justify-between gap-2">
                          <span className="text-echo-muted uppercase">{key}</span>
                          <span className="text-gray-300 truncate max-w-[210px]" title={String(value)}>
                            {String(value)}
                          </span>
                        </div>
                      ))}
                </div>

                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    onClick={handleOpen}
                    disabled={busy}
                    className={`${buttonClass} border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan hover:bg-echo-cyan/20`}
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    OPEN
                  </button>
                  <button
                    onClick={handleSummarize}
                    disabled={summarizing}
                    className={`${buttonClass} border-echo-purple/40 bg-echo-purple/10 text-echo-purple hover:bg-echo-purple/20`}
                  >
                    <Sparkles className={`w-3.5 h-3.5 ${summarizing ? 'animate-pulse' : ''}`} />
                    {summarizing ? 'SUMMARIZING…' : 'SUMMARIZE'}
                  </button>
                </div>

                <div className="rounded-sm border border-echo-border bg-[#07090E] p-2 space-y-2">
                  <span className="font-mono text-[10px] tracking-wider text-echo-muted">RENAME</span>
                  <div className="flex gap-1.5">
                    <input
                      value={renameDraft}
                      onChange={(event) => setRenameDraft(event.target.value)}
                      className={inputClass}
                    />
                    <button
                      onClick={handleRename}
                      disabled={busy || !renameDraft.trim() || renameDraft === selected.name}
                      className={`${buttonClass} border-echo-border text-gray-300 hover:text-white flex-shrink-0`}
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="rounded-sm border border-echo-border bg-[#07090E] p-2 space-y-2">
                  <span className="font-mono text-[10px] tracking-wider text-echo-muted">
                    COPY / MOVE DESTINATION
                  </span>
                  <input
                    value={destination}
                    onChange={(event) => setDestination(event.target.value)}
                    placeholder="Approved folder path"
                    className={inputClass}
                  />
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      onClick={() => handleCopyMove('copy')}
                      disabled={busy || !destination.trim()}
                      className={`${buttonClass} border-echo-border text-gray-300 hover:text-white`}
                    >
                      <Copy className="w-3.5 h-3.5" />
                      COPY
                    </button>
                    <button
                      onClick={() => handleCopyMove('move')}
                      disabled={busy || !destination.trim()}
                      className={`${buttonClass} border-echo-warning/40 bg-echo-warning/5 text-echo-warning hover:bg-echo-warning/15`}
                    >
                      <FolderInput className="w-3.5 h-3.5" />
                      MOVE
                    </button>
                  </div>
                  <p className="text-[10px] text-echo-muted leading-relaxed">
                    Both paths must sit inside an approved directory. Overwrites always ask first.
                  </p>
                </div>

                {summary && (
                  <div className="rounded-sm border border-echo-purple/30 bg-echo-purple/5 p-2 space-y-1.5">
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-echo-purple flex items-center gap-1">
                        <Sparkles className="w-3 h-3" />
                        {summary.ai_used ? 'AI SUMMARY' : 'EXTRACTIVE SUMMARY'}
                      </span>
                      <span className="text-echo-muted">{summary.chars ?? 0} chars</span>
                    </div>
                    <p className="text-[11px] text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {summary.summary || summary.message || 'No summary produced.'}
                    </p>
                    {summary.warning && (
                      <p className="text-[10px] text-echo-warning flex items-center gap-1">
                        <Info className="w-3 h-3" />
                        {summary.warning}
                      </p>
                    )}
                  </div>
                )}

                {detailsLoading ? (
                  <p className="font-mono text-[10px] text-echo-muted">Loading details…</p>
                ) : details?.preview ? (
                  <div className="rounded-sm border border-echo-border bg-[#07090E] p-2 space-y-1">
                    <span className="font-mono text-[10px] tracking-wider text-echo-muted">CONTENT PREVIEW</span>
                    <pre className="text-[10px] text-gray-400 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                      {details.preview}
                    </pre>
                  </div>
                ) : (
                  <p className="font-mono text-[10px] text-echo-muted flex items-center gap-1">
                    <Info className="w-3 h-3" />
                    No text preview available for this file.
                  </p>
                )}
              </div>
            </aside>
          )}
        </div>

        {/* Confirmation overlay */}
        {pending && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-lg border border-echo-warning/40 bg-[#0B0E14] shadow-2xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-echo-border bg-[#12100A]">
                <AlertTriangle className="w-4 h-4 text-echo-warning" />
                <h3 className="font-mono text-xs tracking-wider text-white">{pending.title}</h3>
              </div>
              <div className="p-4 space-y-3">
                <p className="text-xs text-gray-300 leading-relaxed">{pending.message}</p>
                {pending.planKind === 'quarantine' && (
                  <div className="rounded-sm border border-echo-success/30 bg-echo-success/5 p-2 flex items-start gap-2">
                    <ShieldCheck className="w-4 h-4 text-echo-success flex-shrink-0 mt-0.5" />
                    <span className="text-[11px] text-echo-success">
                      Files are moved into _ECHO_DUPLICATES. Nothing is deleted and the keeper copy never moves.
                    </span>
                  </div>
                )}
                {pending.plan && pending.plan.plan.length > 0 && (
                  <div className="rounded-sm border border-echo-border bg-[#07090E] max-h-52 overflow-y-auto">
                    {pending.plan.plan.slice(0, 30).map((item) => (
                      <div key={`${item.source}-${item.target}`} className="px-2 py-1.5 border-b border-echo-border/60 last:border-b-0">
                        <div className="font-mono text-[10px] text-gray-300 truncate">{basename(item.source)}</div>
                        <div className="flex items-center gap-1 font-mono text-[10px] text-echo-muted">
                          <ChevronRight className="w-3 h-3 flex-shrink-0" />
                          <span className="truncate">{item.target}</span>
                        </div>
                      </div>
                    ))}
                    {pending.plan.plan.length > 30 && (
                      <div className="px-2 py-1.5 font-mono text-[10px] text-echo-muted">
                        +{pending.plan.plan.length - 30} more operations
                      </div>
                    )}
                  </div>
                )}
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    onClick={() => setPending(null)}
                    disabled={busy}
                    className={`${buttonClass} border-echo-border text-echo-muted hover:text-white`}
                  >
                    CANCEL
                  </button>
                  <button
                    onClick={runPending}
                    disabled={busy}
                    className={`${buttonClass} border-echo-warning/50 bg-echo-warning/15 text-echo-warning hover:bg-echo-warning/25`}
                  >
                    <Play className="w-3.5 h-3.5" />
                    {busy ? 'WORKING…' : pending.confirmLabel.toUpperCase()}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
