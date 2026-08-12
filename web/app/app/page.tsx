import { redirect } from "next/navigation";

import { signOut } from "@/app/login/actions";
import { createClient } from "@/lib/supabase/server";

/**
 * Protected placeholder. Everything in docs/06 — Home/Today, Wardrobe, Request ->
 * Recommendation, Style DNA — lands under here later. None of it is in scope yet.
 *
 * The auth check is repeated here even though middleware already redirects. That
 * is not redundancy worth removing: middleware can be misconfigured by a matcher
 * edit, and a page that renders user data should verify its own preconditions.
 */
export default async function AppPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Signed in</h1>
        <p className="mt-1 text-sm opacity-70">{user.email}</p>
      </div>

      <p className="text-sm opacity-70">
        Placeholder. No wardrobe, recommendation, feedback or Style DNA screens exist yet.
      </p>

      <form action={signOut}>
        <button
          type="submit"
          className="rounded border border-current/30 px-4 py-2 text-sm"
        >
          Sign out
        </button>
      </form>
    </main>
  );
}
