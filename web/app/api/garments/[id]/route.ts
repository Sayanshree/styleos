import { notImplemented } from "@/lib/http";

interface RouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

/**
 * PATCH corrects AI tags and must set `tag_source='user_corrected'`, which is what
 * makes the CV correction rate measurable.
 */
export async function PATCH(_request: Request, context: RouteContext): Promise<Response> {
  const { id } = await context.params;
  return notImplemented(`PATCH /api/garments/${id}`);
}

/**
 * DELETE can legitimately fail. `outfit_item.garment_id` is `on delete restrict`,
 * so a garment that has appeared in any past outfit cannot be removed —
 * recommendation history must not be rewritten by a wardrobe edit.
 *
 * When implemented: return 409 via `conflict()` on the foreign-key rejection and
 * surface it in the wardrobe UI. Never a 500.
 */
export async function DELETE(_request: Request, context: RouteContext): Promise<Response> {
  const { id } = await context.params;
  return notImplemented(`DELETE /api/garments/${id}`);
}
