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
