export interface Message {
  id: string;
  conversation_id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  created_at: string;
  token_count?: number;
  metadata?: Record<string, any>;
  isStreaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  latest_message?: string;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  database: 'connected' | 'error';
  ai_provider: string;
  ai_available: boolean;
  timestamp: string;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  disk_percent: number;
  uptime_seconds: number;
  platform: string;
}

export interface AppSettings {
  ai_provider: string;
  ai_model: string;
  ai_api_key_configured: boolean;
  ai_api_key?: string;
  ai_api_base?: string;
  ai_temperature: number;
  ai_max_tokens: number;
  theme: string;
  startup_behavior: string;
  data_dir: string;
}

export type MemoryCategory =
  | 'fact'
  | 'project'
  | 'preference'
  | 'context'
  | 'task'
  | 'conversation';

export interface MemoryItem {
  id: string;
  category: MemoryCategory;
  key: string;
  content: string;
  confidence: number;
  sensitivity: 'normal' | 'high';
  source: string;
  tags: string[];
  pinned: boolean;
  archived: boolean;
  permission_granted: boolean;
  last_used_at?: string | null;
  use_count: number;
  created_at: string;
  updated_at: string;
}

export interface MemoryStats {
  total: number;
  by_category: Record<string, number>;
  by_source: Record<string, number>;
  sensitive: number;
  pinned: number;
  last_updated_at: string | null;
}

export interface MemoryExport {
  exported_at: string;
  count: number;
  memories: MemoryItem[];
}

