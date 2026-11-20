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

export interface MemoryItem {
  id: string;
  category: 'fact' | 'project' | 'preference' | 'context';
  key: string;
  content: string;
  confidence: number;
  sensitivity: 'normal' | 'high';
  created_at: string;
  updated_at: string;
}

export interface TaskItem {
  id: string;
  conversation_id?: string;
  goal: string;
  status: 'created' | 'planning' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

export type AgentOrbState = 'idle' | 'thinking' | 'speaking' | 'executing' | 'error' | 'disconnected';

