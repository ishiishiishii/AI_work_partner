"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

// 社員ID(EMP001など)と実際のログイン用メールアドレスの対応。
// 社員番号を管理するAPIがまだ無いため、rep_id から機械的に組み立てている。
function employeeIdToLoginEmail(employeeId: string): string | null {
  const match = /^EMP(\d{3,})$/i.exec(employeeId.trim());
  if (!match) return null;
  return `rep${Number(match[1])}@aiworkpartner.local`;
}

export default function LoginPage() {
  const router = useRouter();
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleContinue(event: React.FormEvent) {
    event.preventDefault();
    if (!employeeIdToLoginEmail(employeeId)) {
      setError("社員IDの形式が正しくありません(例: EMP001)");
      return;
    }
    setError(null);
    setShowPassword(true);
  }

  function handleBack() {
    setShowPassword(false);
    setPassword("");
    setError(null);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const email = employeeIdToLoginEmail(employeeId);
    const supabase = getSupabaseBrowserClient();
    if (!supabase || !email) {
      setError("ログインに失敗しました");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setIsSubmitting(false);

    if (signInError) {
      setError("社員IDまたはパスワードが正しくありません");
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
          <span>社員ID</span>
          <input
            type="text"
            value={employeeId}
            onChange={(event) => setEmployeeId(event.target.value)}
            placeholder="EMP001"
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
          <>
            {error && <p className="new-customer-form__error">{error}</p>}
            <button type="submit" className="goal-card__save">
              次へ
            </button>
          </>
        )}
      </form>
    </main>
  );
}
