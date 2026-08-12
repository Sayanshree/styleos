import { notImplemented } from "@/lib/http";

/**
 * Seeds the one-click sample closet for the public demo.
 *
 * When implemented this must also seed `recommendation` rows with sensible
 * `seq_no` values and a feedback history, not just garments — otherwise the
 * before/after learning improvement has nothing to show on first load.
 */
export function POST(): Response {
  return notImplemented("POST /api/demo/load-sample");
}
