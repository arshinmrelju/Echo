import {
  ActionLogItem,
  ActiveWindowInfo,
  AppSettings,
  ApprovalRequest,
  ApprovedDirectory,
  Conversation,
  DuplicateGroup,
  FileActionLog,
  FileDetails,
  FileEntry,
  FileIndexResult,
  FileOperationPlan,
  FileSearchResult,
  FileStats,
  FileSummary,
  MemoryCategory,
  MemoryExport,
  MemoryItem,
  MemoryStats,
  MonitorAlert,
  MonitorAlertStatus,
  MonitorCategory,
  MonitorEvent,
  MonitorSettings,
  MonitorSeverity,
  MonitorStatus,
  RemoteCommand,
  RemoteNotification,
  RemotePairingCode,
  RemotePendingAction,
  RemoteQueueStatus,
  RemoteSettings,
  RemoteStatus,
  RemoteTask,
  RemoteUser,
  SystemMetrics,
  SystemStatus,
  TaskItem,
  ToolItem,
  VoiceDevice,
  VoiceOption,
  VoiceRecording,
  VoiceSettings,
  VoiceStatus,
} from '../types';

const API_BASE = 'http://127.0.0.1:8000/api/v1';

export class ApiError extends Error {
  status: number;
  detail: any;

  constructor(status: number, detail: any) {
    super(
      typeof detail === 'string'
        ? detail
        : detail?.message || detail?.detail || `HTTP ${status}`
    );
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  get plan(): FileOperationPlan | undefined {
    if (this.detail && typeof this.detail === 'object' && 'plan' in this.detail) {
      return (this.detail as { plan?: FileOperationPlan }).plan;
    }
    return undefined;
  }
}

async function throwApiError(res: Response): Promise<never> {
  const payload = await res.json().catch(() => null);
  throw new ApiError(res.status, payload?.detail ?? `HTTP ${res.status}`);
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) await throwApiError(res);
  return res.json();
}

