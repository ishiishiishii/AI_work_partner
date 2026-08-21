import type { ReplanInfo } from "@/types";

type ReplanBannerProps = {
  info: ReplanInfo;
};

export function ReplanBanner({ info }: ReplanBannerProps) {
  return (
    <section className="panel replan-banner">
      <div className="replan-banner__badge">AIが自動再計画しました</div>
      <p className="replan-banner__reason">{info.reason}</p>
      <div className="replan-banner__rates">
        <span>{info.before_achievement_rate.toFixed(1)}%</span>
        <span className="replan-banner__arrow">→</span>
        <span className="replan-banner__after">{info.after_achievement_rate.toFixed(1)}%</span>
      </div>
    </section>
  );
}
