// Thin reverse-proxy from the browser to the FastAPI feedback endpoint.
// Mirrors the api/chat/route.ts pattern — keeps the FastAPI URL
// server-side and gives us a place to add auth later.
//
// Wire format matches POST /api/feedback in api/main.py:
//   { message_id: string, rating: "up" | "down", comment?: string | null }
// Response is { status: "ok" } on success or a JSON error body on
// 4xx/5xx that the client surfaces in the FeedbackBar's inline error.

import { apiBaseUrl } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const upstream = await fetch(`${apiBaseUrl}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
    cache: "no-store",
  });

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
