import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Battery,
  BatteryCharging,
  Bell,
  CheckCircle2,
  Clock,
  Cpu,
  Gauge,
  HardDrive,
  MemoryStick,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  Settings2,
  ShieldAlert,
  Square,
  Thermometer,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import {
  MonitorAlert,
  MonitorAlertStatus,
  MonitorCategory,
  MonitorCounts,
  MonitorEvent,
  MonitorHistoryPoint,
  MonitorSeverity,
  MonitorSettings,
  MonitorSnapshot,
  MonitorStatus,
  MonitoringProfile,
} from '../types';
import { apiClient } from '../api/client';
import { echoWs } from '../api/ws';

interface SystemDashboardProps {
  isOpen: boolean;
  onClose: () => void;
  onBadgeChange?: (counts: MonitorCounts, running: boolean) => void;
}

type TabKey = 'overview' | 'alerts' | 'events' | 'settings';
type AlertFilter = 'all' | MonitorAlertStatus;

const SEVERITY_STYLE: Record<MonitorSeverity, { chip: string; dot: string; text: string; label: string }> = {
  info: {
    chip: 'border-echo-border bg-[#0F1420] text-echo-muted',
    dot: 'bg-echo-muted',
    text: 'text-echo-muted',
    label: 'INFO',
  },
  notice: {
    chip: 'border-echo-blue/40 bg-echo-blue/10 text-echo-blue',
    dot: 'bg-echo-blue',
    text: 'text-echo-blue',
    label: 'NOTICE',
  },
  warning: {
    chip: 'border-echo-warning/40 bg-echo-warning/10 text-echo-warning',
    dot: 'bg-echo-warning',
    text: 'text-echo-warning',
    label: 'WARNING',
  },
  critical: {
    chip: 'border-echo-danger/50 bg-echo-danger/10 text-echo-danger',
    dot: 'bg-echo-danger',
    text: 'text-echo-danger',
    label: 'CRITICAL',
  },
};

const CATEGORY_LABEL: Record<MonitorCategory, string> = {
  cpu: 'CPU',
  memory: 'MEMORY',
  disk: 'STORAGE',
  battery: 'BATTERY',
  network: 'NETWORK',
  temperature: 'THERMAL',
  application: 'APPLICATION',
  windows_event: 'WINDOWS EVENT',
  system: 'SYSTEM',
};

const EVENT_CATEGORIES: MonitorCategory[] = [
  'cpu',
  'memory',
  'disk',
  'battery',
  'network',
  'temperature',
  'application',
  'windows_event',
  'system',
];

const PROFILES: { key: MonitoringProfile; label: string; detail: string }[] = [
  { key: 'quiet', label: 'QUIET', detail: 'Relaxed thresholds, long windows' },
  { key: 'balanced', label: 'BALANCED', detail: 'Default detection cadence' },
  { key: 'strict', label: 'STRICT', detail: 'Fast detection, low thresholds' },
];

