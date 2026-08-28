# 成約・失注後の自動再計画デモ（EMP010）

対象アカウントは `EMP010`、パスワードは `demo1234` です。
このデータはEMP010の既存商談・予定を一時的にデモ専用データへ置き換えます。
初回実行時のデータは自動退避され、下記の復元SQLで戻せます。

デモ前または成約版・失注版を切り替える前に、ホストから次を実行します。

```bash
docker exec -i supabase_db_ai_work_partner psql -U postgres -d postgres \
  < supabase/demo/replan_demo_emp010.sql
```

実行後、既に画面を開いている場合はブラウザを再読み込みします。

画面では8月10日の「【結果入力デモ】中央DX製作所」を開き、「成約」または
「失注」を押します。

- 成約: 800万円を実績へ反映し、残目標を200万円へ縮小。後半候補を1社に整理
- 失注: 同案件を0円として再計算。後続フォローを削除し、代替候補2社を追加

初回セットアップ前のEMP010データへ戻す場合は次を実行します。

```bash
docker exec -i supabase_db_ai_work_partner psql -U postgres -d postgres \
  < supabase/demo/replan_demo_emp010_restore.sql
```
