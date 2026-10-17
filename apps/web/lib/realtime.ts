/**
 * Realtime transport (F0.4). One WebSocket per tab to `/api/v1/ws`, shared by
 * every `useRealtime` subscription. Reconnects with exponential backoff +
 * jitter and re-subscribes its live topics on reopen, so it rides out a server
 * restart. The SSE job console is untouched.
 *
 * Topics: `case:{id}`, `queue:{workspaceId}`, `presence:{workspaceId}`.
 */
export type RealtimeFrame = {topic: string; ts: number; data: unknown};
type Handler = (frame: RealtimeFrame) => void;
// F7.3 — connection state the console's drop banner reads. "reconnecting"
// covers both the backoff wait and the socket handshake; a fresh page with no
// live topic subscribed yet is "idle", not a dropped connection.
export type RealtimeStatus = "idle" | "connecting" | "open" | "reconnecting";
type StatusHandler = (status: RealtimeStatus) => void;

const MAX_BACKOFF = 15_000;
const PING_MS = 25_000;

class RealtimeClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private statusHandlers = new Set<StatusHandler>();
  private status: RealtimeStatus = "idle";
  private backoff = 1_000;
  private stopped = false;
  private pingTimer: number | undefined;
  private reconnectTimer: number | undefined;

  private setStatus(next: RealtimeStatus): void {
    if (this.status === next) return;
    this.status = next;
    for (const handler of [...this.statusHandlers]) { try { handler(next); } catch { /* ignore */ } }
  }

  getStatus(): RealtimeStatus {
    return this.status;
  }

  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  private topics(): string[] {
    return [...this.handlers.keys()];
  }

  private send(obj: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  private connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    if (this.handlers.size === 0) return;
    this.stopped = false;
    this.setStatus(this.backoff > 1_000 ? "reconnecting" : "connecting");
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${proto}//${window.location.host}/api/v1/ws`);
    this.ws = socket;

    socket.onopen = () => {
      this.backoff = 1_000;
      this.setStatus("open");
      this.send({type: "subscribe", topics: this.topics()});
      window.clearInterval(this.pingTimer);
      this.pingTimer = window.setInterval(() => this.send({type: "ping"}), PING_MS);
    };
    socket.onmessage = (event) => {
      let msg: RealtimeFrame & {type?: string};
      try {
        msg = JSON.parse(event.data as string);
      } catch {
        return;
      }
      if (!msg || typeof msg.topic !== "string") return; // ready / pong frames
      const set = this.handlers.get(msg.topic);
      if (set) for (const handler of [...set]) { try { handler(msg); } catch { /* ignore */ } }
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      window.clearInterval(this.pingTimer);
      this.ws = null;
      if (this.stopped || this.handlers.size === 0) {
        this.setStatus("idle");
        return;
      }
      this.setStatus("reconnecting");
      const wait = Math.min(this.backoff, MAX_BACKOFF) + Math.random() * 500;
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF);
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = window.setTimeout(() => this.connect(), wait);
    };
  }

  subscribe(topic: string, handler: Handler): () => void {
    let set = this.handlers.get(topic);
    if (!set) {
      set = new Set();
      this.handlers.set(topic, set);
    }
    set.add(handler);
    this.connect();
    this.send({type: "subscribe", topics: this.topics()});

    return () => {
      const current = this.handlers.get(topic);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) this.handlers.delete(topic);
      this.send({type: "subscribe", topics: this.topics()});
      if (this.handlers.size === 0) {
        this.stopped = true;
        window.clearTimeout(this.reconnectTimer);
        this.ws?.close();
      }
    };
  }
}

export const realtime: RealtimeClient | null =
  typeof window === "undefined" ? null : new RealtimeClient();