function timeAgo(iso?: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatClock(iso?: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.max(0, Math.round(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function trimNumber(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? '—' : value.toFixed(digits);
}

function lowerFreeDisk(disks: MonitorSnapshot['disks']) {
  if (!disks.length) return null;
  return [...disks].sort((a, b) => a.free_gb - b.free_gb)[0];
}

function Sparkline({
  data,
  color = '#00F0FF',
  height = 34,
}: {
  data: number[];
  color?: string;
  height?: number;
}) {
  const width = 160;
  const points = useMemo(() => {
    if (data.length === 0) return '';
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const span = Math.max(max - min, 1);
    return data
      .map((value, index) => {
        const x = data.length === 1 ? width : (index / (data.length - 1)) * width;
        const y = height - ((value - min) / span) * (height - 6) - 3;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }, [data, height]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      <line x1="0" y1={height - 0.5} x2={width} y2={height - 0.5} stroke="#1C2331" strokeWidth="1" />
      {points ? (
        <polyline points={points} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
      ) : (
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke="#1C2331" strokeDasharray="3 4" />
      )}
    </svg>
  );
}

function SeverityChip({ severity }: { severity: MonitorSeverity }) {
  const style = SEVERITY_STYLE[severity];
  return (
    <span className={`inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-sm border font-mono text-[10px] tracking-wider ${style.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

function MicroLabel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`font-mono text-[10px] uppercase tracking-[0.16em] text-echo-muted ${className}`}>
      {children}
    </span>
  );
}

function MetricTile({
  index,
  label,
  icon,
  value,
  unit,
  detail,
  accent = 'cyan',
  children,
}: {
  index: string;
  label: string;
  icon: React.ReactNode;
  value: string;
  unit?: string;
  detail?: React.ReactNode;
  accent?: 'cyan' | 'blue' | 'green' | 'amber' | 'red';
  children?: React.ReactNode;
}) {
  const accentClass = {
    cyan: 'text-echo-cyan',
    blue: 'text-echo-blue',
    green: 'text-echo-success',
    amber: 'text-echo-warning',
    red: 'text-echo-danger',
  }[accent];
  return (
    <div className="relative border border-echo-border bg-[#0B0E14] rounded-md p-3 overflow-hidden">
      <div className="absolute top-0 left-0 h-[1px] w-10 bg-echo-cyan/40" />
      <div className="flex items-center justify-between">
        <MicroLabel>
          {index} / {label}
        </MicroLabel>
        <span className={accentClass}>{icon}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className={`font-mono text-2xl leading-none tracking-tight ${accentClass}`}>{value}</span>
        {unit && <span className="font-mono text-[11px] text-echo-muted">{unit}</span>}
      </div>
      {detail && <div className="mt-1 text-[11px] text-echo-muted truncate">{detail}</div>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}

function ProgressBar({ percent, dangerBelow }: { percent: number; dangerBelow?: boolean }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="h-1 w-full bg-[#161B22] rounded-sm overflow-hidden">
      <div
        className={`h-full ${dangerBelow ? 'bg-echo-danger' : 'bg-echo-cyan'}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  detail,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  detail?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded-sm border text-left transition-colors ${
        checked
          ? 'border-echo-cyan/40 bg-echo-cyan/5'
          : 'border-echo-border bg-[#0B0E14] hover:border-echo-muted/40'
      }`}
    >
      <span>
        <span className={`block text-xs ${checked ? 'text-white' : 'text-echo-muted'}`}>{label}</span>
        {detail && <span className="block text-[10px] text-echo-muted font-mono mt-0.5">{detail}</span>}
      </span>
      <span
        className={`w-8 h-4 rounded-full border relative flex-shrink-0 transition-colors ${
          checked ? 'bg-echo-cyan/20 border-echo-cyan/60' : 'bg-[#161B22] border-echo-border'
        }`}
      >
        <span
          className={`absolute top-[2px] w-2.5 h-2.5 rounded-full transition-all ${
            checked ? 'left-[18px] bg-echo-cyan' : 'left-[2px] bg-echo-muted'
          }`}
        />
      </span>
    </button>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  step?: number | 'any';
  suffix?: string;
}) {
  return (
    <label className="block">
      <MicroLabel className="block mb-1">{label}</MicroLabel>
      <div className="flex items-center border border-echo-border bg-[#0B0E14] rounded-sm focus-within:border-echo-cyan/50">
        <input
          type="number"
          value={Number.isFinite(value) ? value : 0}
          min={min}
          max={max}
          step={step}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full bg-transparent px-2 py-1.5 text-xs font-mono text-echo-text outline-none"
        />
        {suffix && <span className="pr-2 font-mono text-[10px] text-echo-muted">{suffix}</span>}
      </div>
    </label>
  );
}

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-echo-border bg-[#0B0E14] rounded-md">
      <header className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
        <MicroLabel>{title}</MicroLabel>
        <span className="h-[1px] flex-1 ml-3 bg-echo-border/70" />
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

export const SystemDashboard: React.FC<SystemDashboardProps> = ({ isOpen, onClose, onBadgeChange }) => {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [snapshot, setSnapshot] = useState<MonitorSnapshot | null>(null);
  const [history, setHistory] = useState<MonitorHistoryPoint[]>([]);
  const [alerts, setAlerts] = useState<MonitorAlert[]>([]);
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [tab, setTab] = useState<TabKey>('overview');
  const [alertFilter, setAlertFilter] = useState<AlertFilter>('all');
  const [eventCategory, setEventCategory] = useState<'all' | MonitorCategory>('all');
  const [eventSeverity, setEventSeverity] = useState<'all' | MonitorSeverity>('all');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<MonitorSettings | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [listDrafts, setListDrafts] = useState({
    diskPaths: '',
    networkTargets: '',
    monitoredApps: '',
  });
  const noticeTimer = useRef<any>(null);

  const applyStatus = useCallback(
    (next: MonitorStatus, updateDraft = false) => {
      setStatus(next);
      setSnapshot(next.snapshot);
      setHistory(next.history || []);
      setSettingsDraft((previous) => (updateDraft || previous === null ? next.settings : previous));
      if (updateDraft || !settingsDraft) {
        setListDrafts({
          diskPaths: next.settings.disk_paths.join(', '),
          networkTargets: next.settings.network_targets.join(', '),
          monitoredApps: next.settings.monitored_applications.join(', '),
        });
      }
      onBadgeChange?.(next.counts, next.running);
    },
    [onBadgeChange, settingsDraft]
  );

  const refreshStatus = useCallback(async () => {
    try {
      const next = await apiClient.getMonitoringStatus();
      applyStatus(next);
    } catch {
      // Keep the last known state; the daemon may be restarting.
    }
  }, [applyStatus]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextStatus, alertData, eventData] = await Promise.all([
        apiClient.getMonitoringStatus(),
        apiClient.listMonitorAlerts(undefined, 250),
        apiClient.listMonitorEvents(150),
      ]);
      setStatus(nextStatus);
      setSnapshot(nextStatus.snapshot);
      setHistory(nextStatus.history || []);
      setAlerts(alertData.alerts);
      setEvents(eventData.events);
      setSettingsDraft(nextStatus.settings);
      setListDrafts({
        diskPaths: nextStatus.settings.disk_paths.join(', '),
        networkTargets: nextStatus.settings.network_targets.join(', '),
        monitoredApps: nextStatus.settings.monitored_applications.join(', '),
      });
      onBadgeChange?.(nextStatus.counts, nextStatus.running);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setLoading(false);
    }
  }, [onBadgeChange]);

  useEffect(() => {
    if (!isOpen) return;
    loadAll();
    const interval = setInterval(refreshStatus, 10000);
    return () => clearInterval(interval);
  }, [isOpen, loadAll, refreshStatus]);

  useEffect(() => {
    if (!isOpen) return;
    const unsubscribe = echoWs.subscribe((data) => {
      if (data.type === 'monitor_snapshot') {
        const next = data.snapshot as MonitorSnapshot;
        if (!next) return;
        setSnapshot(next);
        setHistory((previous) =>
          [
            ...previous,
            {
              t: next.timestamp,
              cpu: next.cpu?.percent ?? 0,
              memory: next.memory?.percent ?? 0,
              disk_free_gb: lowerFreeDisk(next.disks || [])?.free_gb ?? null,
              down_kbps: next.network?.down_kbps ?? 0,
              up_kbps: next.network?.up_kbps ?? 0,
            },
          ].slice(-240)
        );
        setStatus((previous) =>
          previous
            ? { ...previous, snapshot: next, counts: next.alert_counts || previous.counts, running: true }
            : previous
        );
        onBadgeChange?.(next.alert_counts, true);
      } else if (data.type === 'monitor_status') {
        const next = data as MonitorStatus;
        setStatus(next);
        setSnapshot(next.snapshot);
        setHistory(next.history || []);
        setSettingsDraft((previous) => previous ?? next.settings);
        onBadgeChange?.(next.counts, next.running);
      } else if (data.type === 'monitor_alert' || data.type === 'monitor_recovered') {
        const alert = data.alert as MonitorAlert | undefined;
        if (alert) {
          setAlerts((previous) => {
            const rest = previous.filter((item) => item.id !== alert.id);
            return [alert, ...rest].sort((a, b) => b.last_seen_at.localeCompare(a.last_seen_at));
          });
        }
        refreshStatus();
      } else if (data.type === 'monitor_event') {
        const event = data.event as MonitorEvent | undefined;
        if (event) {
          setEvents((previous) => [event, ...previous].slice(0, 250));
        }
      }
    });
    return unsubscribe;
  }, [isOpen, onBadgeChange, refreshStatus]);

  useEffect(() => {
    return () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    };
  }, []);

  const flash = useCallback((message: string) => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    setNotice(message);
    noticeTimer.current = setTimeout(() => setNotice(null), 3500);
  }, []);

  const handleToggleMonitoring = async () => {
    setBusy(true);
    try {
      const response = status?.running
        ? await apiClient.stopMonitoring()
        : await apiClient.startMonitoring();
      applyStatus(response.status, true);
      flash(response.status.running ? 'Monitoring engine started.' : 'Monitoring engine stopped.');
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  };

  const handleProfile = async (profile: MonitoringProfile) => {
    if (!status || status.profile === profile) return;
    setBusy(true);
    try {
      const response = await apiClient.updateMonitoringSettings({ profile });
      applyStatus(response.status, true);
      flash(`Profile changed to ${profile}.`);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  };

  const handleAcknowledge = async (alertId: string) => {
    try {
      const response = await apiClient.acknowledgeMonitorAlert(alertId);
      setAlerts((previous) =>
        previous.map((item) => (item.id === response.alert.id ? response.alert : item))
      );
      await refreshStatus();
    } catch (exc) {
      setError(String(exc));
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      const response = await apiClient.resolveMonitorAlert(alertId);
      setAlerts((previous) =>
        previous.map((item) => (item.id === response.alert.id ? response.alert : item))
      );
      await refreshStatus();
    } catch (exc) {
      setError(String(exc));
    }
  };

  const updateSetting = <K extends keyof MonitorSettings>(key: K, value: MonitorSettings[K]) => {
    setSettingsDraft((previous) => (previous ? { ...previous, [key]: value } : previous));
  };

  const handleSaveSettings = async () => {
    if (!settingsDraft) return;
    setBusy(true);
    setSettingsMessage(null);
    try {
      const payload: Partial<MonitorSettings> = {
        ...settingsDraft,
        disk_paths: listDrafts.diskPaths.split(',').map((item) => item.trim()).filter(Boolean),
        network_targets: listDrafts.networkTargets.split(',').map((item) => item.trim()).filter(Boolean),
        monitored_applications: listDrafts.monitoredApps.split(',').map((item) => item.trim()).filter(Boolean),
      };
      const response = await apiClient.updateMonitoringSettings(payload);
      setSettingsDraft(response.settings);
      setListDrafts({
        diskPaths: response.settings.disk_paths.join(', '),
        networkTargets: response.settings.network_targets.join(', '),
        monitoredApps: response.settings.monitored_applications.join(', '),
      });
      applyStatus(response.status);
      setSettingsMessage('Configuration saved.');
    } catch (exc) {
      setSettingsMessage(String(exc));
    } finally {
      setBusy(false);
    }
  };

  const activeAlerts = useMemo(
    () => alerts.filter((alert) => alert.status === 'active'),
    [alerts]
  );

  const filteredAlerts = useMemo(() => {
    if (alertFilter === 'all') return alerts;
    return alerts.filter((alert) => alert.status === alertFilter);
  }, [alerts, alertFilter]);

  const filteredEvents = useMemo(
    () =>
      events.filter(
        (event) =>
          (eventCategory === 'all' || event.category === eventCategory) &&
          (eventSeverity === 'all' || event.severity === eventSeverity)
      ),
    [events, eventCategory, eventSeverity]
  );

  const primaryDisk = snapshot ? lowerFreeDisk(snapshot.disks || []) : null;
  const cpuPercent = snapshot?.cpu?.percent;
  const memoryPercent = snapshot?.memory?.percent;
  const battery = snapshot?.battery;
  const network = snapshot?.network;
  const temperature = snapshot?.temperature;
  const counts = status?.counts;

  if (!isOpen) return null;

  const cpuHistory = history.map((point) => point.cpu);
  const memoryHistory = history.map((point) => point.memory);
  const downHistory = history.map((point) => point.down_kbps);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3">
      <div className="w-full max-w-[1280px] h-[91vh] flex flex-col rounded-lg border border-echo-border bg-[#07090E] shadow-2xl overflow-hidden">
        {/* Instrument header */}
        <header className="border-b border-echo-border bg-[#0B0E14]">
          <div className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-sm border border-echo-cyan/40 bg-echo-cyan/5 flex items-center justify-center text-echo-cyan">
                <Gauge className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="font-mono text-sm tracking-[0.18em] text-white">SYSTEM OBSERVATORY</h2>
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded-sm border tracking-wider ${
                      status?.running
                        ? 'border-echo-success/40 bg-echo-success/10 text-echo-success'
                        : 'border-echo-border bg-[#121721] text-echo-muted'
                    }`}
                  >
                    {status?.running ? 'LIVE' : 'IDLE'}
                  </span>
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-sm border border-echo-cyan/30 bg-echo-cyan/5 text-echo-cyan uppercase">
                    {status?.profile || 'balanced'}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-3 font-mono text-[10px] text-echo-muted truncate">
                  <span>POLL {status?.settings.poll_interval_seconds ?? '—'}s</span>
                  <span>LAST {timeAgo(status?.last_poll_at)}</span>
                  <span>UPTIME {formatDuration(snapshot?.uptime_seconds)}</span>
                  <span className="hidden sm:inline">{snapshot?.platform || 'detecting platform'}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleToggleMonitoring}
                disabled={busy}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border font-mono text-[11px] tracking-wide transition-colors disabled:opacity-50 ${
                  status?.running
                    ? 'border-echo-danger/40 bg-echo-danger/10 text-echo-danger hover:bg-echo-danger/20'
                    : 'border-echo-success/40 bg-echo-success/10 text-echo-success hover:bg-echo-success/20'
                }`}
              >
                {status?.running ? <Square className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                {status?.running ? 'STOP' : 'START'}
              </button>
              <button
                onClick={loadAll}
                className="p-1.5 rounded-sm border border-echo-border text-echo-muted hover:text-white hover:border-echo-muted/50 transition-colors"
                title="Refresh dashboard"
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

          {/* Availability strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 border-t border-echo-border text-[10px] font-mono">
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">EVENT LOG</span>
              <span
                className={
                  status?.availability.windows_events.available
                    ? 'text-echo-success'
                    : 'text-echo-warning'
                }
              >
                {status?.availability.windows_events.available ? 'CONNECTED' : 'UNAVAILABLE'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">THERMAL SENSOR</span>
              <span className={temperature?.available ? 'text-echo-success' : 'text-echo-muted'}>
                {temperature?.available ? temperature.source || 'ACTIVE' : 'NO SENSOR'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 border-r border-echo-border">
              <span className="text-echo-muted">BATTERY</span>
              <span className={battery?.present ? 'text-echo-success' : 'text-echo-muted'}>
                {battery?.present ? `${trimNumber(battery.percent, 0)}%` : 'NOT PRESENT'}
              </span>
            </div>
            <div className="flex items-center justify-between px-3 py-1.5">
              <span className="text-echo-muted">ACTIVE ALERTS</span>
              <span className={counts && counts.total > 0 ? 'text-echo-warning' : 'text-echo-success'}>
                {counts?.total ?? 0}
              </span>
            </div>
          </div>
        </header>

        {/* Tabs */}
        <nav className="flex items-center gap-1 px-4 border-b border-echo-border bg-[#090C12]">
          {(
            [
              ['overview', 'OVERVIEW'],
              ['alerts', `ALERTS${counts?.total ? ` ${counts.total}` : ''}`],
              ['events', 'EVENT FEED'],
              ['settings', 'CONFIG'],
            ] as [TabKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-3 py-2 font-mono text-[11px] tracking-wider border-b-2 transition-colors ${
                tab === key
                  ? 'border-echo-cyan text-echo-cyan'
                  : 'border-transparent text-echo-muted hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2 py-1">
            {error && (
              <span className="font-mono text-[10px] text-echo-danger truncate max-w-[360px]">{error}</span>
            )}
            {notice && <span className="font-mono text-[10px] text-echo-success">{notice}</span>}
          </div>
        </nav>

        <div className="flex-1 overflow-y-auto p-4">
          {tab === 'overview' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                <MetricTile
                  index="01"
                  label="CPU"
                  icon={<Cpu className="w-4 h-4" />}
                  value={cpuPercent === undefined ? '—' : trimNumber(cpuPercent)}
                  unit="%"
                  detail={`${snapshot?.cpu?.cores_logical ?? '—'} threads · ${snapshot?.cpu?.frequency_mhz ?? '—'} MHz`}
                  accent={(cpuPercent ?? 0) >= (settingsDraft?.cpu_warning_percent ?? 85) ? 'amber' : 'cyan'}
                >
                  <Sparkline data={cpuHistory} />
                </MetricTile>

                <MetricTile
                  index="02"
                  label="MEMORY"
                  icon={<MemoryStick className="w-4 h-4" />}
                  value={memoryPercent === undefined ? '—' : trimNumber(memoryPercent)}
                  unit="%"
                  detail={`${trimNumber(snapshot?.memory?.used_gb)} / ${trimNumber(snapshot?.memory?.total_gb)} GB used`}
                  accent={(memoryPercent ?? 0) >= (settingsDraft?.memory_warning_percent ?? 88) ? 'amber' : 'blue'}
                >
                  <Sparkline data={memoryHistory} color="#0070F3" />
                </MetricTile>

                <MetricTile
                  index="03"
                  label="STORAGE"
                  icon={<HardDrive className="w-4 h-4" />}
                  value={primaryDisk ? trimNumber(primaryDisk.free_gb) : '—'}
                  unit="GB FREE"
                  detail={primaryDisk ? `${primaryDisk.path} · ${trimNumber(primaryDisk.percent)}% used` : 'No volumes detected'}
                  accent={
                    primaryDisk && primaryDisk.free_gb < (settingsDraft?.disk_free_critical_gb ?? 3)
                      ? 'red'
                      : primaryDisk && primaryDisk.free_gb < (settingsDraft?.disk_free_warning_gb ?? 10)
                      ? 'amber'
                      : 'green'
                  }
                >
                  {primaryDisk && (
                    <ProgressBar
                      percent={primaryDisk.percent}
                      dangerBelow={primaryDisk.free_gb < (settingsDraft?.disk_free_warning_gb ?? 10)}
                    />
                  )}
                </MetricTile>

                <MetricTile
                  index="04"
                  label="NETWORK"
                  icon={network?.online ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
                  value={network?.online === null || network?.online === undefined ? '—' : network.online ? 'ONLINE' : 'OFFLINE'}
                  detail={
                    network?.online
                      ? `${trimNumber(network.latency_ms)} ms · ↓${trimNumber(network.down_kbps)} ↑${trimNumber(network.up_kbps)} kb/s`
                      : network?.errors?.[0] || 'Connectivity probe pending'
                  }
                  accent={network?.online === false ? 'red' : 'cyan'}
                >
                  <Sparkline data={downHistory} color="#00E676" />
                </MetricTile>

                <MetricTile
                  index="05"
                  label="BATTERY"
                  icon={battery?.plugged ? <BatteryCharging className="w-4 h-4" /> : <Battery className="w-4 h-4" />}
                  value={battery?.present ? trimNumber(battery.percent, 0) : '—'}
                  unit={battery?.present ? '%' : undefined}
                  detail={
                    battery?.present
                      ? battery.plugged
                        ? 'AC power · charging'
                        : battery.seconds_left
                        ? `${formatDuration(battery.seconds_left)} remaining`
                        : 'Discharging'
                      : 'No battery detected'
                  }
                  accent={
                    battery?.present && !battery.plugged && (battery.percent ?? 100) <= (settingsDraft?.battery_warning_percent ?? 20)
                      ? 'red'
                      : 'green'
                  }
                />
                <MetricTile
                  index="06"
                  label="THERMAL"
                  icon={<Thermometer className="w-4 h-4" />}
                  value={temperature?.available ? trimNumber(temperature.celsius) : '—'}
                  unit={temperature?.available ? '°C' : 'NO SENSOR'}
                  detail={
                    temperature?.available
                      ? temperature.source || 'Hardware bridge'
                      : temperature?.reason || 'No temperature data exposed'
                  }
                  accent={temperature?.available ? 'amber' : 'cyan'}
                />
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                {/* Disks */}
                <section className="border border-echo-border bg-[#0B0E14] rounded-md">
                  <header className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
                    <MicroLabel>VOLUMES</MicroLabel>
                    <span className="font-mono text-[10px] text-echo-muted">{snapshot?.disks.length ?? 0} DEVICES</span>
                  </header>
                  <div className="divide-y divide-echo-border/70">
                    {(snapshot?.disks || []).map((disk) => {
                      const warning = disk.free_gb < (settingsDraft?.disk_free_warning_gb ?? 10);
                      const critical = disk.free_gb < (settingsDraft?.disk_free_critical_gb ?? 3);
                      return (
                        <div key={disk.path} className="px-3 py-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono text-white">{disk.path}</span>
                            <span className={`font-mono text-[11px] ${critical ? 'text-echo-danger' : warning ? 'text-echo-warning' : 'text-echo-success'}`}>
                              {trimNumber(disk.free_gb)} GB free
                            </span>
                          </div>
                          <div className="mt-1.5">
                            <ProgressBar percent={disk.percent} dangerBelow={warning} />
                          </div>
                          <div className="mt-1 flex justify-between font-mono text-[10px] text-echo-muted">
                            <span>{trimNumber(disk.used_gb)} / {trimNumber(disk.total_gb)} GB</span>
                            <span>{trimNumber(disk.percent)}%</span>
                          </div>
                        </div>
                      );
                    })}
                    {!snapshot?.disks.length && (
                      <div className="px-3 py-6 text-center text-xs text-echo-muted">No storage volumes detected.</div>
                    )}
                  </div>
                </section>

                {/* System */}
                <section className="border border-echo-border bg-[#0B0E14] rounded-md">
                  <header className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
                    <MicroLabel>HOST STATE</MicroLabel>
                    <Server className="w-3.5 h-3.5 text-echo-muted" />
                  </header>
                  <div className="p-3 space-y-2 text-xs">
                    <div className="flex justify-between"><span className="text-echo-muted">Uptime</span><span className="font-mono text-white">{formatDuration(snapshot?.uptime_seconds)}</span></div>
                    <div className="flex justify-between"><span className="text-echo-muted">Boot time</span><span className="font-mono text-echo-text">{snapshot?.boot_time ? new Date(snapshot.boot_time).toLocaleString() : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-echo-muted">Processes</span><span className="font-mono text-white">{snapshot?.process_count ?? '—'}</span></div>
                    <div className="flex justify-between"><span className="text-echo-muted">Platform</span><span className="font-mono text-echo-text">{snapshot?.platform || '—'}</span></div>
                    <div className="flex justify-between"><span className="text-echo-muted">Swap</span><span className="font-mono text-white">{trimNumber(snapshot?.memory?.swap_percent)}%</span></div>
                    <div className="pt-2 border-t border-echo-border/70">
                      <MicroLabel>TOP MEMORY</MicroLabel>
                      <div className="mt-1.5 space-y-1">
                        {(snapshot?.top_processes || []).map((process) => (
                          <div key={`${process.pid}-${process.name}`} className="flex items-center justify-between text-[11px]">
                            <span className="truncate text-echo-text">{process.name}</span>
                            <span className="font-mono text-echo-muted ml-2">{trimNumber(process.memory_mb)} MB</span>
                          </div>
                        ))}
                        {!snapshot?.top_processes?.length && <span className="text-[11px] text-echo-muted">No process data.</span>}
                      </div>
                    </div>
                  </div>
                </section>

                {/* Signals */}
                <section className="border border-echo-border bg-[#0B0E14] rounded-md">
                  <header className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
                    <MicroLabel>SIGNALS</MicroLabel>
                    <Activity className="w-3.5 h-3.5 text-echo-muted" />
                  </header>
                  <div className="p-3 space-y-2 text-[11px]">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-echo-muted">Windows Event Log</span>
                      <span className={`font-mono ${status?.availability.windows_events.available ? 'text-echo-success' : 'text-echo-warning'}`}>
                        {status?.availability.windows_events.available ? 'MONITORING' : 'UNAVAILABLE'}
                      </span>
                    </div>
                    {status?.availability.windows_events.error && (
                      <p className="text-echo-danger font-mono leading-snug">{status.availability.windows_events.error}</p>
                    )}
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-echo-muted">Temperature</span>
                      <span className={`font-mono text-right ${temperature?.available ? 'text-echo-success' : 'text-echo-muted'}`}>
                        {temperature?.available ? `${trimNumber(temperature.celsius)}°C` : 'NO SENSOR'}
                      </span>
                    </div>
                    {!temperature?.available && temperature?.reason && (
                      <p className="text-echo-muted font-mono leading-snug">{temperature.reason}</p>
                    )}
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-echo-muted">Hung windows</span>
                      <span className={`font-mono ${snapshot?.hung_windows?.length ? 'text-echo-warning' : 'text-echo-success'}`}>
                        {snapshot?.hung_windows?.length ?? 0}
                      </span>
                    </div>
                    <div className="pt-2 border-t border-echo-border/70">
                      <div className="flex items-center justify-between">
                        <MicroLabel>MONITORED APPS</MicroLabel>
                        <span className="font-mono text-[10px] text-echo-muted">{snapshot?.monitored_applications?.length ?? 0}</span>
                      </div>
                      <div className="mt-1.5 space-y-1">
                        {(snapshot?.monitored_applications || []).map((app) => (
                          <div key={app.name} className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1.5 min-w-0">
                              <span className={`w-1.5 h-1.5 rounded-full ${app.running ? 'bg-echo-success' : 'bg-echo-danger'}`} />
                              <span className="truncate text-echo-text">{app.name}</span>
                            </span>
                            <span className="font-mono text-echo-muted">{app.running ? `${trimNumber(app.memory_mb)} MB` : 'STOPPED'}</span>
                          </div>
                        ))}
                        {!snapshot?.monitored_applications?.length && (
                          <span className="text-echo-muted">None configured.</span>
                        )}
                      </div>
                    </div>
                  </div>
                </section>
              </div>

              {/* Active alerts */}
              <section className="border border-echo-border bg-[#0B0E14] rounded-md">
                <header className="px-3 py-2 border-b border-echo-border flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bell className="w-3.5 h-3.5 text-echo-cyan" />
                    <MicroLabel>ACTIVE ALERTS</MicroLabel>
                  </div>
                  <span className={`font-mono text-[10px] ${activeAlerts.length ? 'text-echo-warning' : 'text-echo-success'}`}>
                    {activeAlerts.length} OPEN
                  </span>
                </header>
                <div className="divide-y divide-echo-border/70">
                  {activeAlerts.slice(0, 6).map((alert) => (
                    <div key={alert.id} className="px-3 py-2 flex items-start gap-3">
                      <SeverityChip severity={alert.severity} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-white truncate">{alert.title}</span>
                          <span className="font-mono text-[10px] text-echo-muted">{CATEGORY_LABEL[alert.category] || alert.category}</span>
                        </div>
                        <p className="text-[11px] text-echo-muted truncate">{alert.message}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="font-mono text-[10px] text-echo-muted">{timeAgo(alert.first_seen_at)}</div>
                        <div className="flex items-center gap-1 mt-1">
                          {!alert.acknowledged_at && (
                            <button onClick={() => handleAcknowledge(alert.id)} className="px-1.5 py-0.5 rounded-sm border border-echo-border text-[10px] font-mono text-echo-muted hover:text-white">
                              ACK
                            </button>
                          )}
                          <button onClick={() => handleResolve(alert.id)} className="px-1.5 py-0.5 rounded-sm border border-echo-cyan/30 text-[10px] font-mono text-echo-cyan hover:bg-echo-cyan/10">
                            RESOLVE
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                  {!activeAlerts.length && (
                    <div className="px-3 py-6 flex items-center justify-center gap-2 text-xs text-echo-muted">
                      <CheckCircle2 className="w-4 h-4 text-echo-success" />
                      No active alerts. Monitored conditions are within thresholds.
                    </div>
                  )}
                </div>
              </section>
            </div>
          )}

          {tab === 'alerts' && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {(['all', 'active', 'recovered', 'resolved'] as AlertFilter[]).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setAlertFilter(filter)}
                    className={`px-2.5 py-1 rounded-sm border font-mono text-[10px] uppercase tracking-wide ${
                      alertFilter === filter
                        ? 'border-echo-cyan/50 bg-echo-cyan/10 text-echo-cyan'
                        : 'border-echo-border text-echo-muted hover:text-white'
                    }`}
                  >
                    {filter} ({filter === 'all' ? alerts.length : alerts.filter((alert) => alert.status === filter).length})
                  </button>
                ))}
              </div>

              <div className="border border-echo-border bg-[#0B0E14] rounded-md overflow-hidden">
                <div className="grid grid-cols-[92px_110px_1fr_90px_120px_150px] gap-2 px-3 py-2 border-b border-echo-border font-mono text-[10px] text-echo-muted uppercase tracking-wider">
                  <span>Severity</span>
                  <span>Category</span>
                  <span>Alert</span>
                  <span>Count</span>
                  <span>First seen</span>
                  <span>Actions</span>
                </div>
                <div className="divide-y divide-echo-border/70">
                  {filteredAlerts.map((alert) => (
                    <div key={alert.id} className="grid grid-cols-[92px_110px_1fr_90px_120px_150px] gap-2 px-3 py-2 items-center">
                      <SeverityChip severity={alert.severity} />
                      <span className="font-mono text-[10px] text-echo-muted truncate">{CATEGORY_LABEL[alert.category] || alert.category}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-white truncate">{alert.title}</span>
                          {alert.escalation_level > 0 && (
                            <span className="font-mono text-[9px] px-1 rounded-sm border border-echo-danger/40 text-echo-danger">ESC {alert.escalation_level}</span>
                          )}
                          <span className={`font-mono text-[9px] uppercase ${alert.status === 'active' ? 'text-echo-warning' : alert.status === 'recovered' ? 'text-echo-success' : 'text-echo-muted'}`}>
                            {alert.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-echo-muted truncate">{alert.message}</p>
                      </div>
                      <span className="font-mono text-[11px] text-echo-text">{alert.occurrences}×</span>
                      <span className="font-mono text-[10px] text-echo-muted">{timeAgo(alert.first_seen_at)}</span>
                      <div className="flex items-center gap-1">
                        {alert.status === 'active' && !alert.acknowledged_at && (
                          <button onClick={() => handleAcknowledge(alert.id)} className="px-1.5 py-0.5 rounded-sm border border-echo-border font-mono text-[10px] text-echo-muted hover:text-white">
                            ACK
                          </button>
                        )}
                        {alert.status !== 'resolved' && (
                          <button onClick={() => handleResolve(alert.id)} className="px-1.5 py-0.5 rounded-sm border border-echo-cyan/30 font-mono text-[10px] text-echo-cyan hover:bg-echo-cyan/10">
                            RESOLVE
                          </button>
                        )}
                        {alert.acknowledged_at && alert.status === 'active' && (
                          <span className="font-mono text-[9px] text-echo-success">ACKED</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {!filteredAlerts.length && (
                    <div className="px-3 py-10 text-center text-xs text-echo-muted">No alerts match this filter.</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === 'events' && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={eventCategory}
                  onChange={(event) => setEventCategory(event.target.value as 'all' | MonitorCategory)}
                  className="bg-[#0B0E14] border border-echo-border rounded-sm px-2 py-1 font-mono text-[10px] text-echo-text outline-none focus:border-echo-cyan/50"
                >
                  <option value="all">ALL CATEGORIES</option>
                  {EVENT_CATEGORIES.map((category) => (
                    <option key={category} value={category}>{CATEGORY_LABEL[category]}</option>
                  ))}
                </select>
                <select
                  value={eventSeverity}
                  onChange={(event) => setEventSeverity(event.target.value as 'all' | MonitorSeverity)}
                  className="bg-[#0B0E14] border border-echo-border rounded-sm px-2 py-1 font-mono text-[10px] text-echo-text outline-none focus:border-echo-cyan/50"
                >
                  <option value="all">ALL SEVERITIES</option>
                  <option value="info">INFO</option>
                  <option value="notice">NOTICE</option>
                  <option value="warning">WARNING</option>
                  <option value="critical">CRITICAL</option>
                </select>
                <span className="ml-auto font-mono text-[10px] text-echo-muted">{filteredEvents.length} EVENTS</span>
              </div>

              <div className="border border-echo-border bg-[#0B0E14] rounded-md divide-y divide-echo-border/70">
                {filteredEvents.map((event) => (
                  <div key={event.id} className="px-3 py-2 flex items-start gap-3">
                    <span className="font-mono text-[10px] text-echo-muted pt-0.5 w-16 flex-shrink-0">{formatClock(event.occurred_at)}</span>
                    <SeverityChip severity={event.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-white truncate">{event.title}</span>
                        <span className="font-mono text-[9px] px-1 rounded-sm border border-echo-border text-echo-muted uppercase">{CATEGORY_LABEL[event.category] || event.category}</span>
                        <span className="font-mono text-[9px] text-echo-muted">{event.kind}</span>
                      </div>
                      <p className="text-[11px] text-echo-muted leading-snug break-words">{event.message}</p>
                    </div>
                  </div>
                ))}
                {!filteredEvents.length && (
                  <div className="px-3 py-10 text-center text-xs text-echo-muted">
                    No events recorded for this filter. Windows Event Log, app crashes, connectivity changes and alert lifecycle entries appear here.
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'settings' && settingsDraft && (
            <div className="space-y-4 pb-16">
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <SettingsSection title="PROFILE">
                  <div className="space-y-2">
                    {PROFILES.map((profile) => (
                      <button
                        key={profile.key}
                        type="button"
                        onClick={() => handleProfile(profile.key)}
                        className={`w-full text-left px-3 py-2 rounded-sm border transition-colors ${
                          status?.profile === profile.key
                            ? 'border-echo-cyan/50 bg-echo-cyan/5'
                            : 'border-echo-border hover:border-echo-muted/40'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`font-mono text-[11px] tracking-wider ${status?.profile === profile.key ? 'text-echo-cyan' : 'text-echo-text'}`}>{profile.label}</span>
                          {status?.profile === profile.key && <span className="font-mono text-[9px] text-echo-cyan">ACTIVE</span>}
                        </div>
                        <p className="text-[10px] text-echo-muted mt-0.5">{profile.detail}</p>
                      </button>
                    ))}
                    <Toggle
                      checked={settingsDraft.enabled}
                      onChange={(next) => updateSetting('enabled', next)}
                      label="Monitoring enabled"
                      detail={settingsDraft.enabled ? 'Starts with the daemon' : 'Idle until started manually'}
                    />
                  </div>
                </SettingsSection>

                <SettingsSection title="ENGINE CADENCE">
                  <div className="grid grid-cols-2 gap-2">
                    <NumberField label="Poll interval" value={settingsDraft.poll_interval_seconds} min={2} max={120} suffix="s" onChange={(value) => updateSetting('poll_interval_seconds', value)} />
                    <NumberField label="Retention" value={settingsDraft.retention_days} min={1} max={365} suffix="d" onChange={(value) => updateSetting('retention_days', value)} />
                    <NumberField label="Alert cooldown" value={settingsDraft.alert_cooldown_seconds} min={60} max={86400} suffix="s" onChange={(value) => updateSetting('alert_cooldown_seconds', value)} />
                    <NumberField label="Escalation after" value={settingsDraft.escalation_seconds} min={60} max={86400} suffix="s" onChange={(value) => updateSetting('escalation_seconds', value)} />
                    <NumberField label="Recovery margin" value={settingsDraft.recovery_margin_percent} min={0} max={30} suffix="%" onChange={(value) => updateSetting('recovery_margin_percent', value)} />
                    <NumberField label="Disk margin" value={settingsDraft.recovery_margin_gb} min={0} max={100} suffix="GB" onChange={(value) => updateSetting('recovery_margin_gb', value)} />
                  </div>
                </SettingsSection>

                <SettingsSection title="FEATURE SWITCHES">
                  <div className="grid grid-cols-1 gap-1.5">
                    {(
                      [
                        ['monitor_cpu', 'CPU'],
                        ['monitor_memory', 'Memory'],
                        ['monitor_disk', 'Storage'],
                        ['monitor_battery', 'Battery'],
                        ['monitor_network', 'Network'],
                        ['monitor_temperature', 'Temperature'],
                        ['monitor_processes', 'Processes'],
                        ['monitor_hung_windows', 'Unresponsive windows'],
                        ['monitor_windows_events', 'Windows Event Log'],
                      ] as [keyof MonitorSettings, string][]
                    ).map(([key, label]) => (
                      <Toggle
                        key={String(key)}
                        checked={Boolean(settingsDraft[key])}
                        onChange={(next) => updateSetting(key, next as never)}
                        label={label}
                      />
                    ))}
                  </div>
                </SettingsSection>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                <SettingsSection title="CPU THRESHOLDS">
                  <div className="grid grid-cols-3 gap-2">
                    <NumberField label="Warning" value={settingsDraft.cpu_warning_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('cpu_warning_percent', value)} />
                    <NumberField label="Critical" value={settingsDraft.cpu_critical_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('cpu_critical_percent', value)} />
                    <NumberField label="Sustained" value={settingsDraft.cpu_sustained_seconds} min={5} max={3600} suffix="s" onChange={(value) => updateSetting('cpu_sustained_seconds', value)} />
                  </div>
                </SettingsSection>

                <SettingsSection title="MEMORY THRESHOLDS">
                  <div className="grid grid-cols-3 gap-2">
                    <NumberField label="Warning" value={settingsDraft.memory_warning_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('memory_warning_percent', value)} />
                    <NumberField label="Critical" value={settingsDraft.memory_critical_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('memory_critical_percent', value)} />
                    <NumberField label="Sustained" value={settingsDraft.memory_sustained_seconds} min={5} max={3600} suffix="s" onChange={(value) => updateSetting('memory_sustained_seconds', value)} />
                  </div>
                </SettingsSection>

                <SettingsSection title="STORAGE THRESHOLDS">
                  <div className="grid grid-cols-2 gap-2">
                    <NumberField label="Free warning" value={settingsDraft.disk_free_warning_gb} min={0.1} max={1000} step="any" suffix="GB" onChange={(value) => updateSetting('disk_free_warning_gb', value)} />
                    <NumberField label="Free critical" value={settingsDraft.disk_free_critical_gb} min={0.1} max={1000} step="any" suffix="GB" onChange={(value) => updateSetting('disk_free_critical_gb', value)} />
                    <NumberField label="Usage warning" value={settingsDraft.disk_percent_warning} min={1} max={100} suffix="%" onChange={(value) => updateSetting('disk_percent_warning', value)} />
                    <NumberField label="Usage critical" value={settingsDraft.disk_percent_critical} min={1} max={100} suffix="%" onChange={(value) => updateSetting('disk_percent_critical', value)} />
                    <NumberField label="Sustained" value={settingsDraft.disk_sustained_seconds} min={5} max={3600} suffix="s" onChange={(value) => updateSetting('disk_sustained_seconds', value)} />
                    <label className="block">
                      <MicroLabel className="block mb-1">Explicit paths</MicroLabel>
                      <input
                        value={listDrafts.diskPaths}
                        onChange={(event) => setListDrafts((previous) => ({ ...previous, diskPaths: event.target.value }))}
                        placeholder="C:\\, D:\\"
                        className="w-full bg-[#0B0E14] border border-echo-border rounded-sm px-2 py-1.5 text-xs font-mono text-echo-text outline-none focus:border-echo-cyan/50"
                      />
                    </label>
                  </div>
                </SettingsSection>

                <SettingsSection title="BATTERY & NETWORK">
                  <div className="grid grid-cols-2 gap-2">
                    <NumberField label="Battery warning" value={settingsDraft.battery_warning_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('battery_warning_percent', value)} />
                    <NumberField label="Battery critical" value={settingsDraft.battery_critical_percent} min={1} max={100} suffix="%" onChange={(value) => updateSetting('battery_critical_percent', value)} />
                    <NumberField label="Network interval" value={settingsDraft.network_check_interval_seconds} min={5} max={300} suffix="s" onChange={(value) => updateSetting('network_check_interval_seconds', value)} />
                    <NumberField label="Network timeout" value={settingsDraft.network_timeout_seconds} min={0.5} max={30} step={0.5} suffix="s" onChange={(value) => updateSetting('network_timeout_seconds', value)} />
                    <NumberField label="Offline after" value={settingsDraft.network_failure_seconds} min={10} max={1800} suffix="s" onChange={(value) => updateSetting('network_failure_seconds', value)} />
                    <label className="block col-span-1">
                      <MicroLabel className="block mb-1">Probe targets</MicroLabel>
                      <input
                        value={listDrafts.networkTargets}
                        onChange={(event) => setListDrafts((previous) => ({ ...previous, networkTargets: event.target.value }))}
                        placeholder="1.1.1.1:53, 8.8.8.8:53"
                        className="w-full bg-[#0B0E14] border border-echo-border rounded-sm px-2 py-1.5 text-xs font-mono text-echo-text outline-none focus:border-echo-cyan/50"
                      />
                    </label>
                  </div>
                </SettingsSection>

                <SettingsSection title="THERMAL THRESHOLDS">
                  <div className="grid grid-cols-3 gap-2">
                    <NumberField label="Warning" value={settingsDraft.temperature_warning_celsius} min={20} max={120} suffix="°C" onChange={(value) => updateSetting('temperature_warning_celsius', value)} />
                    <NumberField label="Critical" value={settingsDraft.temperature_critical_celsius} min={20} max={130} suffix="°C" onChange={(value) => updateSetting('temperature_critical_celsius', value)} />
                    <NumberField label="Sustained" value={settingsDraft.temperature_sustained_seconds} min={5} max={1800} suffix="s" onChange={(value) => updateSetting('temperature_sustained_seconds', value)} />
                    <NumberField label="Probe interval" value={settingsDraft.temperature_interval_seconds} min={15} max={600} suffix="s" onChange={(value) => updateSetting('temperature_interval_seconds', value)} />
                  </div>
                  {!temperature?.available && (
                    <p className="mt-2 text-[10px] font-mono text-echo-muted leading-snug">
                      No hardware sensor is exposed. Install LibreHardwareMonitor or OpenHardwareMonitor to enable thermal data.
                    </p>
                  )}
                </SettingsSection>

                <SettingsSection title="WINDOWS EVENTS & APPLICATIONS">
                  <div className="grid grid-cols-2 gap-2">
                    <NumberField label="Event poll" value={settingsDraft.windows_event_interval_seconds} min={15} max={600} suffix="s" onChange={(value) => updateSetting('windows_event_interval_seconds', value)} />
                    <NumberField label="Lookback" value={settingsDraft.windows_event_lookback_seconds} min={30} max={3600} suffix="s" onChange={(value) => updateSetting('windows_event_lookback_seconds', value)} />
                    <NumberField label="Max per log" value={settingsDraft.windows_event_max_per_log} min={5} max={100} onChange={(value) => updateSetting('windows_event_max_per_log', value)} />
                    <NumberField label="Hung window after" value={settingsDraft.hung_window_seconds} min={5} max={600} suffix="s" onChange={(value) => updateSetting('hung_window_seconds', value)} />
                    <label className="block col-span-2">
                      <MicroLabel className="block mb-1">Monitored applications</MicroLabel>
                      <input
                        value={listDrafts.monitoredApps}
                        onChange={(event) => setListDrafts((previous) => ({ ...previous, monitoredApps: event.target.value }))}
                        placeholder="Code.exe, chrome.exe"
                        className="w-full bg-[#0B0E14] border border-echo-border rounded-sm px-2 py-1.5 text-xs font-mono text-echo-text outline-none focus:border-echo-cyan/50"
                      />
                    </label>
                  </div>
                </SettingsSection>
              </div>

              <div className="flex items-center justify-between gap-3 border border-echo-border bg-[#0B0E14] rounded-md px-3 py-2">
                <span className={`font-mono text-[10px] ${settingsMessage?.toLowerCase().includes('saved') ? 'text-echo-success' : settingsMessage ? 'text-echo-danger' : 'text-echo-muted'}`}>
                  {settingsMessage || 'Changes apply immediately. Profile selection resets detection thresholds.'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => status && setSettingsDraft(status.settings)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border border-echo-border font-mono text-[10px] text-echo-muted hover:text-white"
                  >
                    <RotateCcw className="w-3 h-3" /> RESET
                  </button>
                  <button
                    onClick={handleSaveSettings}
                    disabled={busy}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border border-echo-cyan/50 bg-echo-cyan/10 font-mono text-[10px] text-echo-cyan hover:bg-echo-cyan/20 disabled:opacity-50"
                  >
                    <Save className="w-3 h-3" /> SAVE
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
