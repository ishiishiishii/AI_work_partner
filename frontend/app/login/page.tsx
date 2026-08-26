"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { employeeIdToRepId } from "@/lib/demoAuth";
import { useRep } from "@/lib/repContext";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useRep();
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleContinue(event: React.FormEvent) {
    event.preventDefault();
    if (employeeIdToRepId(employeeId) === null) {
      setError("社員IDはEMP001〜EMP050の形式で入力してください");
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
    setIsSubmitting(true);
    setError(null);

    const repId = employeeIdToRepId(employeeId);
    if (repId === null) {
      setIsSubmitting(false);
      setError("社員IDまたはパスワードが正しくありません");
      return;
    }

    try {
      if (!(await signIn(repId, password))) {
        setError("社員IDまたはパスワードが正しくありません");
        return;
      }
      router.replace("/dashboard");
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "ログインに失敗しました");
    } finally {
      setIsSubmitting(false);
    }
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
