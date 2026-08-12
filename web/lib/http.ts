import { NextResponse } from "next/server";

/**
 * Shared responses for the BFF routes.
 *
 * `notImplemented` is what every unbuilt route returns for now. It is a distinct
 * status from 404 on purpose: the route exists and its contract is settled, only
 * the body of the work is missing.
 */
export function notImplemented(what: string): NextResponse {
  return NextResponse.json(
    { error: "not_implemented", detail: `${what} is not implemented yet` },
    { status: 501 },
  );
}

export function unauthorized(detail = "not signed in"): NextResponse {
  return NextResponse.json({ error: "unauthorized", detail }, { status: 401 });
}

export function badRequest(detail: string): NextResponse {
  return NextResponse.json({ error: "bad_request", detail }, { status: 400 });
}

/**
 * A garment that appears in a past outfit cannot be deleted — `outfit_item.garment_id`
 * is `on delete restrict` so recommendation history survives a wardrobe edit.
 * That is a conflict, never a 500. See docs/04-architecture-api.md.
 */
export function conflict(detail: string): NextResponse {
  return NextResponse.json({ error: "conflict", detail }, { status: 409 });
}