export const apiClient = {
  // System
  async getStatus(): Promise<SystemStatus> {
    const res = await fetch(`${API_BASE}/system/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getMetrics(): Promise<SystemMetrics> {
    const res = await fetch(`${API_BASE}/system/metrics`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Conversations
  async listConversations(): Promise<Conversation[]> {
    const res = await fetch(`${API_BASE}/conversations`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async createConversation(title?: string): Promise<Conversation> {
    const res = await fetch(`${API_BASE}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getConversation(id: string) {
    const res = await fetch(`${API_BASE}/conversations/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateConversation(id: string, title: string): Promise<Conversation> {
    const res = await fetch(`${API_BASE}/conversations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async deleteConversation(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/conversations/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Settings
  async getSettings(): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateSettings(settings: Partial<AppSettings>): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Memory ------------------------------------------------------------------

  async listMemories(
    options: {
      category?: MemoryCategory | 'all';
      query?: string;
      source?: string;
      includeArchived?: boolean;
      limit?: number;
    } = {}
  ): Promise<MemoryItem[]> {
    const params = new URLSearchParams();
    if (options.category && options.category !== 'all') params.append('category', options.category);
    if (options.query) params.append('query', options.query);
    if (options.source) params.append('source', options.source);
    if (options.includeArchived) params.append('include_archived', 'true');
    if (options.limit) params.append('limit', String(options.limit));
    const res = await fetch(`${API_BASE}/memory?${params.toString()}`);
    return json<MemoryItem[]>(res);
  },

  async getMemoryStats(): Promise<MemoryStats> {
    const res = await fetch(`${API_BASE}/memory/stats`);
    return json<MemoryStats>(res);
  },

  async exportMemories(): Promise<MemoryExport> {
    const res = await fetch(`${API_BASE}/memory/export`);
    return json<MemoryExport>(res);
  },

  async createMemory(item: {
    category: MemoryCategory;
    key: string;
    content: string;
    confidence?: number;
    source?: string;
    tags?: string[];
    pinned?: boolean;
    allow_sensitive?: boolean;
  }): Promise<MemoryItem> {
    const res = await fetch(`${API_BASE}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    });
    return json<MemoryItem>(res);
  },

  async updateMemory(
    id: string,
    patch: Partial<{
      category: MemoryCategory;
      key: string;
      content: string;
      confidence: number;
      source: string;
      tags: string[];
      pinned: boolean;
      archived: boolean;
      sensitivity: 'normal' | 'high';
      allow_sensitive: boolean;
    }>
  ): Promise<MemoryItem> {
    const res = await fetch(`${API_BASE}/memory/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    return json<MemoryItem>(res);
  },

  async deleteMemory(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/memory/${id}`, { method: 'DELETE' });
    return json<{ success: boolean }>(res);
  },

  async clearMemories(category?: MemoryCategory): Promise<{ success: boolean; removed: number }> {
    const res = await fetch(`${API_BASE}/memory/clear`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: category ?? null, confirm: true }),
    });
    return json<{ success: boolean; removed: number }>(res);
  },

  // File intelligence ---------------------------------------------------------

  async getFileStatus(): Promise<FileStats> {
    const res = await fetch(`${API_BASE}/files/status`);
    return json<FileStats>(res);
  },

  async getFileStats(): Promise<FileStats> {
    const res = await fetch(`${API_BASE}/files/stats`);
    return json<FileStats>(res);
  },

  async listFileDirectories(): Promise<{ directories: ApprovedDirectory[] }> {
    const res = await fetch(`${API_BASE}/files/directories`);
    return json<{ directories: ApprovedDirectory[] }>(res);
  },

  async addFileDirectory(
    path: string,
    options: { label?: string; recursive?: boolean; indexNow?: boolean } = {}
  ): Promise<{ success: boolean; directory: ApprovedDirectory; index: FileIndexResult | null }> {
    const res = await fetch(`${API_BASE}/files/directories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path,
        label: options.label || null,
        recursive: options.recursive ?? true,
        index_now: options.indexNow ?? false,
      }),
    });
    return json(res);
  },

  async removeFileDirectory(id: string): Promise<{ success: boolean; id: string }> {
    const res = await fetch(`${API_BASE}/files/directories/${id}`, { method: 'DELETE' });
    return json(res);
  },

  async indexFiles(directoryId?: string, force = false): Promise<{ success: boolean; result: FileIndexResult }> {
    const res = await fetch(`${API_BASE}/files/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory_id: directoryId ?? null, force }),
    });
    return json(res);
  },

  async searchFiles(
    params: {
      query?: string;
      extension?: string;
      category?: string;
      minSizeMb?: number;
      maxSizeMb?: number;
      modifiedAfter?: string;
      modifiedBefore?: string;
      directoryId?: string;
      sort?: 'modified' | 'oldest' | 'name' | 'size';
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<FileSearchResult> {
    const query = new URLSearchParams();
    if (params.query) query.append('q', params.query);
    if (params.extension) query.append('extension', params.extension);
    if (params.category) query.append('category', params.category);
    if (params.minSizeMb !== undefined) query.append('min_size_mb', String(params.minSizeMb));
    if (params.maxSizeMb !== undefined) query.append('max_size_mb', String(params.maxSizeMb));
    if (params.modifiedAfter) query.append('modified_after', params.modifiedAfter);
    if (params.modifiedBefore) query.append('modified_before', params.modifiedBefore);
    if (params.directoryId) query.append('directory_id', params.directoryId);
    if (params.sort) query.append('sort', params.sort);
    if (params.limit) query.append('limit', String(params.limit));
    if (params.offset) query.append('offset', String(params.offset));
    const res = await fetch(`${API_BASE}/files/search?${query.toString()}`);
    return json<FileSearchResult>(res);
  },

  async getFileCategories(): Promise<{ categories: FileStats['by_category'] }> {
    const res = await fetch(`${API_BASE}/files/categories`);
    return json(res);
  },

  async getDuplicateFiles(
    minSizeMb = 0,
    directoryId?: string
  ): Promise<{ groups: DuplicateGroup[]; count: number; file_count: number }> {
    const params = new URLSearchParams({ min_size_mb: String(minSizeMb) });
    if (directoryId) params.append('directory_id', directoryId);
    const res = await fetch(`${API_BASE}/files/duplicates?${params.toString()}`);
    return json(res);
  },

  async getLargeFiles(minSizeMb = 100, limit = 50): Promise<{ files: FileEntry[]; count: number }> {
    const res = await fetch(`${API_BASE}/files/large?min_size_mb=${minSizeMb}&limit=${limit}`);
    return json(res);
  },

  async getFileDetails(path: string): Promise<FileDetails> {
    const res = await fetch(`${API_BASE}/files/details?path=${encodeURIComponent(path)}`);
    return json<FileDetails>(res);
  },

  async getFileActivity(limit = 100): Promise<{ actions: FileActionLog[]; count: number }> {
    const res = await fetch(`${API_BASE}/files/activity?limit=${limit}`);
    return json(res);
  },

  async updateFileSettings(settings: Partial<FileStats['settings']>): Promise<{ success: boolean; settings: FileStats['settings'] }> {
    const res = await fetch(`${API_BASE}/files/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    return json(res);
  },

  async openFile(path: string): Promise<{ success: boolean; path: string }> {
    const res = await fetch(`${API_BASE}/files/open`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    return json(res);
  },

  async renameFile(
    path: string,
    newName: string,
    confirm = false
  ): Promise<{ success: boolean; old_path: string; new_path: string }> {
    const res = await fetch(`${API_BASE}/files/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, new_name: newName, confirm }),
    });
    return json(res);
  },

  async copyFile(
    path: string,
    destination: string,
    confirm = false
  ): Promise<{ success: boolean; source: string; destination: string }> {
    const res = await fetch(`${API_BASE}/files/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, destination, confirm }),
    });
    return json(res);
  },

  async moveFile(
    path: string,
    destination: string,
    confirm = false
  ): Promise<{ success: boolean; source: string; destination: string }> {
    const res = await fetch(`${API_BASE}/files/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, destination, confirm }),
    });
    return json(res);
  },

  async organizeFiles(
    directory: string,
    options: { destinationRoot?: string; confirm?: boolean; dryRun?: boolean } = {}
  ): Promise<FileOperationPlan> {
    const res = await fetch(`${API_BASE}/files/organize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        directory,
        destination_root: options.destinationRoot || null,
        confirm: options.confirm ?? false,
        dry_run: options.dryRun ?? true,
      }),
    });
    return json<FileOperationPlan>(res);
  },

  async bulkRenameFiles(
    directory: string,
    find: string,
    replace: string,
    options: { confirm?: boolean; dryRun?: boolean } = {}
  ): Promise<FileOperationPlan> {
    const res = await fetch(`${API_BASE}/files/bulk-rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        directory,
        find,
        replace,
        confirm: options.confirm ?? false,
        dry_run: options.dryRun ?? true,
      }),
    });
    return json<FileOperationPlan>(res);
  },

  async quarantineDuplicates(
    directory?: string,
    options: { confirm?: boolean; dryRun?: boolean } = {}
  ): Promise<FileOperationPlan> {
    const res = await fetch(`${API_BASE}/files/duplicates/quarantine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        directory: directory ?? null,
        confirm: options.confirm ?? false,
        dry_run: options.dryRun ?? true,
      }),
    });
    return json<FileOperationPlan>(res);
  },

  async summarizeFile(path: string, useAi = true): Promise<FileSummary> {
    const res = await fetch(`${API_BASE}/files/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, use_ai: useAi }),
    });
    return json<FileSummary>(res);
  },

  // Tasks
  async listTasks(): Promise<TaskItem[]> {
    const res = await fetch(`${API_BASE}/tasks`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async createTask(goal: string, conversation_id?: string): Promise<TaskItem> {
    const res = await fetch(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, conversation_id }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateTask(id: string, status: string): Promise<TaskItem> {
    const res = await fetch(`${API_BASE}/tasks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async deleteTask(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/tasks/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Tools & Desktop Control
  async listTools(category?: string): Promise<{ tools: ToolItem[]; count: number }> {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    const res = await fetch(`${API_BASE}/tools?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async executeTool(tool_name: string, args: Record<string, any> = {}, approval_id?: string) {
    const res = await fetch(`${API_BASE}/tools/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name,
        arguments: args,
        approval_id,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listApprovals(): Promise<ApprovalRequest[]> {
    const res = await fetch(`${API_BASE}/tools/approvals`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async resolveApproval(request_id: string, approved: boolean): Promise<any> {
    const res = await fetch(`${API_BASE}/tools/approvals/${request_id}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getToolLogs(limit: number = 50): Promise<ActionLogItem[]> {
    const res = await fetch(`${API_BASE}/tools/logs?limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getActiveWindow(): Promise<ActiveWindowInfo> {
    const res = await this.executeTool('window.get_active', {});
    if (res.success && res.data) {
      return res.data as ActiveWindowInfo;
    }
    return { handle: 0, title: 'Unknown', pid: 0, process_name: 'none' };
  },

  // Voice ------------------------------------------------------------------

  async getVoiceStatus(): Promise<VoiceStatus> {
    const res = await fetch(`${API_BASE}/voice/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getVoiceSettings(): Promise<{ settings: VoiceSettings; defaults: VoiceSettings; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/settings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateVoiceSettings(
    settings: Partial<VoiceSettings>
  ): Promise<{ success: boolean; settings: VoiceSettings; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async startVoice(): Promise<{ success: boolean; error: string | null; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/start`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async stopVoice(): Promise<{ success: boolean; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/stop`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async muteVoice(): Promise<{ success: boolean; error: string | null; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/mute`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async unmuteVoice(): Promise<{ success: boolean; error: string | null; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/unmute`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async stopSpeaking(): Promise<{ success: boolean; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/stop-speaking`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async dismissVoice(): Promise<{ success: boolean; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/dismiss`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async testVoiceSpeech(text?: string): Promise<{ success: boolean; error: string | null; status: VoiceStatus }> {
    const res = await fetch(`${API_BASE}/voice/test-speech`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(text ? { text } : {}),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listVoiceDevices(force = false): Promise<VoiceDevice[]> {
    const res = await fetch(`${API_BASE}/voice/devices?force=${force ? 'true' : 'false'}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.devices || [];
  },

  async listVoiceOptions(): Promise<VoiceOption[]> {
    const res = await fetch(`${API_BASE}/voice/voices`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.voices || [];
  },

  async getVoiceDiagnostics(): Promise<Record<string, any>> {
    const res = await fetch(`${API_BASE}/voice/diagnostics`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listVoiceRecordings(): Promise<{ recordings: VoiceRecording[]; enabled: boolean }> {
    const res = await fetch(`${API_BASE}/voice/recordings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async deleteVoiceRecordings(): Promise<{ success: boolean; removed: number }> {
    const res = await fetch(`${API_BASE}/voice/recordings`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // System monitoring -------------------------------------------------------

  async getMonitoringStatus(): Promise<MonitorStatus> {
    const res = await fetch(`${API_BASE}/monitoring/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getMonitoringSnapshot(): Promise<{
    snapshot: MonitorStatus['snapshot'];
    history: MonitorStatus['history'];
    counts: MonitorStatus['counts'];
    running: boolean;
  }> {
    const res = await fetch(`${API_BASE}/monitoring/snapshot`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getMonitoringSettings(): Promise<{
    settings: MonitorSettings;
    defaults: MonitorSettings;
    profiles: Record<string, MonitorSettings>;
    status: MonitorStatus;
  }> {
    const res = await fetch(`${API_BASE}/monitoring/settings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateMonitoringSettings(
    settings: Partial<MonitorSettings>
  ): Promise<{ success: boolean; settings: MonitorSettings; status: MonitorStatus }> {
    const res = await fetch(`${API_BASE}/monitoring/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async startMonitoring(): Promise<{ success: boolean; status: MonitorStatus }> {
    const res = await fetch(`${API_BASE}/monitoring/start`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async stopMonitoring(): Promise<{ success: boolean; status: MonitorStatus }> {
    const res = await fetch(`${API_BASE}/monitoring/stop`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listMonitorAlerts(
    status?: MonitorAlertStatus,
    limit: number = 200
  ): Promise<{ alerts: MonitorAlert[]; count: number }> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    const res = await fetch(`${API_BASE}/monitoring/alerts?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async acknowledgeMonitorAlert(alertId: string): Promise<{ success: boolean; alert: MonitorAlert }> {
    const res = await fetch(`${API_BASE}/monitoring/alerts/${alertId}/acknowledge`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async resolveMonitorAlert(alertId: string): Promise<{ success: boolean; alert: MonitorAlert }> {
    const res = await fetch(`${API_BASE}/monitoring/alerts/${alertId}/resolve`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listMonitorEvents(
    limit: number = 100,
    category?: MonitorCategory,
    severity?: MonitorSeverity
  ): Promise<{ events: MonitorEvent[]; count: number }> {
    const params = new URLSearchParams();
    params.append('limit', String(limit));
    if (category) params.append('category', category);
    if (severity) params.append('severity', severity);
    const res = await fetch(`${API_BASE}/monitoring/events?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Remote relay ------------------------------------------------------------

  async getRemoteStatus(): Promise<RemoteStatus> {
    const res = await fetch(`${API_BASE}/remote/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async getRemoteSettings(): Promise<{ settings: RemoteSettings; defaults: RemoteSettings; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/settings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async updateRemoteSettings(
    settings: Partial<RemoteSettings> & { bot_token?: string }
  ): Promise<{ success: boolean; settings: RemoteSettings; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async startRemote(): Promise<{ success: boolean; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/start`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async stopRemote(): Promise<{ success: boolean; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/stop`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async reconnectRemote(): Promise<{ success: boolean; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/reconnect`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async startRemotePairing(): Promise<RemotePairingCode> {
    const res = await fetch(`${API_BASE}/remote/pairing/start`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async cancelRemotePairing(): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/remote/pairing/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listRemoteUsers(): Promise<{ users: RemoteUser[] }> {
    const res = await fetch(`${API_BASE}/remote/users`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async addRemoteUser(telegram_id: number, username?: string): Promise<{ success: boolean; user: RemoteUser }> {
    const res = await fetch(`${API_BASE}/remote/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id, username: username || undefined }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async removeRemoteUser(telegram_id: number): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/remote/users/${telegram_id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listRemoteCommands(limit: number = 100): Promise<{ commands: RemoteCommand[]; count: number }> {
    const res = await fetch(`${API_BASE}/remote/commands?limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listRemoteNotifications(
    status?: RemoteQueueStatus,
    limit: number = 100
  ): Promise<{ notifications: RemoteNotification[]; count: number }> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    const res = await fetch(`${API_BASE}/remote/notifications?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async retryRemoteNotification(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/remote/notifications/${id}/retry`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async testRemoteNotification(): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/remote/notifications/test`, { method: 'POST' });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async listRemotePending(): Promise<{ actions: RemotePendingAction[]; count: number }> {
    const res = await fetch(`${API_BASE}/remote/pending`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async pauseRemote(reason?: string): Promise<{ success: boolean; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/pause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async resumeRemote(): Promise<{ success: boolean; status: RemoteStatus }> {
    const res = await fetch(`${API_BASE}/remote/resume`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async listRemoteTasks(limit: number = 50): Promise<{ tasks: RemoteTask[]; count: number }> {
    const res = await fetch(`${API_BASE}/remote/tasks?limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },
};