export interface TaskItem {
  id: string;
  conversation_id?: string;
  goal: string;
  status: 'created' | 'planning' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

export interface ToolItem {
  name: string;
  description: string;
  category: 'screen' | 'window' | 'mouse' | 'keyboard' | 'application' | 'filesystem' | 'clipboard' | 'system';
  permission_level: 'automatic' | 'approval_required';
  schema: Record<string, any>;
  timeout_seconds: number;
}

export interface ApprovalRequest {
  id: string;
  tool_name: string;
  args: Record<string, any>;
  category: string;
  description: string;
  status: 'pending' | 'approved' | 'denied' | 'expired';
  created_at: string;
  resolved_at?: string;
}

export interface ActionLogItem {
  id: string;
  action: string;
  actor: string;
  details: string;
  status: string;
  created_at: string;
}

export interface ActiveWindowInfo {
  handle: number;
  title: string;
  pid: number;
  process_name: string;
}

export type AgentOrbState =
  | 'idle'
  | 'thinking'
  | 'speaking'
  | 'executing'
  | 'error'
  | 'disconnected'
  | 'listening'
  | 'processing'
  | 'muted';

// ---------------------------------------------------------------------------
// Voice subsystem
// ---------------------------------------------------------------------------

export type VoiceMode = 'push_to_talk' | 'wake_word' | 'continuous';

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'muted' | 'error';

export interface VoiceSettings {
  auto_start: boolean;
  mode: VoiceMode;
  wake_word: string;
  wake_aliases: string[];
  wake_sensitivity: number;
  stt_model: string;
  stt_device: string;
  stt_compute_type: string;
  stt_language: string;
  partial_transcription: boolean;
  min_transcript_confidence: number;
  tts_engine: string;
  tts_voice: string | null;
  tts_rate: number;
  tts_volume: number;
  mic_device_index: number | null;
  mic_sample_rate: number;
  silence_threshold_seconds: number;
  vad_rms_threshold: number;
  min_speech_seconds: number;
  max_utterance_seconds: number;
  barge_in_enabled: boolean;
  barge_in_rms_threshold: number;
  continuous_timeout_seconds: number;
  wake_command_timeout_seconds: number;
  save_recordings: boolean;
  recording_retention: number;
}

export interface VoiceStatus {
  state: VoiceState;
  enabled: boolean;
  running: boolean;
  muted: boolean;
  mic_active: boolean;
  capturing: boolean;
  speaking: boolean;
  mode: VoiceMode;
  wake_word: string;
  wake_active: boolean;
  level: number;
  noise_floor: number;
  sample_rate: number;
  device: string | null;
  stt_available: boolean;
  stt_loaded: boolean;
  stt_model: string;
  stt_error: string | null;
  partial_transcription: boolean;
  tts_available: boolean;
  tts_running: boolean;
  tts_queue_size: number;
  tts_error: string | null;
  tts_voice: string | null;
  barge_in_enabled: boolean;
  continuous_timeout_seconds: number;
  conversation_id: string | null;
  last_transcript: string;
  last_reply: string;
  last_error: string | null;
  last_notice: string | null;
  stt_latency_ms: number | null;
  first_token_ms: number | null;
  turns_completed: number;
  recordings_saved: number;
  save_recordings: boolean;
  started_at: number | null;
  dropped_frames: number;
  settings: VoiceSettings;
  installed?: Record<string, boolean>;
}

export interface VoiceDevice {
  index: number;
  name: string;
  channels: number;
  sample_rate: number;
  host_api?: string;
  is_default?: boolean;
}

export interface VoiceOption {
  id: string;
  name: string;
  languages: string[];
}

export interface VoiceRecording {
  name: string;
  size_bytes: number;
  created_at: string;
}

export interface VoiceTranscript {
  text: string;
  isPartial: boolean;
  confidence?: number;
  dropped?: boolean;
  cleared?: boolean;
  receivedAt: number;
}

// ---------------------------------------------------------------------------
// System monitoring
// ---------------------------------------------------------------------------

export type MonitorSeverity = 'info' | 'notice' | 'warning' | 'critical';
export type MonitorAlertStatus = 'active' | 'recovered' | 'resolved';
export type MonitorCategory =
  | 'cpu'
  | 'memory'
  | 'disk'
  | 'battery'
  | 'network'
  | 'temperature'
  | 'application'
  | 'windows_event'
  | 'system';
export type MonitoringProfile = 'quiet' | 'balanced' | 'strict';

export interface MonitorCounts {
  info: number;
  notice: number;
  warning: number;
  critical: number;
  total: number;
  unacknowledged: number;
}

export interface MonitorAlert {
  id: string;
  dedupe_key: string;
  category: MonitorCategory;
  severity: MonitorSeverity;
  title: string;
  message: string;
  details: Record<string, any>;
  status: MonitorAlertStatus;
  source: string;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
  last_notified_at: string;
  last_escalated_at: string | null;
  acknowledged_at: string | null;
  recovered_at: string | null;
  resolved_at: string | null;
  escalation_level: number;
}

export interface MonitorEvent {
  id: string;
  dedupe_key: string | null;
  category: MonitorCategory;
  severity: MonitorSeverity;
  kind: string;
  title: string;
  message: string;
  details: Record<string, any>;
  alert_id: string | null;
  occurred_at: string;
  recorded_at: string;
}

export interface MonitorDisk {
  path: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
}

export interface MonitoredApplication {
  name: string;
  running: boolean;
  instances: number;
  pids: number[];
  memory_mb: number;
  status: string;
  started_at: string | null;
}

export interface MonitorSnapshot {
  available: boolean;
  timestamp: string | null;
  cpu: {
    percent?: number;
    cores_logical?: number;
    cores_physical?: number;
    frequency_mhz?: number | null;
  };
  memory: {
    percent?: number;
    used_gb?: number;
    available_gb?: number;
    total_gb?: number;
    swap_percent?: number;
  };
  disks: MonitorDisk[];
  battery: {
    present: boolean;
    percent: number | null;
    plugged: boolean | null;
    seconds_left: number | null;
  };
  network: {
    online: boolean | null;
    latency_ms: number | null;
    last_check_at: string | null;
    down_kbps: number;
    up_kbps: number;
    errors: string[];
  };
  temperature: {
    available: boolean;
    celsius: number | null;
    source: string | null;
    reason: string | null;
    checked_at: string | null;
  };
  monitored_applications: MonitoredApplication[];
  hung_windows: { handle: number; title: string; pid: number; process_name: string }[];
  process_count: number | null;
  top_processes: { pid: number; name: string; memory_mb: number; status: string }[];
  boot_time: string | null;
  uptime_seconds: number | null;
  platform: string | null;
  windows_events_available: boolean | null;
  windows_events_error?: string | null;
  alert_counts: MonitorCounts;
}

export interface MonitorHistoryPoint {
  t: string | null;
  cpu: number;
  memory: number;
  disk_free_gb: number | null;
  down_kbps: number;
  up_kbps: number;
}

export interface MonitorSettings {
  enabled: boolean;
  profile: MonitoringProfile;
  poll_interval_seconds: number;
  retention_days: number;

