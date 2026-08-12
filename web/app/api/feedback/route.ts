import type { NextRequest } from "next/server";

import { buildFeedbackCall } from "@/lib/engine";
import type { FeedbackRequest, FeedbackSignal } from "@/lib/engine-types";
import { badRequest, notImplemented, unauthorized } from "@/lib/http";
import { createClient } from "@/lib/supabase/server";

const VALID_SIGNALS: readonly FeedbackSignal[] = ["accepted", "liked", "disliked"];

function isSignal(value: unknown): value is FeedbackSignal {
  return typeof value === "string" && (VALID_SIGNALS as readonly string[]).includes(value);
}

/**
 * Thin proxy to the engine's POST /feedback.
 *
 * As with /api/recommend, everything runs except the dispatch itself.
 *
 * `ignored` is rejected here as well as in the engine and the database. An
 * ignored recommendation is one with no feedback events, derived at query time —
 * writing one would need a timer to decide when "no answer yet" becomes "no".
 */
export async function POST(request: NextRequest): Promise<Response> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return unauthorized("sign in before submitting feedback");
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return badRequest("body must be JSON");
  }

  if (typeof payload !== "object" || payload === null) {
    return badRequest("body must be a JSON object");
  }

  const { outfit_id: outfitId, signal } = payload as {
    outfit_id?: unknown;
    signal?: unknown;
  };

  if (typeof outfitId !== "string" || outfitId === "") {
    return badRequest("`outfit_id` is required");
  }

  if (!isSignal(signal)) {
    return badRequest("`signal` must be one of accepted, liked, disliked");
  }

  // No user_id: ownership of the outfit is resolved by the engine from the token.
  const body: FeedbackRequest = { outfit_id: outfitId, signal };

  const call = buildFeedbackCall(session.access_token, body);
  void call;

  // TODO: replace the line below with
  //   return NextResponse.json(await callEngine<FeedbackResponse, FeedbackRequest>(call));
  // The engine returns the updated Style DNA descriptors so the UI can reflect
  // learning immediately.
  return notImplemented("POST /api/feedback");
}
