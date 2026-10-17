import {cookies} from "next/headers";
import type {Auth} from "./types";

export async function getMe(): Promise<Auth | null> {
  const cookieStore = await cookies();
  const cookie = cookieStore.toString();
  if (!cookie) return null;
  const origin = process.env.GURU_API_ORIGIN ?? "http://127.0.0.1:5000";
  try {
    const response = await fetch(`${origin}/api/v1/auth/me`, {
      headers: {cookie}, cache: "no-store",
    });
    if (!response.ok) return null;
    const data = await response.json() as Auth;
    return data.user ? data : null;
  } catch { return null; }
}
