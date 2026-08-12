import "server-only";

import type { FeedbackRequest, RecommendRequest } from "./engine-types";

/**
 * The single code path that talks to the FastAPI engine.
 *
 * `import "server-only"` at the top is load-bearing: if any Client Component ever
 * imports this module, the build fails rather than shipping SERVICE_SHARED_TOKEN
 * to a browser. That is the guarantee, not a convention.
 *
 * Two credentials go on every engine request, per docs/04-architecture-api.md:
 *
 *   Authorization: Bearer <supabase_jwt>   the end user's identity
 *   X-Service-Token: <shared_secret>       proves the caller is this BFF
 *
 * `user_id` is never sent. It is not a parameter here and appears in no request
 * type, so there is no way to add one without changing this file on purpose.
 */

/** Engine paths this BFF is allowed to call. */
export type EnginePath = "/recommend" | "/feedback" | "/metrics";

const ENGINE_TIMEOUT_MS = 15_000;

interface ServerEnv {
  readonly engineUrl: string;
  readonly serviceToken: string;
}

function serverEnv(): ServerEnv {
  const engineUrl = process.env.ENGINE_URL;
  const serviceToken = process.env.SERVICE_SHARED_TOKEN;
  if (!engineUrl || !serviceToken) {
    throw new Error(
      "Missing ENGINE_URL and/or SERVICE_SHARED_TOKEN. Copy web/.env.local.example " +
        "to web/.env.local and fill it in. SERVICE_SHARED_TOKEN must match the engine's.",
    );
  }
  return { engineUrl, serviceToken };
}

/** A fully-formed engine request, credentials attached, not yet dispatched. */
export interface EngineCall<TBody> {
  readonly url: string;
  readonly method: "GET" | "POST";
  readonly headers: Readonly<Record<string, string>>;
  readonly body: TBody | undefined;
}

export class EngineError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "EngineError";
  }
}

/**
 * Build an engine request with both credentials attached.
 *
 * Separated from dispatch so a route can construct — and have the compiler check —
 * the exact call it will make before the call itself is implemented.
 */
export function buildEngineCall<TBody>(
  path: EnginePath,
  accessToken: string,
  body?: TBody,
): EngineCall<TBody> {
  const { engineUrl, serviceToken } = serverEnv();
  return {
    url: new URL(path, engineUrl).toString(),
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      "X-Service-Token": serviceToken,
    },
    body,
  };
}

/** Dispatch a built call and parse the engine's JSON response. */
export async function callEngine<TRes, TBody = undefined>(
  call: EngineCall<TBody>,
): Promise<TRes> {
  const response = await fetch(call.url, {
    method: call.method,
    headers: call.headers,
    body: call.body === undefined ? undefined : JSON.stringify(call.body),
    // The engine is on the critical path of the one moment the product exists to
    // deliver. An unbounded fetch here is a hung browser tab.
    signal: AbortSignal.timeout(ENGINE_TIMEOUT_MS),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new EngineError(
      `engine responded ${response.status} for ${call.method} ${call.url}`,
      response.status,
    );
  }

  return (await response.json()) as TRes;
}

/** Typed convenience wrappers, so route handlers cannot mistype a path or body. */
export function buildRecommendCall(
  accessToken: string,
  body: RecommendRequest,
): EngineCall<RecommendRequest> {
  return buildEngineCall<RecommendRequest>("/recommend", accessToken, body);
}

export function buildFeedbackCall(
  accessToken: string,
  body: FeedbackRequest,
): EngineCall<FeedbackRequest> {
  return buildEngineCall<FeedbackRequest>("/feedback", accessToken, body);
}
