/** Small date-grid math for the F4 content calendar. No date library needed. */

export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Monday-first 6-week (42 day) grid covering the month containing `anchor`. */
export function monthGrid(anchor: Date): Date[] {
  const first = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 1));
  const weekday = (first.getUTCDay() + 6) % 7; // 0 = Monday
  const start = new Date(first);
  start.setUTCDate(first.getUTCDate() - weekday);
  return Array.from({length: 42}, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    return d;
  });
}

/** Monday-first 7-day grid covering the week containing `anchor`. */
export function weekGrid(anchor: Date): Date[] {
  const weekday = (anchor.getUTCDay() + 6) % 7;
  const start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), anchor.getUTCDate() - weekday));
  return Array.from({length: 7}, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    return d;
  });
}

export function addMonths(d: Date, n: number): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1));
}

export function addWeeks(d: Date, n: number): Date {
  const out = new Date(d);
  out.setUTCDate(out.getUTCDate() + n * 7);
  return out;
}

export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
