import type { PlanChange, ReplanInfo } from "@/types";

type ReplanBannerProps = {
  info: ReplanInfo;
  onClose: () => void;
};

function formatPlanDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${Number(month)}/${Number(day)}`;
}

function formatYen(amount: number): string {
  return `¥${Math.round(amount).toLocaleString("ja-JP")}`;
}

function describeChangeHeadline(change: PlanChange): string {
  if (change.type === "moved") {
    return `${change.customer_name}(${change.activity_type_name})を${formatPlanDate(change.before_date!)}→${formatPlanDate(change.after_date!)}に変更`;
  }
  if (change.type === "added") {
    return `${change.customer_name}(${change.activity_type_name})を${formatPlanDate(change.after_date!)}に新規追加`;
  }
  return `${change.customer_name}(${change.activity_type_name})を${formatPlanDate(change.before_date!)}の予定から削除`;
}

export function ReplanBanner({ info, onClose }: ReplanBannerProps) {
  const badge =
    info.outcome === "lost"
      ? "失注を受けてAIが自動再計画しました"
      : info.outcome === "won"
        ? "成約を受けてAIが自動再計画しました"
        : "AIが自動再計画しました";

  return (
    <div
      className="plan-modal-overlay replan-banner-overlay"
      onClick={onClose}
      role="presentation"
    >
      <section
        className="panel plan-modal replan-banner"
        role="dialog"
        aria-modal="true"
        aria-label={badge}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="plan-modal__header">
          <div className="replan-banner__badge">{badge}</div>
          <button type="button" className="plan-modal__close" onClick={onClose} aria-label="閉じる">
            ×
          </button>
        </div>
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
        <p className="replan-banner__goal-explainer">
          {(() => {
            const gap = info.target_amount - info.after_forecast_amount;
            return gap <= 0
              ? `目標金額${formatYen(info.target_amount)}に対して見込みは${formatYen(info.after_forecast_amount)}(達成率${info.after_achievement_rate.toFixed(1)}%)。目標を上回る見込みです。`
              : `目標金額${formatYen(info.target_amount)}に対して見込みは${formatYen(info.after_forecast_amount)}(達成率${info.after_achievement_rate.toFixed(1)}%)。あと${formatYen(gap)}分の積み増しが必要です。`;
          })()}
        </p>
        {info.changes && info.changes.length > 0 && (
          <>
            <p className="replan-banner__changes-heading">変更された予定({info.changes.length}件)</p>
            <ul className="replan-banner__changes">
              {info.changes.map((change, index) => (
                <li key={index} className={`replan-banner__change replan-banner__change--${change.type}`}>
                  <div className="replan-banner__change-headline">{describeChangeHeadline(change)}</div>
                  {change.type !== "removed" && (
                    <div className="replan-banner__change-detail">
                      {change.expected_amount !== undefined && (
                        <span>
                          見込み{formatYen(change.expected_amount)}
                          {change.expected_probability !== undefined && `(成約確度${change.expected_probability}%)`}
                        </span>
                      )}
                      {change.reasoning_text && <span>{change.reasoning_text}</span>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
