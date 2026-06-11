# %%
# Imports #

from datetime import date

import pytest

# %%
# Fixtures #


@pytest.fixture(autouse=True)
def _bootstrap_db():
    from db import bootstrap, get_conn, release_conn

    bootstrap()
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "TRUNCATE workout_sets, workout_sessions, exercises RESTART IDENTITY CASCADE;"
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


# %%
# Tests #


def test_get_or_create_exercise_is_case_insensitive():
    import workouts

    a = workouts.get_or_create_exercise("Bench Press")
    b = workouts.get_or_create_exercise("bench press")
    assert a["id"] == b["id"]
    assert len(workouts.get_all_exercises()) == 1


def test_create_session_default_date_is_today():
    import workouts

    s = workouts.create_session()
    assert s["session_date"] == date.today()
    assert s["notes"] == ""


def test_add_and_get_session_sets():
    import workouts

    ex = workouts.get_or_create_exercise("squat")
    s = workouts.create_session()
    workouts.add_set(s["id"], ex["id"], 1, 8, 135.0)
    workouts.add_set(s["id"], ex["id"], 2, 8, 135.0)

    sets = workouts.get_session_sets(s["id"])
    assert len(sets) == 2
    assert sets[0]["exercise_name"] == "squat"
    assert sets[0]["reps"] == 8
    assert sets[1]["weight_lbs"] == 135.0


def test_last_session_for_exercise_excludes_self():
    import workouts

    ex = workouts.get_or_create_exercise("deadlift")
    s1 = workouts.create_session(session_date=date(2026, 6, 1))
    workouts.add_set(s1["id"], ex["id"], 1, 5, 225.0)
    s2 = workouts.create_session(session_date=date(2026, 6, 8))
    workouts.add_set(s2["id"], ex["id"], 1, 5, 235.0)

    last = workouts.get_last_session_for_exercise(ex["id"], before_session_id=s2["id"])
    assert len(last) == 1
    assert last[0]["weight_lbs"] == 225.0


def test_suggest_next_weight_bumps_when_hit_targets():
    import workouts

    ex = workouts.get_or_create_exercise("ohp")
    s1 = workouts.create_session(session_date=date(2026, 6, 1))
    workouts.add_set(s1["id"], ex["id"], 1, 8, 100.0)
    workouts.add_set(s1["id"], ex["id"], 2, 8, 100.0)

    s2 = workouts.create_session(session_date=date(2026, 6, 8))
    workouts.add_set(s2["id"], ex["id"], 1, 8, 100.0)
    workouts.add_set(s2["id"], ex["id"], 2, 8, 100.0)

    assert workouts.suggest_next_weight(ex["id"], s2["id"]) == 105.0


def test_suggest_next_weight_holds_when_missed():
    import workouts

    ex = workouts.get_or_create_exercise("row")
    s1 = workouts.create_session(session_date=date(2026, 6, 1))
    workouts.add_set(s1["id"], ex["id"], 1, 8, 95.0)
    workouts.add_set(s1["id"], ex["id"], 2, 8, 95.0)

    s2 = workouts.create_session(session_date=date(2026, 6, 8))
    workouts.add_set(s2["id"], ex["id"], 1, 8, 95.0)
    workouts.add_set(s2["id"], ex["id"], 2, 6, 95.0)

    assert workouts.suggest_next_weight(ex["id"], s2["id"]) == 95.0


def test_suggest_next_weight_none_without_history():
    import workouts

    ex = workouts.get_or_create_exercise("curl")
    s = workouts.create_session()
    workouts.add_set(s["id"], ex["id"], 1, 10, 25.0)

    assert workouts.suggest_next_weight(ex["id"], s["id"]) is None


def test_update_session_notes():
    import workouts

    s = workouts.create_session()
    workouts.update_session_notes(s["id"], "felt strong")
    sessions = workouts.get_recent_sessions()
    assert sessions[0]["notes"] == "felt strong"


def test_exercise_history_dataframe():
    import workouts

    ex = workouts.get_or_create_exercise("bench")
    s1 = workouts.create_session(session_date=date(2026, 6, 1))
    workouts.add_set(s1["id"], ex["id"], 1, 8, 135.0)
    s2 = workouts.create_session(session_date=date(2026, 6, 8))
    workouts.add_set(s2["id"], ex["id"], 1, 8, 140.0)

    df = workouts.get_exercise_history(ex["id"])
    assert list(df.columns) == ["session_date", "set_number", "reps", "weight_lbs"]
    assert len(df) == 2
