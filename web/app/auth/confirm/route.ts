import type { EmailOtpType } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/**
 * Handles the link Supabase emails on sign-up.
 *
 * Without this route, a project with email confirmation enabled (the default)
 * sends users to a link nothing answers, and the account can never be activated.
 */
export async function GET(request: NextRequest): Promise<never> {
  const { searchParams } = request.nextUrl;
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = searchParams.get("next") ?? "/app";

  if (!tokenHash || !type) {
    redirect("/login?error=invalid_confirmation_link");
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });

  if (error) {
    redirect(`/login?error=${encodeURIComponent(error.message)}`);
  }

  redirect(next);
}
