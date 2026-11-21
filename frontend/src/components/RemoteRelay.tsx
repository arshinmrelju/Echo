import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bell,
  Check,
  Clock,
  Copy,
  KeyRound,
  Link2,
  Lock,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Satellite,
  ScrollText,
  Send,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  Trash2,
  UserPlus,
  Users,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import { apiClient } from '../api/client';
import {
  RemoteCommand,
  RemoteNotification,
  RemotePairingCode,
  RemoteQueueStatus,
  RemoteSettings,
  RemoteSeverity,
  RemoteStatus,
  RemoteTask,
  RemoteUser,
} from '../types';

type TabKey = 'link' | 'access' | 'notifications' | 'audit';

interface RemoteRelayProps {
  isOpen: boolean;
  onClose: () => void;
  onBadgeChange?: (status: RemoteStatus) => void;
}

const SEVERITY_STYLE: Record<RemoteSeverity, string> = {
  info: 'border-echo-muted/30 bg-echo-muted/10 text-echo-muted',
  notice: 'border-echo-blue/40 bg-echo-blue/10 text-echo-blue',
  warning: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
  critical: 'border-echo-danger/50 bg-echo-danger/10 text-echo-danger',
};

const QUEUE_STYLE: Record<RemoteQueueStatus, string> = {
  queued: 'border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan',
  sending: 'border-echo-blue/40 bg-echo-blue/10 text-echo-blue',
  sent: 'border-echo-success/40 bg-echo-success/10 text-echo-success',
  failed: 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger',
  expired: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
  suppressed: 'border-echo-muted/30 bg-echo-muted/10 text-echo-muted',
};

const COMMAND_STATUS_STYLE: Record<string, string> = {
  ok: 'text-echo-success',
  received: 'text-echo-cyan',
  rejected: 'text-echo-danger',
  rate_limited: 'text-echo-warning',
  failed: 'text-echo-danger',
  pair_failed: 'text-echo-warning',
};

const formatClock = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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

const minutesLeft = (value: string | null | undefined, now: number) => {
  if (!value) return '—';
  const ms = new Date(value).getTime() - now;
  if (Number.isNaN(ms) || ms <= 0) return 'expired';
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
};

const parseArgs = (value: string | null | undefined) => {
  if (!value) return '{}';
  try {
    return JSON.stringify(JSON.parse(value));
  } catch {
    return value;
  }
};

