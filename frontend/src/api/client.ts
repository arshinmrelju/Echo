import {
  ActionLogItem,
  ActiveWindowInfo,
  AppSettings,
  ApprovalRequest,
  Conversation,
  MemoryItem,
  SystemMetrics,
  SystemStatus,
  TaskItem,
  ToolItem,
} from '../types';

const API_BASE = 'http://127.0.0.1:8000/api/v1';

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

  // Memory
  async listMemories(category?: string, query?: string): Promise<MemoryItem[]> {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (query) params.append('query', query);
    const res = await fetch(`${API_BASE}/memory?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async createMemory(item: { category: string; key: string; content: string }): Promise<MemoryItem> {
    const res = await fetch(`${API_BASE}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  async deleteMemory(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/memory/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
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
};
