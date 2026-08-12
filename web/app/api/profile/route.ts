import { notImplemented } from "@/lib/http";

/**
 * Self-reported body profile. A scoring input, never a hard filter — body data is
 * an aid, not a rule.
 */
export function GET(): Response {
  return notImplemented("GET /api/profile");
}

export function PUT(): Response {
  return notImplemented("PUT /api/profile");
}
