import { notImplemented } from "@/lib/http";

/**
 * Style DNA descriptors and weights, for display.
 *
 * Read-only from the web side: the weights are written by the engine as feedback
 * arrives, never by the browser.
 */
export function GET(): Response {
  return notImplemented("GET /api/style-dna");
}
