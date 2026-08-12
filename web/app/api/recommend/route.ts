import type { NextRequest } from "next/server";

import { buildRecommendCall } from "@/lib/engine";
import type { RecommendRequest, RequestContext } from "@/lib/engine-types";
import { badRequest, notImplemented, unauthorized } from "@/lib/http";
import { createClient } from "@/lib/supabase/server";

/**
 * Thin proxy to the engine's POST /recommend.
 *
 * Everything here is real except the final dispatch: the session is read, the
 * credentials are assembled, and the typed body is constructed and type-checked.
 * Only `callEngine(call)` is withheld — see the TODO at the bottom.
 *
 * The engine URL and the shared token never reach the browser. `lib/engine` is
 * `server-only`, so importing it from a Client Component fails the build.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    // Rejected here, before the engine is contacted at all.
    return unauthorized("sign in before requesting a recommendation");
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

  const { occasion, context } = payload as {
    occasion?: unknown;
    context?: unknown;
  };

  if (typeof occasion !== "string" || occasion.trim() === "") {
    return badRequest("`occasion` is required");
  }

  // Context is gathered server-side by this BFF — weather lookup is the web
  // app's job, not the engine's. On a lookup failure send a neutral context and
  // let the engine drop weatherFit and renormalise; never fail the request.
  const requestContext: RequestContext =
    typeof context === "object" && context !== null ? (context as RequestContext) : {};

  // Note the absence of user_id. RecommendRequest has no such field, so identity
  // can only travel in the bearer token below.
  const body: RecommendRequest = { occasion, context: requestContext };

  const call = buildRecommendCall(session.access_token, body);
  void call;

  // TODO: replace the line below with
  //   return NextResponse.json(await callEngine<RecommendResponse, RecommendRequest>(call));
  // and map EngineError.status onto a response the wardrobe UI can act on.
  return notImplemented("POST /api/recommend");
}
