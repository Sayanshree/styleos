/**
 * Public Supabase configuration.
 *
 * Only the anon / publishable key is ever used in `web/`. That key is safe in a
 * browser because row level security is what actually protects the data behind it
 * — see supabase/migrations/0002_rls_policies.sql.
 *
 * The Supabase service-role key is deliberately absent from this entire package.
 * It bypasses RLS and belongs only to the engine.
 *
 * The two values are read as literal `process.env.NEXT_PUBLIC_*` expressions on
 * purpose: Next.js inlines public env vars into the client bundle only when it can
 * see the literal property access. A dynamic lookup like `process.env[name]` would
 * silently become `undefined` in the browser.
 */

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export interface PublicSupabaseConfig {
  readonly url: string;
  readonly anonKey: string;
}

export function publicSupabaseConfig(): PublicSupabaseConfig {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL and/or NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
        "Copy web/.env.local.example to web/.env.local and fill it in, then restart the dev server.",
    );
  }
  return { url: SUPABASE_URL, anonKey: SUPABASE_ANON_KEY };
}
