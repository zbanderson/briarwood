import { apiBaseUrl } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const upstream = await fetch(
    `${apiBaseUrl}/api/street-view?${new URL(request.url).searchParams.toString()}`,
    {
      method: "GET",
    },
  );

  if (!upstream.ok) {
    return new Response(await upstream.text(), {
      status: upstream.status || 502,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "text/plain; charset=utf-8",
      },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "image/jpeg",
      "Cache-Control": upstream.headers.get("Cache-Control") ?? "public, max-age=86400",
    },
  });
}
