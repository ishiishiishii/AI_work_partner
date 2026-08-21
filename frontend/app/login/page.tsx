"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setError("Supabaseの設定が見つかりません。.envを確認してください。");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setIsSubmitting(false);

    if (signInError) {
      setError("メールアドレスまたはパスワードが正しくありません");
      return;
    }

    router.replace("/dashboard");
  }

  return (
    <main className="login-page">
      <h1>ログイン</h1>
      <p>担当者アカウントでログインしてください。</p>

      <form className="panel login-form" onSubmit={handleSubmit}>
        <label className="goal-card__field">
          <span>メールアドレス</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="rep1@aiworkpartner.local"
            required
          />
        </label>
        <label className="goal-card__field">
          <span>パスワード</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>

        {error && <p className="new-customer-form__error">{error}</p>}

        <button type="submit" className="goal-card__save" disabled={isSubmitting}>
          {isSubmitting ? "ログイン中..." : "ログイン"}
        </button>
      </form>
    </main>
  );
}
