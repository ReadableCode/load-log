# %%
# Imports #

from datetime import date, timedelta

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
        cur.execute("TRUNCATE workout_sets, exercises RESTART IDENTITY CASCADE;")
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


def test_add_set_auto_increments_set_number():
    import workouts

    ex = workouts.get_or_create_exercise("squat")
    today = date.today()
    s1 = workouts.add_set(today, ex["id"], 8, 135.0)
    s2 = workouts.add_set(today, ex["id"], 8, 135.0)
    s3 = workouts.add_set(today, ex["id"], 7, 135.0)

    assert s1["set_number"] == 1
    assert s2["set_number"] == 2
    assert s3["set_number"] == 3


def test_add_set_per_exercise_numbering_isolated():
    import workouts

    bench = workouts.get_or_create_exercise("bench")
    row = workouts.get_or_create_exercise("row")
    d = date.today()

    workouts.add_set(d, bench["id"], 8, 135.0)
    workouts.add_set(d, row["id"], 10, 100.0)
    s = workouts.add_set(d, bench["id"], 8, 135.0)
    assert s["set_number"] == 2  # bench set numbering is independent of row


def test_get_sets_for_date():
    import workouts

    ex = workouts.get_or_create_exercise("ohp")
    today = date.today()
    yesterday = today - timedelta(days=1)
    workouts.add_set(today, ex["id"], 8, 100.0)
    workouts.add_set(yesterday, ex["id"], 8, 95.0)

    sets = workouts.get_sets_for_date(today)
    assert len(sets) == 1
    assert sets[0]["weight_lbs"] == 100.0


def test_last_workout_excludes_current_date():
    import workouts

    ex = workouts.get_or_create_exercise("deadlift")
    workouts.add_set(date(2026, 6, 1), ex["id"], 5, 225.0)
    workouts.add_set(date(2026, 6, 8), ex["id"], 5, 235.0)

    last = workouts.get_last_workout_for_exercise(ex["id"], before_date=date(2026, 6, 8))
    assert len(last) == 1
    assert last[0]["weight_lbs"] == 225.0
    assert last[0]["workout_date"] == date(2026, 6, 1)


def test_volume_by_date():
    import workouts

    ex = workouts.get_or_create_exercise("curl")
    today = date.today()
    workouts.add_set(today, ex["id"], 10, 25.0)
    workouts.add_set(today, ex["id"], 10, 25.0)

    volumes = workouts.get_volume_by_date(days=7)
    assert volumes[today] == 10 * 25.0 + 10 * 25.0


def test_workout_dates_distinct_sorted():
    import workouts

    ex = workouts.get_or_create_exercise("plank")
    workouts.add_set(date(2026, 6, 1), ex["id"], 1, 0.0)
    workouts.add_set(date(2026, 6, 1), ex["id"], 1, 0.0)
    workouts.add_set(date(2026, 6, 5), ex["id"], 1, 0.0)

    dates = workouts.get_workout_dates(days=30)
    assert dates == [date(2026, 6, 1), date(2026, 6, 5)]


def test_suggest_next_weight_bumps_on_match():
    import workouts

    ex = workouts.get_or_create_exercise("ohp")
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 8)
    workouts.add_set(d1, ex["id"], 8, 100.0)
    workouts.add_set(d1, ex["id"], 8, 100.0)
    workouts.add_set(d2, ex["id"], 8, 100.0)
    workouts.add_set(d2, ex["id"], 8, 100.0)

    assert workouts.suggest_next_weight(ex["id"], d2) == 105.0


def test_suggest_next_weight_holds_when_missed():
    import workouts

    ex = workouts.get_or_create_exercise("row")
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 8)
    workouts.add_set(d1, ex["id"], 8, 95.0)
    workouts.add_set(d1, ex["id"], 8, 95.0)
    workouts.add_set(d2, ex["id"], 8, 95.0)
    workouts.add_set(d2, ex["id"], 6, 95.0)

    assert workouts.suggest_next_weight(ex["id"], d2) == 95.0


def test_suggest_next_weight_none_without_history():
    import workouts

    ex = workouts.get_or_create_exercise("face pull")
    workouts.add_set(date.today(), ex["id"], 12, 30.0)
    assert workouts.suggest_next_weight(ex["id"], date.today()) is None


def test_delete_set():
    import workouts

    ex = workouts.get_or_create_exercise("dip")
    s = workouts.add_set(date.today(), ex["id"], 10, 0.0)
    workouts.delete_set(s["id"])
    assert workouts.get_sets_for_date(date.today()) == []


def test_exercise_history_dataframe():
    import workouts

    ex = workouts.get_or_create_exercise("bench")
    workouts.add_set(date(2026, 6, 1), ex["id"], 8, 135.0)
    workouts.add_set(date(2026, 6, 8), ex["id"], 8, 140.0)

    df = workouts.get_exercise_history(ex["id"], limit_days=365)
    assert list(df.columns) == ["workout_date", "set_number", "reps", "weight_lbs"]
    assert len(df) == 2
