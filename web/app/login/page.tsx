"use client";

import { useActionState } from "react";

import { authenticate, type AuthState } from "./actions";

const INITIAL: AuthState = {};

/**
 * The only real UI in this scaffold. Deliberately unstyled beyond the minimum —
 * the design budget in docs/06 goes to Home/Today and Request -> Recommendation,
 * and dressing this page up would only make it look finished when it is not.
 */
export default function LoginPage() {
  const [state, formAction, pending] = useActionState(authenticate, INITIAL);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">StyleOS</h1>
        <p className="mt-1 text-sm opacity-70">Sign in, or create an account.</p>
      </header>

      <form action={formAction} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span>Email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            className="rounded border border-current/20 bg-transparent px-3 py-2 text-base"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span>Password</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            minLength={6}
            className="rounded border border-current/20 bg-transparent px-3 py-2 text-base"
          />
        </label>

        {state.error ? (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {state.error}
          </p>
        ) : null}

        {state.notice ? (
          <p role="status" className="text-sm text-green-700 dark:text-green-400">
            {state.notice}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button
            type="submit"
            name="intent"
            value="signin"
            disabled={pending}
            className="flex-1 rounded bg-foreground px-4 py-2 text-background disabled:opacity-50"
          >
            {pending ? "Working…" : "Sign in"}
          </button>
          <button
            type="submit"
            name="intent"
            value="signup"
            disabled={pending}
            className="flex-1 rounded border border-current/30 px-4 py-2 disabled:opacity-50"
          >
            Sign up
          </button>
        </div>
      </form>
    </main>
  );
}
