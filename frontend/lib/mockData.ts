import type { RepAffinity, SalesRep } from "@/types";

// 担当者一覧を返すAPIがまだ無いため、supabase/seed.sql の担当者情報を直書きしている
// (rep_id: 1 = 石川次郎、sales_rep.csv 由来)
export const mockSalesRep: SalesRep = {
  rep_id: 1,
  rep_name: "石川次郎",
};

// rep_affinity（得意分野スコア）はバックエンドにまだ無いテーブルのため、引き続きモック
export const mockRepAffinities: RepAffinity[] = [
  {
    rep_id: 1,
    category_id: 1,
    category_name: "製造業",
    score: 82,
  },
  {
    rep_id: 1,
    category_id: 2,
    category_name: "卸売業",
    score: 55,
  },
  {
    rep_id: 1,
    category_id: 3,
    category_name: "小売業",
    score: 30,
  },
];
