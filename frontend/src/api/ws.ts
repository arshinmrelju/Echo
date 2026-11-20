type MessageHandler = (data: any) => void;

class EchoWebSocket {
  private ws: WebSocket | null = null;
  private url: string = 'ws://127.0.0.1:8000/api/v1/ws';
  private listeners: Set<MessageHandler> = new Set();
  private isConnecting: boolean = false;
  private reconnectTimer: any = null;
  public isConnected: boolean = false;

  constructor() {
    this.connect();
  }

  public connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.isConnecting = true;
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.isConnecting = false;
        this.emit({ type: 'ws_connected' });
        // Start heartbeat
        this.startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.emit(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message', e);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.isConnecting = false;
        this.emit({ type: 'ws_disconnected' });
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        this.isConnected = false;
        this.emit({ type: 'ws_error', error: err });
      };
    } catch (e) {
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  private heartbeatInterval: any = null;
  private startHeartbeat() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, 15000);
  }

  private scheduleReconnect() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, 3000);
    }
  }

  public send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('Cannot send: WebSocket is not open');
    }
  }

  public subscribe(handler: MessageHandler): () => void {
    this.listeners.add(handler);
    return () => this.listeners.delete(handler);
  }

  private emit(data: any) {
    for (const listener of this.listeners) {
      try {
        listener(data);
      } catch (err) {
        console.error('Error in WS listener', err);
      }
    }
  }

  public sendChatMessage(content: string, conversation_id?: string) {
    this.send({
      type: 'chat_message',
      content,
      conversation_id,
    });
  }

  public stopGeneration(conversation_id?: string) {
    this.send({
      type: 'stop',
      conversation_id,
    });
  }
}

export const echoWs = new EchoWebSocket();

