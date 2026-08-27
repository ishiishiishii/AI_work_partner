"""Per-rep profile: weekly home-office availability and admin-task duration
estimates. Not yet consumed by route_planning.py -- that still uses its own
request-level work_start/work_end/turnaround_buffer_min; wiring this data in
as defaults is a separate follow-up.
"""

from psycopg import Connection


def list_admin_task_types(conn: Connection) -> list[dict]:
    rows = conn.execute(
        """
        select task_type_id, task_name, is_default
        from admin_task_type
        order by display_order, task_type_id
        """
    ).fetchall()
    return list(rows)


def create_admin_task_type(conn: Connection, task_name: str) -> dict:
    row = conn.execute(
        """
        insert into admin_task_type (task_name, is_default, display_order)
        values (%s, false, (select coalesce(max(display_order), 0) + 1 from admin_task_type))
        on conflict (task_name) do update set task_name = excluded.task_name
        returning task_type_id, task_name, is_default
        """,
        (task_name,),
    ).fetchone()
    conn.commit()
    return row


def get_rep_profile(conn: Connection, rep_id: int) -> dict:
    home_office = conn.execute(
        """
        select day_of_week, is_home_available
        from rep_home_office_availability
        where rep_id = %s
        order by day_of_week
        """,
        (rep_id,),
    ).fetchall()

    task_durations = conn.execute(
        """
        select att.task_type_id, att.task_name, ratd.duration_minutes, ratd.updated_at
        from admin_task_type att
        left join rep_admin_task_duration ratd
          on ratd.task_type_id = att.task_type_id and ratd.rep_id = %s
        order by att.display_order, att.task_type_id
        """,
        (rep_id,),
    ).fetchall()

    return {
        "rep_id": rep_id,
        "home_office": list(home_office),
        "task_durations": list(task_durations),
    }


def set_home_office_availability(
    conn: Connection, rep_id: int, day_of_week: int, is_home_available: bool
) -> dict:
    row = conn.execute(
        """
        insert into rep_home_office_availability (rep_id, day_of_week, is_home_available)
        values (%s, %s, %s)
        on conflict (rep_id, day_of_week)
        do update set is_home_available = excluded.is_home_available
        returning day_of_week, is_home_available
        """,
        (rep_id, day_of_week, is_home_available),
    ).fetchone()
    conn.commit()
    return row


def set_admin_task_duration(
    conn: Connection, rep_id: int, task_type_id: int, duration_minutes: int
) -> dict:
    row = conn.execute(
        """
        insert into rep_admin_task_duration (rep_id, task_type_id, duration_minutes, updated_at)
        values (%s, %s, %s, now())
        on conflict (rep_id, task_type_id)
        do update set duration_minutes = excluded.duration_minutes, updated_at = now()
        returning task_type_id, duration_minutes, updated_at
        """,
        (rep_id, task_type_id, duration_minutes),
    ).fetchone()
    conn.commit()
    task_name = conn.execute(
        "select task_name from admin_task_type where task_type_id = %s",
        (task_type_id,),
    ).fetchone()["task_name"]
    return {**row, "task_name": task_name}