const Chip: React.FC<{ label: string; tone?: 'live' | 'idle' | 'error' | 'warning' | 'neutral' }> = ({
  label,
  tone = 'neutral',
}) => {
  const tones: Record<string, string> = {
    live: 'border-echo-success/40 bg-echo-success/10 text-echo-success',
    idle: 'border-echo-border bg-[#121721] text-echo-muted',
    error: 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger',
    warning: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
    neutral: 'border-echo-cyan/30 bg-echo-cyan/5 text-echo-cyan',
  };
  return (
    <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-sm border tracking-wider ${tones[tone]}`}>
      {label}
    </span>
  );
};

const Panel: React.FC<{ title: string; icon: React.ReactNode; aside?: React.ReactNode; children: React.ReactNode }> = ({
  title,
  icon,
  aside,
  children,
}) => (
  <section className="rounded-lg border border-echo-border bg-[#0A0D13]">
    <header className="flex items-center justify-between px-3 py-2 border-b border-echo-border">
      <div className="flex items-center gap-2 text-echo-muted">
        {icon}
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-gray-300">{title}</span>
      </div>
      {aside}
    </header>
    <div className="p-3">{children}</div>
  </section>
);

const Toggle: React.FC<{ label: string; hint?: string; checked: boolean; onChange: (value: boolean) => void }> = ({
  label,
  hint,
  checked,
  onChange,
}) => (
  <button
    type="button"
    onClick={() => onChange(!checked)}
    className="w-full flex items-start justify-between gap-3 py-2 text-left group"
  >
    <div className="min-w-0">
      <div className="text-xs text-gray-200 group-hover:text-white">{label}</div>
      {hint && <div className="text-[10px] text-echo-muted mt-0.5">{hint}</div>}
    </div>
    <span
      className={`mt-0.5 w-8 h-4 rounded-full border flex items-center px-0.5 transition-colors ${
        checked ? 'bg-echo-cyan/20 border-echo-cyan/60 justify-end' : 'bg-[#121721] border-echo-border justify-start'
      }`}
    >
      <span className={`w-2.5 h-2.5 rounded-full ${checked ? 'bg-echo-cyan' : 'bg-echo-muted'}`} />
    </span>
  </button>
);

const Stat: React.FC<{ label: string; value: React.ReactNode; tone?: string }> = ({ label, value, tone }) => (
  <div className="rounded-sm border border-echo-border bg-[#0D1118] px-2.5 py-2">
    <div className="font-mono text-[9px] tracking-wider text-echo-muted uppercase">{label}</div>
    <div className={`mt-1 font-mono text-sm ${tone || 'text-gray-200'}`}>{value}</div>
  </div>
);

export const RemoteRelay: React.FC<RemoteRelayProps> = ({ isOpen, onClose, onBadgeChange }) => {
  const [tab, setTab] = useState<TabKey>('link');
  const [status, setStatus] = useState<RemoteStatus | null>(null);
  const [draft, setDraft] = useState<RemoteSettings | null>(null);
  const [commands, setCommands] = useState<RemoteCommand[]>([]);
  const [notifications, setNotifications] = useState<RemoteNotification[]>([]);
  const [tasks, setTasks] = useState<RemoteTask[]>([]);
  const [pairing, setPairing] = useState<RemotePairingCode | null>(null);
  const [tokenDraft, setTokenDraft] = useState('');
  const [ownerDraft, setOwnerDraft] = useState('');
  const [newUserId, setNewUserId] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [categoriesDraft, setCategoriesDraft] = useState('');
  const [clock, setClock] = useState(Date.now());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const draftLoaded = useRef(false);

  const flash = useCallback((message: string, isError = false) => {
    if (isError) {
      setError(message);
      setNotice(null);
    } else {
      setNotice(message);
      setError(null);
    }
  }, []);

  const applyStatus = useCallback(
    (next: RemoteStatus) => {
      setStatus(next);
      onBadgeChange?.(next);
    },
    [onBadgeChange]
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [nextStatus, commandList, notificationList, taskList] = await Promise.all([
        apiClient.getRemoteStatus(),
        apiClient.listRemoteCommands(80),
        apiClient.listRemoteNotifications(undefined, 60),
        apiClient.listRemoteTasks(30),
      ]);
      applyStatus(nextStatus);
      if (!draftLoaded.current) {
        setDraft(nextStatus.settings);
        setCategoriesDraft(nextStatus.settings.monitor_event_categories.join(', '));
        setOwnerDraft(
          nextStatus.settings.effective_owner_user_id
            ? String(nextStatus.settings.effective_owner_user_id)
            : ''
        );
        draftLoaded.current = true;
      }
      setCommands(commandList.commands);
      setNotifications(notificationList.notifications);
      setTasks(taskList.tasks);
      setError(null);
    } catch (e) {
      setError(`Could not load remote relay: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [applyStatus]);

  useEffect(() => {
    if (!isOpen) return;
    draftLoaded.current = false;
    setPairing(null);
    setTokenDraft('');
    setNotice(null);
    setError(null);
    loadAll();
    const poll = setInterval(loadAll, 5000);
    return () => clearInterval(poll);
  }, [isOpen, loadAll]);

  useEffect(() => {
    if (!isOpen) return;
    const tick = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [isOpen]);

  const remote = status?.remote_status;
  const queue = status?.queue;
  const relayLabel = status?.paused
    ? 'PAUSED'
    : status?.running && status?.connected
    ? 'LINKED'
    : status?.enabled
    ? 'OFFLINE'
    : 'IDLE';
  const relayTone: 'live' | 'idle' | 'error' | 'warning' = status?.paused
    ? 'warning'
    : status?.running && status?.connected
    ? 'live'
    : status?.enabled
    ? 'error'
    : 'idle';

  const ownerUser = useMemo(
    () => status?.users.find((u) => u.role === 'owner') || null,
    [status?.users]
  );
  const allowedUsers = useMemo(() => status?.users.filter((u) => u.role !== 'owner') || [], [status?.users]);
  const pending = status?.pending_actions || [];
  const failedNotifications = notifications.filter((n) =>
    ['failed', 'expired', 'suppressed'].includes(n.status)
  );

  const withBusy = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      flash(String(e instanceof Error ? e.message : e), true);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveConnection = () =>
    withBusy(async () => {
      const payload: { bot_token?: string; owner_user_id?: number } = {};
      if (tokenDraft.trim()) payload.bot_token = tokenDraft.trim();
      if (ownerDraft.trim()) {
        const parsed = Number(ownerDraft.trim());
        if (!Number.isInteger(parsed) || parsed <= 0) {
          flash('Owner id must be a positive numeric Telegram user id.', true);
          return;
        }
        payload.owner_user_id = parsed;
      }
      if (!Object.keys(payload).length) {
        flash('Nothing to save. Enter a bot token or owner id.');
        return;
      }
      const res = await apiClient.updateRemoteSettings(payload);
      applyStatus(res.status);
      setTokenDraft('');
      flash('Channel credentials updated.');
    });

  const handleToggleRelay = () =>
    withBusy(async () => {
      const res = status?.running ? await apiClient.stopRemote() : await apiClient.startRemote();
      applyStatus(res.status);
      if (!status?.running && !res.success) {
        flash(res.status.last_error || 'Relay did not start. Check the bot token.', true);
      } else {
        flash(res.status.running ? 'Relay started.' : 'Relay stopped.');
      }
    });

  const handleReconnect = () =>
    withBusy(async () => {
      const res = await apiClient.reconnectRemote();
      applyStatus(res.status);
      flash(res.success ? 'Relay reconnected.' : res.status.last_error || 'Relay could not reconnect.', !res.success);
    });

  const handlePause = () =>
    withBusy(async () => {
      const res = status?.paused ? await apiClient.resumeRemote() : await apiClient.pauseRemote('Paused from desktop');
      applyStatus(res.status);
      flash(res.status.paused ? 'Remote commands paused.' : 'Remote commands resumed.');
    });

  const handleGeneratePairing = () =>
    withBusy(async () => {
      const code = await apiClient.startRemotePairing();
      setPairing(code);
      setCopied(false);
      flash('Pairing code generated.');
    });

  const handleCancelPairing = () =>
    withBusy(async () => {
      await apiClient.cancelRemotePairing();
      setPairing(null);
      flash('Pairing cancelled.');
    });

  const handleCopy = async () => {
    if (!pairing) return;
    try {
      await navigator.clipboard.writeText(`/pair ${pairing.code}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      flash('Clipboard unavailable — copy the code manually.', true);
    }
  };

  const handleAddUser = () =>
    withBusy(async () => {
      const parsed = Number(newUserId.trim());
      if (!Number.isInteger(parsed) || parsed <= 0) {
        flash('Enter a positive numeric Telegram user id.', true);
        return;
      }
      await apiClient.addRemoteUser(parsed, newUsername.trim() || undefined);
      setNewUserId('');
      setNewUsername('');
      await loadAll();
      flash('Allowed user added.');
    });

  const handleRemoveUser = (user: RemoteUser) =>
    withBusy(async () => {
      await apiClient.removeRemoteUser(user.telegram_id);
      await loadAll();
      flash(`${user.display_name || user.telegram_id} removed.`);
    });

  const handleSavePolicy = () =>
    withBusy(async () => {
      if (!draft) return;
      const categories = categoriesDraft
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const res = await apiClient.updateRemoteSettings({
        notify_critical_alerts: draft.notify_critical_alerts,
        notify_warnings: draft.notify_warnings,
        notify_task_results: draft.notify_task_results,
        notify_approval_requests: draft.notify_approval_requests,
        notify_connectivity: draft.notify_connectivity,
        notify_monitor_events: draft.notify_monitor_events,
        monitor_event_min_severity: draft.monitor_event_min_severity,
        monitor_event_categories: categories,
        screenshot_enabled: draft.screenshot_enabled,
        max_screenshot_mb: draft.max_screenshot_mb,
        queue_ttl_hours: draft.queue_ttl_hours,
      });
      applyStatus(res.status);
      setDraft(res.status.settings);
      setCategoriesDraft(res.status.settings.monitor_event_categories.join(', '));
      flash('Notification policy saved.');
    });

  const handleTestNotification = () =>
    withBusy(async () => {
      await apiClient.testRemoteNotification();
      await loadAll();
      flash('Test notification queued for the owner.');
    });

  const handleRetry = (notification: RemoteNotification) =>
    withBusy(async () => {
      await apiClient.retryRemoteNotification(notification.id);
      await loadAll();
      flash('Notification re-queued.');
    });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3">
      <div className="w-full max-w-[1180px] h-[90vh] flex flex-col rounded-lg border border-echo-border bg-[#07090E] shadow-2xl overflow-hidden">
        <header className="border-b border-echo-border bg-[#0B0E14]">
          <div className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-sm border border-echo-cyan/40 bg-echo-cyan/5 flex items-center justify-center text-echo-cyan">
                <Satellite className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-mono text-sm tracking-[0.18em] text-white">REMOTE RELAY</h2>
                  <Chip label={relayLabel} tone={relayTone} />
                  {status?.bot_username && <Chip label={`@${status.bot_username}`} />}
                  {status?.paused && <Chip label="COMMANDS BLOCKED" tone="warning" />}
                </div>
                <div className="mt-1 flex items-center gap-3 font-mono text-[10px] text-echo-muted truncate">
                  <span>TRANSPORT telegram_long_poll</span>
                  <span>INBOUND {status?.listener.inbound_ports ?? 0}</span>
                  <span>HEARTBEAT {timeAgo(remote?.last_heartbeat_at)}</span>
                  <span>QUEUE {queue?.queued ?? 0}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleToggleRelay}
                disabled={busy}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border font-mono text-[11px] tracking-wide transition-colors disabled:opacity-50 ${
                  status?.running
                    ? 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger hover:bg-echo-danger/20'
                    : 'border-echo-success/40 bg-echo-success/10 text-echo-success hover:bg-echo-success/20'
                }`}
              >
                {status?.running ? <X className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                {status?.running ? 'STOP' : 'START'}
              </button>
              <button
                onClick={handlePause}
                disabled={busy || !status?.enabled}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border font-mono text-[11px] tracking-wide transition-colors disabled:opacity-40 ${
                  status?.paused
                    ? 'border-echo-success/40 bg-echo-success/10 text-echo-success hover:bg-echo-success/20'
                    : 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning hover:bg-echo-warning/20'
                }`}
              >
                {status?.paused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                {status?.paused ? 'RESUME' : 'PAUSE'}
              </button>
              <button
                onClick={handleReconnect}
                disabled={busy}
                className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-muted/50 transition-colors disabled:opacity-40"
                title="Reconnect relay"
              >
                <RotateCcw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={loadAll}
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
              <span className="text-echo-muted">OWNER</span>
              <span className={ownerUser ? 'text-echo-success' : 'text-echo-warning'}>
                {ownerUser ? ownerUser.display_name || ownerUser.telegram_id : 'UNPAIRED'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">BOT TOKEN</span>
              <span className={status?.token_configured ? 'text-echo-success' : 'text-echo-warning'}>
                {status?.token_configured ? `CONFIGURED ${status.settings.bot_token_hint}` : 'MISSING'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">SCREENSHOTS</span>
              <span className={status?.settings.screenshot_enabled ? 'text-echo-cyan' : 'text-echo-muted'}>
                {status?.settings.screenshot_enabled ? 'OWNER ONLY' : 'DISABLED'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5">
              <span className="text-echo-muted">PENDING APPROVALS</span>
              <span className={pending.length ? 'text-echo-warning' : 'text-echo-success'}>{pending.length}</span>
            </div>
          </div>
        </header>

        <nav className="flex items-center gap-1 px-4 border-b border-echo-border bg-[#090C12]">
          {(
            [
              ['link', 'LINK'],
              ['access', `ACCESS${allowedUsers.length ? ` ${allowedUsers.length}` : ''}`],
              ['notifications', `NOTIFICATIONS${queue?.queued ? ` ${queue.queued}` : ''}`],
              ['audit', 'AUDIT'],
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
          <div className="ml-auto flex items-center gap-2 py-1 min-w-0">
            {error && <span className="font-mono text-[10px] text-echo-danger truncate max-w-[420px]">{error}</span>}
            {notice && <span className="font-mono text-[10px] text-echo-success truncate max-w-[360px]">{notice}</span>}
          </div>
        </nav>

        <div className="flex-1 overflow-y-auto p-4">
          {tab === 'link' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <Panel title="Channel Credentials" icon={<KeyRound className="w-3.5 h-3.5" />}>
                  <div className="space-y-3">
                    <label className="block">
                      <span className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">Bot token</span>
                      <input
                        type="password"
                        value={tokenDraft}
                        onChange={(e) => setTokenDraft(e.target.value)}
                        placeholder={
                          status?.token_configured
                            ? 'Configured — enter a new token to replace it'
                            : '123456789:AA… (from @BotFather)'
                        }
                        autoComplete="off"
                        className="mt-1 w-full px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                      />
                      <span className="mt-1 block text-[10px] text-echo-muted">
                        Stored locally. Never returned by the API, never written to logs.
                      </span>
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <label className="block">
                        <span className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">
                          Owner Telegram id
                        </span>
                        <input
                          inputMode="numeric"
                          value={ownerDraft}
                          onChange={(e) => setOwnerDraft(e.target.value)}
                          placeholder="Numeric id — or pair from Telegram"
                          className="mt-1 w-full px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                        />
                      </label>
                      <div>
                        <span className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">Bot identity</span>
                        <div className="mt-1 px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border font-mono text-xs text-gray-300 truncate">
                          {status?.bot_username ? `@${status.bot_username}` : 'Not resolved until the relay starts'}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[10px] text-echo-muted font-mono">
                        OWNER {status?.settings.effective_owner_user_id ?? '—'} · RATE{' '}
                        {status?.settings.command_rate_limit ?? '—'} CMD/MIN
                      </span>
                      <button
                        onClick={handleSaveConnection}
                        disabled={busy}
                        className="px-3 py-1.5 rounded-sm border border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan font-mono text-[11px] tracking-wide hover:bg-echo-cyan/20 disabled:opacity-50"
                      >
                        SAVE CREDENTIALS
                      </button>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Relay Control"
                  icon={<Link2 className="w-3.5 h-3.5" />}
                  aside={
                    <span className={`font-mono text-[10px] ${status?.connected ? 'text-echo-success' : 'text-echo-warning'}`}>
                      {status?.connected ? 'ONLINE' : 'OFFLINE'}
                    </span>
                  }
                >
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <Stat
                      label="PC"
                      value={remote?.pc_online ? 'ONLINE' : 'OFFLINE'}
                      tone={remote?.pc_online ? 'text-echo-success' : 'text-echo-danger'}
                    />
                    <Stat
                      label="ECHO"
                      value={(remote?.echo_state || 'unknown').toUpperCase()}
                      tone={remote?.paused ? 'text-echo-warning' : 'text-echo-success'}
                    />
                    <Stat
                      label="Health"
                      value={(remote?.health.state || 'unknown').toUpperCase()}
                      tone={
                        remote?.health.state === 'critical'
                          ? 'text-echo-danger'
                          : remote?.health.state === 'warning'
                          ? 'text-echo-warning'
                          : 'text-echo-success'
                      }
                    />
                    <Stat label="Last poll" value={timeAgo(remote?.relay.last_poll_at)} />
                  </div>

                  <div className="mt-3 rounded-sm border border-echo-border bg-[#0D1118] px-3 py-2">
                    <div className="font-mono text-[9px] tracking-wider text-echo-muted uppercase">Current task</div>
                    {remote?.current_task ? (
                      <div className="mt-1 flex items-center justify-between gap-3">
                        <span className="text-xs text-gray-200 truncate">{remote.current_task.goal}</span>
                        <Chip label={remote.current_task.status.toUpperCase()} />
                      </div>
                    ) : (
                      <div className="mt-1 font-mono text-xs text-echo-muted">IDLE</div>
                    )}
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="flex items-center justify-between text-echo-muted">
                      <span>RECONNECT ATTEMPTS</span>
                      <span className="text-gray-300">{status?.reconnect_attempts ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-echo-muted">
                      <span>UPTIME SINCE</span>
                      <span className="text-gray-300">{status?.started_at ? timeAgo(status.started_at) : '—'}</span>
                    </div>
                  </div>

                  {status?.last_error && (
                    <div className="mt-3 flex items-start gap-2 rounded-sm border border-echo-danger/30 bg-echo-danger/5 px-2.5 py-2 text-[11px] text-echo-danger">
                      <ShieldAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      <span>{status.last_error}</span>
                    </div>
                  )}
                  {status?.paused && (
                    <div className="mt-3 flex items-start gap-2 rounded-sm border border-echo-warning/30 bg-echo-warning/5 px-2.5 py-2 text-[11px] text-echo-warning">
                      <Pause className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      <span>Remote commands are paused. {status.pause_reason || 'Send /resume from Telegram or resume here.'}</span>
                    </div>
                  )}
                </Panel>
              </div>

              <div className="space-y-4">
                <Panel title="Owner Pairing" icon={<Smartphone className="w-3.5 h-3.5" />}>
                  {pairing ? (
                    <div className="space-y-3">
                      <div className="rounded-sm border border-echo-cyan/40 bg-echo-cyan/5 px-3 py-3 text-center">
                        <div className="font-mono text-[9px] tracking-[0.2em] text-echo-muted">ONE-TIME CODE</div>
                        <div className="mt-1 font-mono text-2xl tracking-[0.3em] text-echo-cyan select-all">{pairing.code}</div>
                        <div className="mt-1 font-mono text-[10px] text-echo-muted">
                          EXPIRES {minutesLeft(pairing.expires_at, clock)} · SINGLE USE
                        </div>
                      </div>
                      <button
                        onClick={handleCopy}
                        className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-sm border border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan font-mono text-[11px] hover:bg-echo-cyan/20"
                      >
                        {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                        {copied ? 'COPIED /pair COMMAND' : 'COPY /pair COMMAND'}
                      </button>
                      <p className="text-[11px] text-echo-muted leading-relaxed">{pairing.instructions}</p>
                      <button
                        onClick={handleCancelPairing}
                        className="w-full px-2.5 py-1.5 rounded-sm border border-echo-border text-echo-muted font-mono text-[10px] hover:text-white"
                      >
                        CANCEL PAIRING
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-[11px] text-echo-muted leading-relaxed">
                        Send <span className="font-mono text-gray-300">/pair CODE</span> from your private Telegram chat
                        with the bot. The first account to redeem a valid code becomes the owner.
                      </p>
                      {status?.active_pairing && status.pairing_expires_at ? (
                        <div className="rounded-sm border border-echo-cyan/30 bg-echo-cyan/5 px-2.5 py-2">
                          <div className="font-mono text-[9px] tracking-wider text-echo-muted">CODE ACTIVE</div>
                          <div className="mt-1 font-mono text-xs text-echo-cyan">
                            EXPIRES IN {minutesLeft(status.pairing_expires_at, clock)}
                          </div>
                        </div>
                      ) : null}
                      <button
                        onClick={handleGeneratePairing}
                        disabled={busy || !status?.token_configured}
                        className="w-full flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-sm border border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan font-mono text-[11px] hover:bg-echo-cyan/20 disabled:opacity-40"
                      >
                        <KeyRound className="w-3.5 h-3.5" />
                        GENERATE PAIRING CODE
                      </button>
                      <div className="font-mono text-[10px] text-echo-muted">
                        TTL {status?.settings.pairing_ttl_seconds ?? 600}s · MAX{' '}
                        {status?.settings.pairing_attempt_limit ?? 5} ATTEMPTS /{' '}
                        {Math.round((status?.settings.pairing_attempt_window_seconds ?? 600) / 60)} MIN
                      </div>
                    </div>
                  )}
                </Panel>

                <Panel title="Privacy Posture" icon={<Lock className="w-3.5 h-3.5" />}>
                  <ul className="space-y-2 text-[11px] text-gray-300">
                    <li className="flex items-center justify-between">
                      <span className="text-echo-muted">Inbound ports</span>
                      <span className="font-mono text-echo-success">{status?.listener.inbound_ports ?? 0}</span>
                    </li>
                    <li className="flex items-center justify-between">
                      <span className="text-echo-muted">Transport</span>
                      <span className="font-mono text-echo-cyan">OUTBOUND LONG POLL</span>
                    </li>
                    <li className="flex items-center justify-between">
                      <span className="text-echo-muted">Screenshot delivery</span>
                      <span className="font-mono text-echo-cyan">OWNER ONLY</span>
                    </li>
                    <li className="flex items-center justify-between">
                      <span className="text-echo-muted">Credential requests</span>
                      <span className="font-mono text-echo-success">BLOCKED</span>
                    </li>
                    <li className="flex items-center justify-between">
                      <span className="text-echo-muted">Dangerous actions</span>
                      <span className="font-mono text-echo-warning">APPROVAL</span>
                    </li>
                  </ul>
                  <p className="mt-3 text-[10px] text-echo-muted leading-relaxed">
                    The desktop daemon never exposes a remote-control port. Telegram receives outbound requests only,
                    and the REST API stays bound to 127.0.0.1.
                  </p>
                </Panel>
              </div>
            </div>
          )}

          {tab === 'access' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <Panel
                  title="Allowed Users"
                  icon={<Users className="w-3.5 h-3.5" />}
                  aside={<span className="font-mono text-[10px] text-echo-muted">{allowedUsers.length} READ-ONLY</span>}
                >
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
                    <input
                      inputMode="numeric"
                      value={newUserId}
                      onChange={(e) => setNewUserId(e.target.value)}
                      placeholder="Telegram user id"
                      className="px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                    />
                    <input
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      placeholder="@username (optional)"
                      className="px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                    />
                    <button
                      onClick={handleAddUser}
                      disabled={busy}
                      className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm border border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan font-mono text-[11px] hover:bg-echo-cyan/20 disabled:opacity-50"
                    >
                      <UserPlus className="w-3.5 h-3.5" /> ADD
                    </button>
                  </div>

                  <div className="mt-3 divide-y divide-echo-border/60">
                    {allowedUsers.length === 0 ? (
                      <div className="py-6 text-center text-xs text-echo-muted">
                        No allowed users. Only the paired owner can talk to ECHO.
                      </div>
                    ) : (
                      allowedUsers.map((user) => (
                        <div key={user.telegram_id} className="flex items-center justify-between gap-3 py-2">
                          <div className="min-w-0">
                            <div className="text-xs text-gray-200 truncate">
                              {user.display_name || user.username || `User ${user.telegram_id}`}
                            </div>
                            <div className="font-mono text-[10px] text-echo-muted">
                              ID {user.telegram_id} · SEEN {timeAgo(user.last_seen_at)} · VIA {user.added_by || '—'}
                            </div>
                          </div>
                          <button
                            onClick={() => handleRemoveUser(user)}
                            className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-echo-danger hover:border-echo-danger/40"
                            title="Remove allowed user"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="mt-2 text-[10px] text-echo-muted">
                    Allowed users can run /status, /health, /events, and /tasks. Screenshots, app launches, tasks, and /
                    ask stay owner-only.
                  </p>
                </Panel>

                <Panel
                  title="Pending Dangerous Actions"
                  icon={<ShieldAlert className="w-3.5 h-3.5" />}
                  aside={
                    <span className={`font-mono text-[10px] ${pending.length ? 'text-echo-warning' : 'text-echo-muted'}`}>
                      {pending.length} WAITING
                    </span>
                  }
                >
                  {pending.length === 0 ? (
                    <div className="py-6 text-center text-xs text-echo-muted">
                      Nothing is waiting for approval. Remote app launches appear here and in the desktop approval
                      dialog.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {pending.map((action) => (
                        <div key={action.approval_id} className="rounded-sm border border-echo-warning/25 bg-[#12100A] px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-[11px] text-echo-warning">{action.tool_name}</span>
                            <Chip label="PENDING" tone="warning" />
                          </div>
                          <div className="mt-1 font-mono text-[10px] text-gray-400 break-all">
                            {parseArgs(action.arguments)}
                          </div>
                          <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-echo-muted">
                            <span>USER {action.telegram_id} · {action.command}</span>
                            <span>EXPIRES {minutesLeft(action.expires_at, clock)}</span>
                          </div>
                          <div className="mt-1 font-mono text-[10px] text-echo-cyan break-all">
                            /approve {action.approval_id}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>

              <div className="space-y-4">
                <Panel title="Owner" icon={<ShieldCheck className="w-3.5 h-3.5" />}>
                  {ownerUser ? (
                    <div className="space-y-2">
                      <div className="text-sm text-white">{ownerUser.display_name || 'Owner'}</div>
                      <div className="font-mono text-[10px] text-echo-muted">ID {ownerUser.telegram_id}</div>
                      {ownerUser.username && (
                        <div className="font-mono text-[10px] text-echo-muted">@{ownerUser.username}</div>
                      )}
                      <div className="font-mono text-[10px] text-echo-muted">
                        PAIRED {ownerUser.paired_at ? timeAgo(ownerUser.paired_at) : '—'}
                      </div>
                      <div className="font-mono text-[10px] text-echo-muted">
                        LAST SEEN {timeAgo(ownerUser.last_seen_at)}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-echo-warning">
                      No owner verified. Pair a Telegram account from the LINK tab before enabling commands.
                    </div>
                  )}
                  <p className="mt-3 text-[10px] text-echo-muted leading-relaxed">
                    Pairing a new account transfers ownership and removes the previous owner row. Allowed users cannot
                    approve actions.
                  </p>
                </Panel>

                <Panel title="Access Rules" icon={<Lock className="w-3.5 h-3.5" />}>
                  <ul className="space-y-2 text-[11px] text-gray-300">
                    <li>Private chats only — group messages are refused.</li>
                    <li>Rate limit {status?.settings.command_rate_limit ?? 20} commands / minute.</li>
                    <li>Dangerous tools always require a fresh approval.</li>
                    <li>Credentials and secrets are never in the command set.</li>
                  </ul>
                </Panel>
              </div>
            </div>
          )}

          {tab === 'notifications' && draft && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <Panel
                  title="Routing Policy"
                  icon={<Bell className="w-3.5 h-3.5" />}
                  aside={
                    <button
                      onClick={handleSavePolicy}
                      disabled={busy}
                      className="px-2.5 py-1 rounded-sm border border-echo-cyan/40 bg-echo-cyan/10 text-echo-cyan font-mono text-[10px] hover:bg-echo-cyan/20 disabled:opacity-50"
                    >
                      SAVE POLICY
                    </button>
                  }
                >
                  <div className="divide-y divide-echo-border/50">
                    <Toggle
                      label="Critical system alerts"
                      hint="CPU, disk, battery, thermal, and network emergencies"
                      checked={draft.notify_critical_alerts}
                      onChange={(v) => setDraft({ ...draft, notify_critical_alerts: v })}
                    />
                    <Toggle
                      label="Warnings"
                      hint="Alerts below critical severity"
                      checked={draft.notify_warnings}
                      onChange={(v) => setDraft({ ...draft, notify_warnings: v })}
                    />
                    <Toggle
                      label="Task results"
                      hint="Completed and failed local tasks"
                      checked={draft.notify_task_results}
                      onChange={(v) => setDraft({ ...draft, notify_task_results: v })}
                    />
                    <Toggle
                      label="Approval requests"
                      hint="Dangerous actions waiting for a decision"
                      checked={draft.notify_approval_requests}
                      onChange={(v) => setDraft({ ...draft, notify_approval_requests: v })}
                    />
                    <Toggle
                      label="PC online / offline"
                      hint="Relay reconnects and downtime summaries"
                      checked={draft.notify_connectivity}
                      onChange={(v) => setDraft({ ...draft, notify_connectivity: v })}
                    />
                    <Toggle
                      label="Monitoring events"
                      hint="Selected event-feed entries, filtered below"
                      checked={draft.notify_monitor_events}
                      onChange={(v) => setDraft({ ...draft, notify_monitor_events: v })}
                    />
                  </div>

                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <label className="block">
                      <span className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">
                        Minimum event severity
                      </span>
                      <select
                        value={draft.monitor_event_min_severity}
                        onChange={(e) =>
                          setDraft({ ...draft, monitor_event_min_severity: e.target.value as RemoteSeverity })
                        }
                        className="mt-1 w-full px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                      >
                        {(['info', 'notice', 'warning', 'critical'] as RemoteSeverity[]).map((severity) => (
                          <option key={severity} value={severity}>
                            {severity.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">
                        Event categories
                      </span>
                      <input
                        value={categoriesDraft}
                        onChange={(e) => setCategoriesDraft(e.target.value)}
                        placeholder="all — or cpu, disk, network"
                        className="mt-1 w-full px-2.5 py-2 rounded-sm bg-[#0D1118] border border-echo-border text-xs text-gray-200 font-mono focus:outline-none focus:border-echo-cyan/50"
                      />
                    </label>
                  </div>

                  <div className="mt-3 border-t border-echo-border/60 pt-1">
                    <Toggle
                      label="Remote screenshots"
                      hint={`Owner-only capture · JPEG fallback above ${draft.max_screenshot_mb} MB`}
                      checked={draft.screenshot_enabled}
                      onChange={(v) => setDraft({ ...draft, screenshot_enabled: v })}
                    />
                  </div>
                </Panel>

                <Panel
                  title="Notification Queue"
                  icon={<Send className="w-3.5 h-3.5" />}
                  aside={
                    <button
                      onClick={handleTestNotification}
                      disabled={busy || !status?.token_configured}
                      className="px-2.5 py-1 rounded-sm border border-echo-border text-echo-muted font-mono text-[10px] hover:text-white disabled:opacity-40"
                    >
                      SEND TEST
                    </button>
                  }
                >
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="font-mono text-[9px] tracking-wider text-echo-muted uppercase border-b border-echo-border">
                          <th className="py-1.5 pr-2 font-normal">Time</th>
                          <th className="py-1.5 pr-2 font-normal">Severity</th>
                          <th className="py-1.5 pr-2 font-normal">Message</th>
                          <th className="py-1.5 pr-2 font-normal">Status</th>
                          <th className="py-1.5 font-normal text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-echo-border/40">
                        {notifications.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="py-6 text-center text-xs text-echo-muted">
                              No queued notifications yet.
                            </td>
                          </tr>
                        ) : (
                          notifications.map((item) => (
                            <tr key={item.id} className="align-top">
                              <td className="py-2 pr-2 font-mono text-[10px] text-echo-muted whitespace-nowrap">
                                {formatClock(item.created_at)}
                              </td>
                              <td className="py-2 pr-2">
                                <span
                                  className={`font-mono text-[9px] px-1.5 py-0.5 rounded-sm border ${SEVERITY_STYLE[item.severity]}`}
                                >
                                  {item.severity.toUpperCase()}
                                </span>
                              </td>
                              <td className="py-2 pr-2 min-w-0">
                                <div className="text-[11px] text-gray-200">{item.title}</div>
                                <div className="text-[10px] text-echo-muted line-clamp-2">{item.message}</div>
                                {item.last_error && (
                                  <div className="mt-0.5 font-mono text-[9px] text-echo-danger">{item.last_error}</div>
                                )}
                              </td>
                              <td className="py-2 pr-2">
                                <span
                                  className={`font-mono text-[9px] px-1.5 py-0.5 rounded-sm border ${QUEUE_STYLE[item.status]}`}
                                >
                                  {item.status.toUpperCase()}
                                </span>
                                <div className="mt-0.5 font-mono text-[9px] text-echo-muted">
                                  ATT {item.attempts} · {timeAgo(item.created_at)}
                                </div>
                              </td>
                              <td className="py-2 text-right">
                                {['failed', 'expired', 'suppressed'].includes(item.status) ? (
                                  <button
                                    onClick={() => handleRetry(item)}
                                    className="inline-flex items-center gap-1 font-mono text-[9px] text-echo-cyan hover:text-white"
                                  >
                                    <RotateCcw className="w-3 h-3" /> RETRY
                                  </button>
                                ) : (
                                  <span className="font-mono text-[9px] text-echo-muted">—</span>
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>

              <div className="space-y-4">
                <Panel title="Queue State" icon={<Clock className="w-3.5 h-3.5" />}>
                  <div className="grid grid-cols-2 gap-2">
                    <Stat label="Queued" value={queue?.queued ?? 0} tone="text-echo-cyan" />
                    <Stat label="Sending" value={queue?.sending ?? 0} tone="text-echo-blue" />
                    <Stat label="Sent" value={queue?.sent ?? 0} tone="text-echo-success" />
                    <Stat label="Failed" value={queue?.failed ?? 0} tone="text-echo-danger" />
                    <Stat label="Expired" value={queue?.expired ?? 0} tone="text-echo-warning" />
                    <Stat label="Suppressed" value={queue?.suppressed ?? 0} tone="text-echo-muted" />
                  </div>
                  <div className="mt-3 space-y-1.5 font-mono text-[10px] text-echo-muted">
                    <div className="flex justify-between">
                      <span>TTL</span>
                      <span className="text-gray-300">{status?.settings.queue_ttl_hours ?? 12}h</span>
                    </div>
                    <div className="flex justify-between">
                      <span>BATCH</span>
                      <span className="text-gray-300">{status?.settings.queue_batch_size ?? 8} / FLUSH</span>
                    </div>
                    <div className="flex justify-between">
                      <span>SEND RATE</span>
                      <span className="text-gray-300">{status?.settings.send_rate_per_second ?? 1}/s</span>
                    </div>
                    <div className="flex justify-between">
                      <span>MAX</span>
                      <span className="text-gray-300">{status?.settings.queue_max_items ?? 200} ITEMS</span>
                    </div>
                  </div>
                  {failedNotifications.length > 0 && (
                    <div className="mt-3 rounded-sm border border-echo-danger/30 bg-echo-danger/5 px-2.5 py-2 text-[10px] text-echo-danger">
                      {failedNotifications.length} notification(s) need attention.
                    </div>
                  )}
                </Panel>

                <Panel title="Offline Behaviour" icon={<WifiOff className="w-3.5 h-3.5" />}>
                  <ul className="space-y-2 text-[11px] text-gray-300">
                    <li className="flex items-start gap-2">
                      <Wifi className="w-3.5 h-3.5 mt-0.5 text-echo-cyan flex-shrink-0" />
                      Notifications persist in SQLite while the relay is offline.
                    </li>
                    <li className="flex items-start gap-2">
                      <Clock className="w-3.5 h-3.5 mt-0.5 text-echo-cyan flex-shrink-0" />
                      Stale entries expire by severity; duplicates collapse on reconnect.
                    </li>
                    <li className="flex items-start gap-2">
                      <RotateCcw className="w-3.5 h-3.5 mt-0.5 text-echo-cyan flex-shrink-0" />
                      A downtime summary replaces the backlog when the link returns.
                    </li>
                  </ul>
                </Panel>
              </div>
            </div>
          )}

          {tab === 'audit' && (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              <div className="xl:col-span-2">
                <Panel
                  title="Remote Command Log"
                  icon={<ScrollText className="w-3.5 h-3.5" />}
                  aside={<span className="font-mono text-[10px] text-echo-muted">{commands.length} ENTRIES</span>}
                >
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="font-mono text-[9px] tracking-wider text-echo-muted uppercase border-b border-echo-border">
                          <th className="py-1.5 pr-2 font-normal">Time</th>
                          <th className="py-1.5 pr-2 font-normal">Actor</th>
                          <th className="py-1.5 pr-2 font-normal">Command</th>
                          <th className="py-1.5 pr-2 font-normal">Status</th>
                          <th className="py-1.5 font-normal">Detail</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-echo-border/40">
                        {commands.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="py-6 text-center text-xs text-echo-muted">
                              No remote commands recorded yet.
                            </td>
                          </tr>
                        ) : (
                          commands.map((item) => (
                            <tr key={item.id} className="align-top">
                              <td className="py-2 pr-2 font-mono text-[10px] text-echo-muted whitespace-nowrap">
                                {formatClock(item.created_at)}
                              </td>
                              <td className="py-2 pr-2 font-mono text-[10px] text-gray-300 whitespace-nowrap">
                                {item.username || item.telegram_id}
                              </td>
                              <td className="py-2 pr-2 font-mono text-[10px] text-echo-cyan whitespace-nowrap">
                                {item.command}
                              </td>
                              <td className="py-2 pr-2">
                                <span
                                  className={`font-mono text-[10px] ${
                                    COMMAND_STATUS_STYLE[item.status] || 'text-echo-muted'
                                  }`}
                                >
                                  {item.status.toUpperCase()}
                                </span>
                              </td>
                              <td className="py-2 min-w-0">
                                {item.error ? (
                                  <div className="font-mono text-[10px] text-echo-danger break-all">{item.error}</div>
                                ) : (
                                  <div className="text-[10px] text-echo-muted line-clamp-2">
                                    {item.response || '—'}
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>

              <div>
                <Panel
                  title="Remote Tasks"
                  icon={<Send className="w-3.5 h-3.5" />}
                  aside={<span className="font-mono text-[10px] text-echo-muted">{tasks.length} TOTAL</span>}
                >
                  {tasks.length === 0 ? (
                    <div className="py-6 text-center text-xs text-echo-muted">
                      No remote tasks yet. Try /task take a screenshot.
                    </div>
                  ) : (
                    <div className="divide-y divide-echo-border/50">
                      {tasks.map((task) => (
                        <div key={task.id} className="py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] text-gray-200 truncate">{task.goal}</span>
                            <span
                              className={`font-mono text-[9px] ${
                                task.status === 'completed'
                                  ? 'text-echo-success'
                                  : task.status === 'failed'
                                  ? 'text-echo-danger'
                                  : task.status === 'cancelled'
                                  ? 'text-echo-muted'
                                  : 'text-echo-cyan'
                              }`}
                            >
                              {task.status.toUpperCase()}
                            </span>
                          </div>
                          <div className="mt-0.5 font-mono text-[9px] text-echo-muted">
                            {task.command} · USER {task.telegram_id} · {timeAgo(task.updated_at)}
                          </div>
                          {(task.error || task.result) && (
                            <div
                              className={`mt-1 text-[10px] line-clamp-2 ${
                                task.error ? 'text-echo-danger' : 'text-gray-400'
                              }`}
                            >
                              {task.error || task.result}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
