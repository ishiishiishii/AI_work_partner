const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL ||
  process.env.API_PUBLIC_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  try {
    const upstream = await fetch(API_INTERNAL_URL + "/api/ai/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: request.headers.get("authorization") || "",
      },
      body: await request.text(),
      cache: "no-store",
    });

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    console.error("Failed to proxy AI chat request", error);
    return Response.json(
      { detail: "AIサーバーに接続できませんでした。" },
      { status: 502 },
    );
  }
}
