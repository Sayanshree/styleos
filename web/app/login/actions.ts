"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

/**
 * Auth as Server Actions rather than browser-side calls, so session cookies are
 * written server-side on the same response that performs the sign-in.
 */

export interface AuthState {
  readonly error?: string;
  readonly notice?: string;
}

function readCredentials(formData: FormData): { email: string; password: string } {
  return {
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  };
}

/**
 * Single entry point for both buttons on the login form; the submitter sets
 * `intent`. One action keeps `useActionState` able to report errors for either.
 */
export async function authenticate(
  _previous: AuthState,
  formData: FormData,
): Promise<AuthState> {
  const intent = String(formData.get("intent") ?? "signin");
  const { email, password } = readCredentials(formData);

  if (!email || !password) {
    return { error: "Email and password are both required." };
  }

  const supabase = await createClient();

  if (intent === "signup") {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) {
      return { error: error.message };
    }
    // With email confirmation enabled — the Supabase default — sign-up returns a
    // user but no session, and nothing happens until the emailed link is clicked.
    if (!data.session) {
      return {
        notice: "Account created. Check your email for the confirmation link, then sign in.",
      };
    }
  } else {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      return { error: error.message };
    }
  }

  revalidatePath("/", "layout");
  redirect("/app");
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  revalidatePath("/", "layout");
  redirect("/login");
}
