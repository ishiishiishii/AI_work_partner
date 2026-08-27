import type { ReplanInfo } from "@/types";

type ReplanBannerProps = {
  info: ReplanInfo;
};

export function ReplanBanner({ info }: ReplanBannerProps) {
  const badge =
    info.outcome === "lost"
      ? "失注を受けてAIが自動再計画しました"
      : info.outcome === "won"
        ? "成約を受けてAIが自動再計画しました"
        : "AIが自動再計画しました";

  return (
    <section className="panel replan-banner">
      <div className="replan-banner__badge">{badge}</div>
      <p className="replan-banner__reason">{info.reason}</p>
      {info.steps && info.steps.length > 0 && (
        <ol className="replan-banner__steps">
          {info.steps.map((step) => <li key={step}>{step}</li>)}
        </ol>
      )}
      <div className="replan-banner__rates">
        <span>{info.before_achievement_rate.toFixed(1)}%</span>
        <span className="replan-banner__arrow">→</span>
        <span className="replan-banner__after">{info.after_achievement_rate.toFixed(1)}%</span>
      </div>
    </section>
  );
}
