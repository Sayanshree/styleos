import { redirect } from "next/navigation";

/**
 * Root route. Sends everyone to /app; middleware bounces anonymous traffic on to
 * /login from there, so the signed-in check lives in exactly one place.
 *
 * Onboarding (docs/06, screen 1) will land here eventually. Not in this pass.
 */
export default function Home(): never {
  redirect("/app");
}
