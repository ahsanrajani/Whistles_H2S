"use client";

import {useEffect, useRef, useSyncExternalStore} from "react";
import {realtime, type RealtimeFrame, type RealtimeStatus} from "@/lib/realtime";

/**
 * Subscribe to one realtime topic for the life of the component. `topic` may be
 * null (nothing subscribed); the handler ref is kept current so a changing
 * closure does not churn the subscription.
 */
export function useRealtime(
  topic: string | null | undefined,
  handler: (frame: RealtimeFrame) => void,
): void {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });

  useEffect(() => {
    if (!topic || !realtime) return;
    return realtime.subscribe(topic, (frame) => ref.current(frame));
  }, [topic]);
}

/** F7.3 — the WebSocket connection state, for a drop banner. "idle" (nothing
 * subscribed yet) renders nothing; "reconnecting" is the only state worth
 * interrupting the user for. */
export function useRealtimeStatus(): RealtimeStatus {
  return useSyncExternalStore(
    (onChange) => (realtime ? realtime.onStatus(onChange) : () => {}),
    () => realtime?.getStatus() ?? "idle",
    () => "idle" as const,
  );
}
