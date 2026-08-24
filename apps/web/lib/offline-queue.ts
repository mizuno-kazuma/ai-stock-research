/**
 * オフラインで入力した売買記録のキュー。
 * Background Sync があれば SW が送信し、iOS など未対応環境では画面を開いたときに送る。
 */

const STORAGE_KEY = "ai-stock.trade-queue.v1";

export interface QueuedTrade {
  queue_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

function readAll(): QueuedTrade[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as QueuedTrade[];
  } catch {
    return [];
  }
}

function writeAll(items: QueuedTrade[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export function enqueueTrade(payload: Record<string, unknown>): QueuedTrade {
  const item: QueuedTrade = {
    queue_id: `q_${Date.now()}`,
    payload,
    created_at: new Date().toISOString(),
  };
  writeAll([...readAll(), item]);
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    void navigator.serviceWorker.ready.then((reg) => {
      const syncReg = reg as ServiceWorkerRegistration & {
        sync?: { register: (tag: string) => Promise<void> };
      };
      return syncReg.sync?.register("sync-trades");
    });
  }
  return item;
}

export function listQueuedTrades(): QueuedTrade[] {
  return readAll();
}

export function removeQueuedTrade(queueId: string) {
  writeAll(readAll().filter((item) => item.queue_id !== queueId));
}

export async function flushTradeQueue<T>(
  send: (payload: T) => Promise<unknown>,
): Promise<{ sent: number; failed: number }> {
  const items = readAll();
  let sent = 0;
  let failed = 0;
  for (const item of items) {
    try {
      await send(item.payload as T);
      removeQueuedTrade(item.queue_id);
      sent += 1;
    } catch {
      failed += 1;
    }
  }
  return { sent, failed };
}
