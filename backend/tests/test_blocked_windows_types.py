"""_blocked_windows/_merge_windows の型の食い違いバグの回帰テスト。

activity_plan.start_time/end_time はDB上text("HH:MM")で保存されているため、
_blocked_windows がそのまま返すとstrになる。break_start/break_end はPydanticの
time型で来るため、両者を混ぜてsorted()やdatetime.combine()に渡すと
TypeErrorになっていた(本番相当のDBで実際に発生した不具合)。

テスト用の予定はTEST_DATEに1件だけ作成し、最後に必ず削除する。
"""

from datetime import date, time, timedelta

from app.db import get_connection
from app.services.route_planning import (
    _blocked_windows,
    _merge_windows,
    _reschedule_flexible_tasks_for_day,
)

TEST_DATE = date(2099, 1, 15)


def test_blocked_windows_returns_time_objects_not_strings():
    with get_connection() as conn:
        try:
            conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  activity_type, priority, plan_status, is_ai_generated
                )
                values (1, %s, '09:00', '10:00', 'task', 'test', 'task', 3, 'scheduled', false)
                """,
                (TEST_DATE,),
            )
            conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  activity_type, priority, plan_status, is_ai_generated
                )
                values (1, %s, '10:00', '11:00', 'task', 'AI空き時間タスク',
                        '新規開拓', 3, 'scheduled', true)
                """,
                (TEST_DATE,),
            )

            windows = _blocked_windows(conn, rep_id=1, target_date=TEST_DATE)
            assert windows == [(time(9, 0), time(10, 0))]
            assert all(isinstance(start, time) and isinstance(end, time) for start, end in windows)
        finally:
            conn.rollback()


def test_merge_windows_accepts_db_and_request_sourced_times_together():
    # _blocked_windows(DB由来、修正後はtime型) + break_start/end(Pydantic由来、time型)
    # を混ぜてもsorted()で例外にならないことを確認
    db_window = (time(9, 0), time(10, 0))
    break_window = (time(12, 0), time(13, 0))
    merged = _merge_windows([db_window, break_window])
    assert merged == [db_window, break_window]

    # 重なる場合は1つにまとまる
    overlapping = _merge_windows([(time(9, 0), time(12, 30)), (time(12, 0), time(13, 0))])
    assert overlapping == [(time(9, 0), time(13, 0))]


def test_flexible_ai_tasks_are_repacked_around_fixed_visits():
    target_date = TEST_DATE + timedelta(days=1)
    with get_connection() as conn:
        try:
            conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  activity_type, priority, plan_status, is_ai_generated
                ) values
                  (1, %s, '09:00', '10:00', 'task', '固定訪問相当',
                   '訪問', 1, 'scheduled', false),
                  (1, %s, '09:00', '10:00', 'task', '新規開拓リストの更新',
                   '新規開拓', 2, 'scheduled', true),
                  (1, %s, '10:00', '11:00', 'task', '週次報告書の作成',
                   '資料作成', 3, 'scheduled', true)
                """,
                (target_date, target_date, target_date),
            )

            overflow = _reschedule_flexible_tasks_for_day(
                conn,
                rep_id=1,
                target_date=target_date,
                work_start=time(9, 0),
                work_end=time(13, 0),
                break_window=(time(12, 0), time(13, 0)),
            )
            rows = conn.execute(
                """
                select title, start_time, end_time
                from activity_plan
                where rep_id = 1 and plan_date = %s and is_ai_generated = true
                order by start_time
                """,
                (target_date,),
            ).fetchall()

            assert overflow == 0
            assert [
                (row["title"], row["start_time"], row["end_time"])
                for row in rows
            ] == [
                ("新規開拓リストの更新", "10:00", "11:00"),
                ("週次報告書の作成", "11:00", "12:00"),
            ]
        finally:
            conn.rollback()
