import type { Product } from "@/types";

// 顧客の表示名は GET /api/customers (ai.customer ビュー) が industry_name/
// company_size_name まで解決して返すため、表示用途にはもう使わない。
// ここに残しているのは新規顧客登録フォームの業種/企業規模セレクトボックス用で、
// マスタ一覧を返すAPIがまだ無いため supabase/seed.sql の投入順(= serial の採番順)を
// 前提にハードコードしている。マスタの並びが変わるとズレるため、マスタ一覧APIが
// 追加され次第そちらに差し替える。
export const INDUSTRY_NAMES: Record<number, string> = {
  1: "製造業",
  2: "建設業",
  3: "金融・保険業",
  4: "教育",
  5: "不動産業",
  6: "情報通信業",
  7: "小売業",
  8: "卸売業",
  9: "医療・福祉",
  10: "運輸業",
  11: "サービス業",
  12: "飲食業",
};

export const COMPANY_SIZE_NAMES: Record<number, string> = {
  1: "中小企業",
  2: "中堅企業",
  3: "大企業",
};

// 商談登録フォームの商談フェーズ選択用。deal_phase 一覧を返すAPIがまだ無いため
// supabase/seed.sql の投入順(= serial の採番順)を前提にハードコードしている。
// 表示専用途(既存商談の deal_phase_name 表示)では ai.* ビューが名称を返すため不要。
export const DEAL_PHASE_NAMES: Record<number, string> = {
  1: "初回接触",
  2: "ヒアリング",
  3: "提案",
  4: "見積",
  5: "契約交渉",
};

// deal_result_status テーブルは status_code(英語)しか持たないため、表示用の
// 日本語名はここで解決する。deal_phase_name・pattern_name 等は ai.* ビューが
// マスタの日本語名をそのまま返すため、ここでのハードコードは不要。
export const DEAL_RESULT_STATUS_NAMES: Record<string, string> = {
  ongoing: "進行中",
  won: "成約",
  lost: "失注",
};

// 商談編集フォームのフェーズ選択用。ai.deal ビューは deal_phase_name しか返さないため、
// 編集APIに送る deal_phase_id を選べるよう、ここだけは id/name の対応を持っておく。
// マスタ一覧を返すAPIがまだ無いため、supabase/seed.sql の投入順を前提にハードコードしている。
export const DEAL_PHASE_OPTIONS: { deal_phase_id: number; deal_phase_name: string }[] = [
  { deal_phase_id: 1, deal_phase_name: "初回接触" },
  { deal_phase_id: 2, deal_phase_name: "ヒアリング" },
  { deal_phase_id: 3, deal_phase_name: "提案" },
  { deal_phase_id: 4, deal_phase_name: "見積" },
  { deal_phase_id: 5, deal_phase_name: "契約交渉" },
];

// 事務作業(category='task')の「対応が難しい」差し替え候補プール。商談と違って実データが
// 無いため、固定の候補から未使用のものを提示する。この差し替え自体はまだローカル表示のみ
// (バックエンドへの保存は無い)。
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
