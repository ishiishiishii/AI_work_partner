import type { RepAffinity, SalesRep } from "@/types";

// 担当者一覧を返すAPIがまだ無いため、supabase/seed.sql の担当者情報を直書きしている
export const mockSalesRep: SalesRep = {
  rep_id: "11111111-1111-1111-1111-111111111111",
  rep_name: "山田 太郎",
};

// rep_affinity（得意分野スコア）はバックエンドにまだ無いテーブルのため、引き続きモック
export const mockRepAffinities: RepAffinity[] = [
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 1,
    category_name: "製造業",
    score: 82,
  },
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 2,
    category_name: "卸売業",
    score: 55,
  },
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 3,
    category_name: "小売業",
    score: 30,
  },
];
