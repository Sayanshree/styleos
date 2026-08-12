import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { publicSupabaseConfig } from "./config";

/**
 * Supabase client for Server Components, Server Actions and Route Handlers.
 *
 * Anon key only — the same key the browser uses, so RLS still applies to every
 * read and write made through it. Server-side use does not imply elevated access,
 * and that is intentional: the only component with RLS-bypassing credentials is
 * the FastAPI engine.
 */
export async function createClient() {
  const cookieStore = await cookies();
  const { url, anonKey } = publicSupabaseConfig();

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Server Components cannot set cookies. This is safe to swallow because
          // middleware.ts refreshes the session on every request, so the cookie is
          // written there instead.
        }
      },
    },
  });
}
