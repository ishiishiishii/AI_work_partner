import type { Product } from "@/types";

// deal_result_status テーブルは status_code(英語)しか持たないため、表示用の
// 日本語名はここで解決する。deal_phase_name・pattern_name 等は ai.* ビューが
// マスタの日本語名をそのまま返すため、ここでのハードコードは不要。
export const DEAL_RESULT_STATUS_NAMES: Record<string, string> = {
  ongoing: "進行中",
  won: "成約",
  lost: "失注",
};

// 事務作業(category='task')の「対応が難しい」差し替え候補プール。商談と違って実データが
// 無いため、固定の候補から未使用のものを提示する。差し替え自体は POST /api/plans で
// 実在の予定として保存する(dashboard/page.tsx の handleRequestAlternative 参照)。
export const mockTaskSuggestions: { title: string; activityTypeName: string; reasoningText: string }[] = [
  {
    title: "見積書の見直し",
    activityTypeName: "資料作成",
    reasoningText: "他の予定と重なっていたため、見積内容の見直しに差し替えました。",
  },
  {
    title: "新規リストへの架電",
    activityTypeName: "新規開拓",
    reasoningText: "空いた時間を使って新規開拓の候補を増やすことを提案しました。",
  },
  {
    title: "既存顧客へのフォローメール",
    activityTypeName: "メール",
    reasoningText: "短時間でも接点を作れるよう、フォローメールに差し替えました。",
  },
  {
    title: "週次報告書の作成",
    activityTypeName: "資料作成",
    reasoningText: "活動の振り返りと報告書作成の時間として提案しました。",
  },
];

// 商品マスタには名称・カテゴリしか無く、価格帯・特徴などを返すAPIがまだ無いため、
// 商品詳細ページ用に product_id から決定的に(同じ商品なら常に同じ内容になるよう)
// ダミーの説明・価格帯・納期目安・特徴を生成する。実データが用意でき次第、置き換える。
const PRODUCT_FEATURE_POOL = [
  "導入実績豊富",
  "低コストで導入可能",
  "短納期対応",
  "柔軟なカスタマイズ",
  "保守サポート充実",
  "クラウド対応",
  "省スペース設計",
  "高い信頼性",
];

export type ProductDummyDetails = {
  description: string;
  priceRangeText: string;
  leadTimeText: string;
  features: string[];
};

export function getProductDummyDetails(product: Product): ProductDummyDetails {
  const seed = product.product_id;
  const priceLow = 50000 + ((seed * 37) % 950000);
  const priceHigh = priceLow + 100000 + ((seed * 13) % 300000);
  const leadDays = 5 + (seed % 20);
  const features = [0, 3, 5].map((offset) => PRODUCT_FEATURE_POOL[(seed + offset) % PRODUCT_FEATURE_POOL.length]);

  return {
    description: `${product.category_name}(${product.subcategory_name})に分類される商品です。業種・企業規模に応じた提案実績があります。`,
    priceRangeText: `¥${priceLow.toLocaleString("ja-JP")} 〜 ¥${priceHigh.toLocaleString("ja-JP")}`,
    leadTimeText: `約${leadDays}営業日`,
    features,
  };
}