  monitor_cpu: boolean;
  monitor_memory: boolean;
  monitor_disk: boolean;
  monitor_battery: boolean;
  monitor_network: boolean;
  monitor_temperature: boolean;
  monitor_processes: boolean;
  monitor_hung_windows: boolean;
  monitor_windows_events: boolean;

  cpu_warning_percent: number;
  cpu_critical_percent: number;
  cpu_sustained_seconds: number;
  memory_warning_percent: number;
  memory_critical_percent: number;
  memory_sustained_seconds: number;

  disk_paths: string[];
  disk_free_warning_gb: number;
  disk_free_critical_gb: number;
  disk_percent_warning: number;
  disk_percent_critical: number;
  disk_sustained_seconds: number;

  battery_warning_percent: number;
  battery_critical_percent: number;
  battery_sustained_seconds: number;

  network_targets: string[];
  network_check_interval_seconds: number;
  network_timeout_seconds: number;
  network_failure_seconds: number;

  temperature_warning_celsius: number;
  temperature_critical_celsius: number;
  temperature_sustained_seconds: number;
  temperature_interval_seconds: number;

  windows_event_interval_seconds: number;
  windows_event_lookback_seconds: number;
  windows_event_max_per_log: number;

  monitored_applications: string[];
  hung_window_seconds: number;

  alert_cooldown_seconds: number;
  escalation_seconds: number;
  recovery_margin_percent: number;
  recovery_margin_gb: number;
  notification_on_recovery: boolean;

