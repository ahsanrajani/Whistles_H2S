"use client";

/**
 * F7.3 — live status banner for the care console and supervisor console.
 * Hamza, 2026-09-11: "disable this bar, should never show" -- cases/queues/
 * presence all still work while the push channel is down (every mutation
 * round-trips the API regardless), so a disconnect here was never more than
 * a heads-up, and it read as an alarming/flappy error. Off unconditionally;
 * useRealtimeStatus (hooks/use-realtime.ts) stays available if a quieter
 * version of this is wanted later.
 */
export function RealtimeBanner() {
  return null;
}
