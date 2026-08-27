import { createClient, SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

export function getSupabaseBrowserClient(): SupabaseClient | null {
  let url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey || anonKey === "your-anon-key") {
    return null;
  }

  if (typeof window !== "undefined") {
    try {
      const parsed = new URL(url);
      const pageHost = window.location.hostname;
      const isLoopback = (host: string) => host === "localhost" || host === "127.0.0.1";
      // Same reasoning as getApiBaseUrl (lib/api.ts): only rewrite when
      // either side is a bare loopback address that doesn't describe where
      // this browser actually is. Leaves Codespaces-style per-port
      // subdomains (both sides real, non-loopback hostnames) untouched.
      if (pageHost !== parsed.hostname && (isLoopback(pageHost) || isLoopback(parsed.hostname))) {
        parsed.hostname = pageHost;
        url = parsed.origin;
      }
    } catch {
      return null;
    }
  }

  if (!client) {
    client = createClient(url, anonKey);
  }
  return client;
}

export async function getAccessToken(): Promise<string> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) throw new Error("Supabase Authが設定されていません");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.access_token) {
    throw new Error("ログインセッションの有効期限が切れています");
  }
  return data.session.access_token;
}

export async function getAuthenticatedRepId(): Promise<number | null> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  const repId = data.session?.user.app_metadata?.rep_id;
  return typeof repId === "number" ? repId : null;
}

export async function signInSalesRep(repId: number, password: string): Promise<boolean> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) throw new Error("Supabase Authが設定されていません");
  const { data, error } = await supabase.auth.signInWithPassword({
    email: `rep${repId}@aiworkpartner.local`,
    password,
  });
  if (error || !data.user) return false;
  return data.user.app_metadata?.rep_id === repId;
}

export async function signOutSalesRep(): Promise<void> {
  const supabase = getSupabaseBrowserClient();
  if (supabase) await supabase.auth.signOut();
}
