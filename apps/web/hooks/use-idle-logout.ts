"use client";

import {useEffect, useRef} from "react";

// Hamza, 2026-09-11: "logout after 20 mins of inactivity". This is client-
// observed inactivity specifically -- no real mouse/keyboard/touch event for
// the full window -- not merely "no API call", so a tab left open with
// nobody at it times out even while its own background polling (realtime
// reconnects, React Query refetches) would otherwise keep the server-side
// session's last_seen fresh forever (see apps/api/websession/idle.py, the
// actual security boundary this is UX for). The server enforces the same
// 20-minute idle timeout independently; this fires the same logout
// proactively instead of waiting for the next API call to 401.
const IDLE_TIMEOUT_MS = 20 * 60 * 1000;
// mousemove/scroll fire far more often than a 20-minute timer needs to know
// about -- coalesce activity bookkeeping to at most once every few seconds.
const ACTIVITY_THROTTLE_MS = 5_000;
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "wheel", "touchstart", "scroll"] as const;

export function useIdleLogout(onIdle: () => void) {
  const onIdleRef = useRef(onIdle);
  useEffect(() => {
    onIdleRef.current = onIdle;
  });

  useEffect(() => {
    let lastActivity = Date.now();
    let fired = false;
    let lastBookkeeping = lastActivity;

    // A real setTimeout for the common case (tab stays foregrounded and
    // idle) fires right on time. It is NOT trusted alone for the "laptop
    // slept / tab was backgrounded for hours" case -- a suspended tab's
    // timers can run late or get throttled, silently extending the
    // effective idle window -- so `check()` re-derives from wall-clock time
    // on every real activity event and on visibilitychange, and fires
    // immediately if the deadline already passed rather than waiting for a
    // timer that may never come.
    let timer: ReturnType<typeof setTimeout>;

    function fire() {
      if (fired) return;
      fired = true;
      clearTimeout(timer);
      onIdleRef.current();
    }

    function scheduleFrom(now: number) {
      clearTimeout(timer);
      timer = setTimeout(check, Math.max(0, IDLE_TIMEOUT_MS - (Date.now() - now)));
    }

    function check() {
      if (Date.now() - lastActivity >= IDLE_TIMEOUT_MS) fire();
      else scheduleFrom(lastActivity);
    }

    function onActivity() {
      if (fired) return;
      const now = Date.now();
      if (now - lastBookkeeping < ACTIVITY_THROTTLE_MS) return;
      lastBookkeeping = now;
      lastActivity = now;
      scheduleFrom(now);
    }

    scheduleFrom(lastActivity);
    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, onActivity, {passive: true}));
    document.addEventListener("visibilitychange", check);

    return () => {
      clearTimeout(timer);
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, onActivity));
      document.removeEventListener("visibilitychange", check);
    };
  }, []);
}
