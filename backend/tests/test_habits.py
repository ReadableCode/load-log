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
    # Clean slate per test
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("TRUNCATE habit_completions, habits RESTART IDENTITY CASCADE;")
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


# %%
# Tests #


def test_add_and_list_habit():
    import habits

    h = habits.add_habit("10,000 steps")
    assert h["name"] == "10,000 steps"
    assert h["id"] > 0

    all_habits = habits.get_all_habits()
    assert len(all_habits) == 1
    assert all_habits[0]["name"] == "10,000 steps"


def test_delete_habit_cascades_completions():
    import habits

    h = habits.add_habit("pushups")
    habits.toggle_completion(h["id"], date.today())
    habits.delete_habit(h["id"])

    assert habits.get_all_habits() == []
    assert habits.get_completions(h["id"]) == []


def test_toggle_completion_inserts_then_removes():
    import habits

    h = habits.add_habit("plank")
    today = date.today()

    assert habits.toggle_completion(h["id"], today) is True
    assert today in habits.get_completions(h["id"])

    assert habits.toggle_completion(h["id"], today) is False
    assert today not in habits.get_completions(h["id"])


def test_toggle_works_for_future_date():
    import habits

    h = habits.add_habit("read")
    future = date.today() + timedelta(days=3)

    assert habits.toggle_completion(h["id"], future) is True
    assert future in habits.get_completions(h["id"])


def test_completion_counts():
    import habits

    h1 = habits.add_habit("a")
    h2 = habits.add_habit("b")
    today = date.today()
    habits.toggle_completion(h1["id"], today)
    habits.toggle_completion(h1["id"], today - timedelta(days=1))
    habits.toggle_completion(h2["id"], today)

    counts = habits.get_completion_counts(days=7)
    assert counts[h1["id"]] == 2
    assert counts[h2["id"]] == 1


def test_current_streak():
    import habits

    h = habits.add_habit("water")
    today = date.today()
    for offset in [0, 1, 2, 4]:
        habits.toggle_completion(h["id"], today - timedelta(days=offset))

    assert habits.get_current_streak(h["id"]) == 3


def test_streak_zero_when_recent_gap():
    import habits

    h = habits.add_habit("stretch")
    today = date.today()
    habits.toggle_completion(h["id"], today - timedelta(days=3))

    assert habits.get_current_streak(h["id"]) == 0
