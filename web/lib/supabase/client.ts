"use client";

import { createBrowserClient } from "@supabase/ssr";

import { publicSupabaseConfig } from "./config";

/** Supabase client for use in Client Components. Anon key only. */
export function createClient() {
  const { url, anonKey } = publicSupabaseConfig();
  return createBrowserClient(url, anonKey);
}
