/**
 * SSE 封装：优先 EventSource，失败/无接口时回退轮询。
 */
export interface SseHandle {
  close: () => void;
}

export function openSse(
  url: string,
  onMessage: (data: unknown) => void,
  options: {
    /** 连接失败或 error 时回退 */
    onFallback?: () => void;
    /** 返回 true 时自动关闭 */
    shouldStop?: (data: unknown) => boolean;
  } = {},
): SseHandle {
  let closed = false;
  let es: EventSource | null = null;

  const stop = () => {
    if (closed) return;
    closed = true;
    es?.close();
    es = null;
  };

  if (typeof EventSource === "undefined") {
    options.onFallback?.();
    return { close: stop };
  }

  try {
    es = new EventSource(url);
    es.onmessage = (ev) => {
      if (closed) return;
      try {
        const data = JSON.parse(ev.data);
        onMessage(data);
        if (options.shouldStop?.(data)) stop();
      } catch {
        /* ignore parse error */
      }
    };
    es.onerror = () => {
      stop();
      options.onFallback?.();
    };
  } catch {
    options.onFallback?.();
  }

  return { close: stop };
}

/** 轮询回退 */
export function pollStatus(
  fetchStatus: () => Promise<unknown>,
  onMessage: (data: unknown) => void,
  options: {
    intervalMs?: number;
    maxTicks?: number;
    shouldStop?: (data: unknown) => boolean;
  } = {},
): SseHandle {
  const intervalMs = options.intervalMs ?? 1500;
  const maxTicks = options.maxTicks ?? 120;
  let ticks = 0;
  let stopped = false;

  const timer = setInterval(async () => {
    if (stopped) return;
    ticks += 1;
    if (ticks > maxTicks) {
      stopped = true;
      clearInterval(timer);
      return;
    }
    try {
      const data = await fetchStatus();
      onMessage(data);
      if (options.shouldStop?.(data)) {
        stopped = true;
        clearInterval(timer);
      }
    } catch {
      stopped = true;
      clearInterval(timer);
    }
  }, intervalMs);

  return {
    close: () => {
      stopped = true;
      clearInterval(timer);
    },
  };
}
