import { getApiBaseUrl } from "@/lib/api";
import { StatusPanel } from "./status-panel";

async function fetchHealth() {
  const base = getApiBaseUrl();
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    if (!res.ok) {
      return { ok: false as const, body: `HTTP ${res.status}` };
    }
    const body = await res.json();
    const ok = typeof body === "object" && body !== null && body.status === "ok";
    return { ok, body };
  } catch (error) {
    return {
      ok: false as const,
      body: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

async function fetchAiPing() {
  const base = getApiBaseUrl();
  try {
    const res = await fetch(`${base}/api/ai/ping`, { cache: "no-store" });
    if (!res.ok) {
      return { ok: false as const, body: `HTTP ${res.status}` };
    }
    return { ok: true as const, body: await res.json() };
  } catch (error) {
    return {
      ok: false as const,
      body: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

export default async function HomePage() {
  const [health, aiPing] = await Promise.all([fetchHealth(), fetchAiPing()]);
  const supabaseConfigured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY !== "your-anon-key",
  );

  return (
    <main>
      <h1>AI Work Partner</h1>
      <p>
        FastAPI + Next.js + Supabase のローカル開発環境です。営業ダッシュボードは
        <a href="/dashboard">/dashboard</a>
        です。このページでは API の疎通と Supabase 設定を確認できます。
      </p>

      <StatusPanel
        title="FastAPI /health"
        ok={health.ok}
        body={JSON.stringify(health.body, null, 2)}
      />

      <StatusPanel
        title="AI placeholder /api/ai/ping"
        ok={aiPing.ok}
        body={JSON.stringify(aiPing.body, null, 2)}
      />

      <section className="panel">
        <h2>Supabase client</h2>
        <p className={`status ${supabaseConfigured ? "ok" : "warn"}`}>
          {supabaseConfigured
            ? "NEXT_PUBLIC_SUPABASE_* is set. Browser client helper is ready (see lib/supabase.ts)."
            : "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in .env from `supabase status`."}
        </p>
      </section>

      <p>
        API docs:{" "}
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          http://localhost:8000/docs
        </a>
      </p>
    </main>
  );
}
