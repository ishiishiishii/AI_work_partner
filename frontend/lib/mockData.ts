import type { SalesRep } from "@/types";

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

// 担当者一覧を返すAPIがまだ無いため、supabase/seed.sql に実在する18人を直書きしている。
// 名称解決APIが追加され次第、GET /api/sales-reps 相当のAPI呼び出しに差し替える。
export const mockSalesReps: SalesRep[] = [
  { rep_id: 1, rep_name: "石川次郎" },
  { rep_id: 2, rep_name: "村上花子" },
  { rep_id: 3, rep_name: "小林綾子" },
  { rep_id: 4, rep_name: "木村さゆり" },
  { rep_id: 5, rep_name: "加藤拓也" },
  { rep_id: 6, rep_name: "遠藤直樹" },
  { rep_id: 7, rep_name: "近藤拓也" },
  { rep_id: 8, rep_name: "井上愛" },
  { rep_id: 9, rep_name: "吉田直樹" },
  { rep_id: 10, rep_name: "高橋健二" },
  { rep_id: 11, rep_name: "林慎一" },
  { rep_id: 12, rep_name: "井上健太" },
  { rep_id: 13, rep_name: "林麻衣" },
  { rep_id: 14, rep_name: "岡田健二" },
  { rep_id: 15, rep_name: "吉田陽子" },
  { rep_id: 16, rep_name: "石川大輔" },
  { rep_id: 17, rep_name: "岡本裕子" },
  { rep_id: 18, rep_name: "後藤大輔" },
];

export const mockSalesRep: SalesRep = mockSalesReps[0];

// 事務作業の「AI作り直し」で差し替え候補として使う仮の提案プール。
// 商談のような実データが無いため、ここでは固定の候補から未使用のものを提示する。
export const mockTaskSuggestions: {
  title: string;
  activityTypeName: string;
  reasoningText: string;
}[] = [
  {
    title: "名刺交換した見込み客のリストアップ",
    activityTypeName: "新規開拓",
    reasoningText: "直近の展示会・商談で交換した名刺をリスト化し、新規開拓の候補を増やすことを提案しました。",
  },
  {
    title: "見積書テンプレートの見直し",
    activityTypeName: "資料作成",
    reasoningText: "商品カタログの更新に合わせて、見積書テンプレートを最新化しておくことを提案しました。",
  },
  {
    title: "休眠顧客への様子伺いメール送付",
    activityTypeName: "メール",
    reasoningText: "しばらく接点の無い既存顧客に、様子伺いのメールで関係を維持することを提案しました。",
  },
  {
    title: "紹介案件の候補リスト作成",
    activityTypeName: "新規開拓",
    reasoningText: "既存顧客からの紹介が見込めそうな案件を洗い出し、優先順位をつけることを提案しました。",
  },
  {
    title: "商談メモの整理・共有",
    activityTypeName: "資料作成",
    reasoningText: "直近の商談内容をメモから整理し、チームで共有できる状態にしておくことを提案しました。",
  },
  {
    title: "オンライン商談ツールの動作確認",
    activityTypeName: "Web会議",
    reasoningText: "来週予定しているオンライン商談に備え、事前に接続・画面共有の動作確認をしておくことを提案しました。",
  },
];

