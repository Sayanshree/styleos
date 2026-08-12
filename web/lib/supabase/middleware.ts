import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { publicSupabaseConfig } from "./config";

/** Route prefixes that require a signed-in user. */
const PROTECTED_PREFIXES = ["/app"] as const;

/**
 * Refresh the Supabase session and guard protected routes.
 *
 * Two jobs, both of which have to happen here:
 *
 * 1. Access tokens expire. Server Components cannot write cookies, so without a
 *    middleware refresh a user gets silently signed out when their token lapses.
 * 2. Redirect anonymous traffic away from protected routes before any page code
 *    runs.
 *
 * `supabase.auth.getUser()` is used rather than `getSession()` deliberately: it
 * revalidates the token with Supabase, whereas `getSession()` trusts whatever is
 * in the cookie.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let supabaseResponse = NextResponse.next({ request });
  const { url, anonKey } = publicSupabaseConfig();

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        supabaseResponse = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          supabaseResponse.cookies.set(name, value, options);
        }
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );

  if (!user && isProtected) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    redirectUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(redirectUrl);
  }

  return supabaseResponse;
}