  top_process_count: number;
}

export interface MonitorStatus {
  running: boolean;
  enabled: boolean;
  profile: MonitoringProfile;
  started_at: string | null;
  service_started_at?: string | null;
  last_error: string | null;
  last_poll_at: string | null;
  last_network_check_at: string | null;
  last_temperature_check_at: string | null;
  last_windows_event_check_at: string | null;
  snapshot: MonitorSnapshot;
  history: MonitorHistoryPoint[];
  counts: MonitorCounts;
  settings: MonitorSettings;
  availability: {
    temperature: { available: boolean; reason: string | null; source: string | null };
    battery: { available: boolean };
    windows_events: { available: boolean | null; error: string | null };
    network: { online: boolean | null; error: string | null };
  };
}

// ---------------------------------------------------------------------------
// Remote relay (Stage 5)
// ---------------------------------------------------------------------------

export type RemoteSeverity = 'info' | 'notice' | 'warning' | 'critical';
export type RemoteQueueStatus =
  | 'queued'
  | 'sending'
  | 'sent'
  | 'failed'
  | 'expired'
  | 'suppressed';
export type RemotePendingStatus = 'pending' | 'approved' | 'denied' | 'executed' | 'expired';
export type RemoteTaskStatus = 'created' | 'planning' | 'in_progress' | 'completed' | 'failed' | 'cancelled';

export interface RemoteSettings {
  enabled: boolean;
  bot_username: string | null;
  owner_user_id: number | null;
  owner_username: string | null;
  owner_display_name: string | null;
  allowed_user_ids: number[];
  pairing_ttl_seconds: number;
  command_rate_limit: number;
  pairing_attempt_limit: number;
  pairing_attempt_window_seconds: number;
  poll_timeout_seconds: number;
  reconnect_max_seconds: number;
  screenshot_enabled: boolean;
  max_screenshot_mb: number;
  notify_critical_alerts: boolean;
  notify_warnings: boolean;
  notify_task_results: boolean;
  notify_approval_requests: boolean;
  notify_connectivity: boolean;
  notify_monitor_events: boolean;
  monitor_event_min_severity: RemoteSeverity;
  monitor_event_categories: string[];
  queue_ttl_hours: number;
  queue_max_items: number;
  queue_batch_size: number;
  send_rate_per_second: number;
  paused: boolean;
  pause_reason: string | null;
  // API-safe token metadata (the token itself is never returned)
  bot_token_configured: boolean;
  bot_token_hint: string;
  effective_owner_user_id: number | null;
}

export interface RemoteRelayInfo {
  enabled: boolean;
  connected: boolean;
  running: boolean;
  bot_username: string | null;
  polling: boolean;
  last_poll_at: string | null;
  last_heartbeat_at: string | null;
  last_error: string | null;
  reconnect_attempts: number;
}

export interface RemoteCurrentTask {
  id: string;
  goal: string;
  status: string;
  source: 'local' | 'remote';
}

export interface RemoteHealth {
  state: 'healthy' | 'warning' | 'critical' | 'starting' | 'unknown';
  cpu_percent: number | null;
  memory_percent: number | null;
  memory_used_gb: number | null;
  memory_total_gb: number | null;
  disks: { path: string; free_gb: number | null; total_gb: number | null; percent: number | null }[];
  battery: {
    present?: boolean;
    percent?: number | null;
    plugged?: boolean | null;
    seconds_left?: number | null;
  };
  network_online: boolean | null;
  uptime_seconds: number | null;
  active_alerts: number;
  alerts_by_severity: { critical: number; warning: number; notice: number; info: number };
  monitoring_running: boolean;
}

export interface RemoteRuntimeStatus {
  timestamp: string;
  relay: RemoteRelayInfo;
  pc_online: boolean;
  echo_running: boolean;
  echo_state: string;
  paused: boolean;
  pause_reason: string | null;
  current_task: RemoteCurrentTask | null;
  health: RemoteHealth;
  last_heartbeat_at: string | null;
  last_heartbeat_age_seconds: number | null;
}

export interface RemoteQueueStats {
  queued: number;
  sending: number;
  sent: number;
  failed: number;
  expired: number;
  suppressed: number;
  total: number;
}

export interface RemoteUser {
  telegram_id: number;
  username: string | null;
  display_name: string | null;
  role: 'owner' | 'allowed';
  paired_at: string | null;
  last_seen_at: string | null;
  added_by: string | null;
}

export interface RemotePendingAction {
  approval_id: string;
  telegram_id: number;
  command: string;
  tool_name: string;
  arguments: string;
  status: RemotePendingStatus;
  result: string | null;
  task_id: string | null;
  created_at: string;
  expires_at: string;
}

export interface RemoteStatus {
  enabled: boolean;
  running: boolean;
  connected: boolean;
  polling: boolean;
  paused: boolean;
  pause_reason: string | null;
  bot_username: string | null;
  token_configured: boolean;
  started_at: string | null;
  last_error: string | null;
  reconnect_attempts: number;
  last_heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  active_pairing: boolean;
  pairing_expires_at: string | null;
  settings: RemoteSettings;
  relay: RemoteRelayInfo;
  remote_status: RemoteRuntimeStatus;
  queue: RemoteQueueStats;
  users: RemoteUser[];
  pending_actions: RemotePendingAction[];
  listener: {
    transport: string;
    inbound_ports: number;
    screenshots_owner_only: boolean;
  };
}

export interface RemotePairingCode {
  code: string;
  expires_at: string;
  ttl_seconds: number;
  bot_username: string | null;
  instructions: string;
}

export interface RemoteCommand {
  id: string;
  telegram_id: number;
  username: string | null;
  command: string;
  args: string | null;
  status: string;
  response: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RemoteNotification {
  id: string;
  dedupe_key: string | null;
  category: string;
  severity: RemoteSeverity;
  title: string;
  message: string;
  payload: string | null;
  status: RemoteQueueStatus;
  attempts: number;
  next_attempt_at: string | null;
  created_at: string;
  sent_at: string | null;
  expires_at: string | null;
  last_error: string | null;
}

export interface RemoteTask {
  id: string;
  telegram_id: number;
  command: string;
  goal: string;
  status: RemoteTaskStatus;
  result: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// File intelligence (Stage 6)
// ---------------------------------------------------------------------------

export type FileCategory =
  | 'document'
  | 'spreadsheet'
  | 'presentation'
  | 'image'
  | 'audio'
  | 'video'
  | 'code'
  | 'archive'
  | 'executable'
  | 'other';

export interface FileSettings {
  content_indexing: boolean;
  ocr_enabled: boolean;
  include_hidden: boolean;
  max_file_size_mb: number;
  max_hash_size_mb: number;
  max_content_chars: number;
  max_index_files: number;
  bulk_confirm_threshold: number;
}

export interface FileCapabilities {
  text: boolean;
  csv: boolean;
  docx: boolean;
  xlsx: boolean;
  pptx: boolean;
  pdf: boolean;
  image_metadata: boolean;
  ocr: boolean;
}

export interface ApprovedDirectory {
  id: string;
  path: string;
  label: string | null;
  recursive: boolean;
  enabled: boolean;
  created_at: string;
  last_indexed_at: string | null;
  file_count: number;
}

export interface FileEntry {
  id: string;
  directory_id: string;
  path: string;
  name: string;
  extension: string;
  category: FileCategory;
  size_bytes: number;
  modified_at: number | null;
  created_at: string | null;
  content_hash: string | null;
  content_status: string;
  indexed_at: string;
  snippet?: string | null;
}

export interface FileSearchResult {
  results: FileEntry[];
  count: number;
  total: number;
  limit: number;
  offset: number;
}

export interface FileCategoryStat {
  category: FileCategory;
  count: number;
  bytes: number;
}

export interface FileLargest {
  path: string;
  name: string;
  size_bytes: number;
  modified_at: number | null;
  category: FileCategory;
}

export interface FileStats {
  total_files: number;
  total_bytes: number;
  by_category: FileCategoryStat[];
  largest: FileLargest[];
  last_indexed_at: string | null;
  duplicate_groups: number;
  duplicate_wasted_bytes: number;
  directories: ApprovedDirectory[];
  settings: FileSettings;
  capabilities: FileCapabilities;
  approved_directory_count?: number;
  locked?: boolean;
}

export interface DuplicateFile {
  id: string;
  path: string;
  name: string;
  extension: string;
  category: FileCategory;
  size_bytes: number;
  modified_at: number | null;
}

export interface DuplicateGroup {
  content_hash: string;
  size_bytes: number;
  count: number;
  files: DuplicateFile[];
}

export interface FileActionLog {
  id: string;
  action: string;
  source_path: string | null;
  target_path: string | null;
  status: string;
  details: Record<string, any>;
  created_at: string;
}

export interface FileIndexResult {
  files_seen: number;
  indexed: number;
  unchanged: number;
  skipped: number;
  errors: number;
  removed: number;
  truncated: boolean;
  duration_ms: number;
  directories: {
    directory_id: string;
    path: string;
    files_seen?: number;
    indexed?: number;
    unchanged?: number;
    skipped?: number;
    errors?: number;
    removed?: number;
    truncated?: boolean;
    error?: string;
  }[];
}

export interface FileDetails extends FileEntry {
  indexed: boolean;
  metadata: Record<string, any>;
  preview: string | null;
  size_bytes: number;
  modified_at: number | null;
}

export interface FileSummary {
  path: string;
  summary: string;
  ai_used: boolean;
  status: string;
  extractor: string;
  chars?: number;
  warning?: string | null;
  message?: string;
}

export interface FilePlanItem {
  source: string;
  target: string;
  category?: FileCategory;
  folder?: string;
  kept?: string;
  content_hash?: string;
  size_bytes?: number;
}

export interface FileOperationPlan {
  directory?: string;
  destination_root?: string;
  planned: number;
  plan: FilePlanItem[];
  threshold?: number;
  dry_run: boolean;
  moved?: number;
  skipped?: number;
  renamed?: number;
}
