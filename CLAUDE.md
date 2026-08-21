# CLAUDE.md

このリポジトリのプロダクト定義・MVP 範囲・データモデル方針・Docker 作業ルールは **[AGENTS.md](./AGENTS.md)** を正とする。

作業開始前に `AGENTS.md` を読み、特に次を守ること。

1. MVP のコア体験（目標入力 → 計画生成 → 根拠 → 結果入力 → 再計画）を壊さない
2. Later 機能（Calendar / CRM 連携、チーム最適など）を先に実装しない
3. アプリの実行・依存操作は Docker コンテナ内（`docker compose exec`）を原則とする
4. Supabase CLI はホスト側。アプリコンテナに CLI を入れない
5. AI は差し替え可能な境界（スタブ / サービス層）を維持する
