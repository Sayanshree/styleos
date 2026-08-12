/**
 * TypeScript mirror of the engine's public shapes.
 *
 * Kept in step with engine/app/schemas.py and the "Key shapes" section of
 * docs/04-architecture-api.md.
 *
 * Note what is absent: no request type has a `user_id` field. Identity travels in
 * the JWT and nowhere else, so a caller cannot express one — the compiler rejects
 * it rather than the engine having to ignore it.
 */

/** The only feedback signals that exist. There is deliberately no `ignored`. */
export type FeedbackSignal = "accepted" | "liked" | "disliked";

export interface RequestContext {
  readonly temp_c?: number;
  readonly rain?: boolean;
}

export interface RecommendRequest {
  readonly occasion: string;
  readonly context: RequestContext;
}

export interface OutfitItem {
  readonly garment_id: string;
  readonly role: string;
}

export interface Outfit {
  readonly outfit_id: string;
  readonly rank: number;
  readonly confidence: number;
  readonly items: readonly OutfitItem[];
  readonly reasons: readonly string[];
  readonly weakest_factor: string | null;
}

export interface RecommendResponse {
  readonly recommendation_id: string;
  readonly latency_ms: number;
  /** True when the stylist fell back to templated reasons. Log it; the UI may ignore it. */
  readonly degraded: boolean;
  readonly outfits: readonly Outfit[];
}

export interface FeedbackRequest {
  readonly outfit_id: string;
  readonly signal: FeedbackSignal;
}

export interface FeedbackResponse {
  readonly descriptors: readonly string[];
}
