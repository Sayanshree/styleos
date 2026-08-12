import { notImplemented } from "@/lib/http";

/**
 * Wardrobe collection. Flow 2 (wardrobe maintenance) lives here.
 *
 * POST will do CV tagging and background removal server-side, then save the
 * garment with `tag_source='ai'`. Adding a garment updates state only — it must
 * never trigger a recommendation.
 */
export function GET(): Response {
  return notImplemented("GET /api/garments");
}

export function POST(): Response {
  return notImplemented("POST /api/garments");
}
