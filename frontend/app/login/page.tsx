"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleContinue(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    setShowPassword(true);
  }

  function handleBack() {
    setShowPassword(false);
    setPassword("");
    setError(null);
  }

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

      <form
        className="panel login-form"
        onSubmit={showPassword ? handleSubmit : handleContinue}
      >
        <label className="goal-card__field">
          <span>ID(メールアドレス)</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="rep1@aiworkpartner.local"
            disabled={showPassword}
            required
          />
        </label>

        {showPassword ? (
          <>
            <label className="goal-card__field">
              <span>パスワード</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoFocus
                required
              />
            </label>

            {error && <p className="new-customer-form__error">{error}</p>}

            <div className="login-form__actions">
              <button type="button" className="goal-card__cancel" onClick={handleBack}>
                戻る
              </button>
              <button type="submit" className="goal-card__save" disabled={isSubmitting}>
                {isSubmitting ? "ログイン中..." : "ログイン"}
              </button>
            </div>
          </>
        ) : (
          <button type="submit" className="goal-card__save">
            次へ
          </button>
        )}
      </form>
    </main>
  );
}
