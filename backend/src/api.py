# %%
# Imports #

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import habits
import workouts
from db import bootstrap

# %%
# App #

app = FastAPI(title="Load Log API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    bootstrap()


@app.get("/health")
async def health():
    return {"status": "ok"}


# %%
# Schemas #


class HabitIn(BaseModel):
    name: str


class ToggleIn(BaseModel):
    target_date: date


class SessionIn(BaseModel):
    session_date: date | None = None
    notes: str = ""


class NotesIn(BaseModel):
    notes: str


class SetIn(BaseModel):
    exercise_name: str
    reps: int
    weight_lbs: float


# %%
# Habits #


@app.get("/habits")
def list_habits():
    return habits.get_all_habits()


@app.post("/habits")
def create_habit(payload: HabitIn):
    return habits.add_habit(payload.name)


@app.delete("/habits/{habit_id}")
def remove_habit(habit_id: int):
    habits.delete_habit(habit_id)
    return {"deleted": habit_id}


@app.get("/habits/{habit_id}/completions")
def habit_completions(habit_id: int, days: int = 365):
    return [d.isoformat() for d in habits.get_completions(habit_id, days=days)]


@app.post("/habits/{habit_id}/toggle")
def habit_toggle(habit_id: int, payload: ToggleIn):
    now_completed = habits.toggle_completion(habit_id, payload.target_date)
    return {"completed": now_completed, "date": payload.target_date.isoformat()}


# %%
# Workouts #


@app.get("/exercises")
def list_exercises():
    return workouts.get_all_exercises()


@app.post("/sessions")
def create_session(payload: SessionIn):
    return workouts.create_session(
        session_date=payload.session_date, notes=payload.notes
    )


@app.get("/sessions")
def recent_sessions(limit: int = 10):
    return workouts.get_recent_sessions(limit=limit)


@app.get("/sessions/{session_id}")
def session_detail(session_id: int):
    return {
        "id": session_id,
        "sets": workouts.get_session_sets(session_id),
    }


@app.patch("/sessions/{session_id}/notes")
def patch_notes(session_id: int, payload: NotesIn):
    workouts.update_session_notes(session_id, payload.notes)
    return {"id": session_id, "notes": payload.notes}


@app.post("/sessions/{session_id}/sets")
def log_set(session_id: int, payload: SetIn):
    exercise = workouts.get_or_create_exercise(payload.exercise_name)
    existing = workouts.get_session_sets(session_id)
    next_set_num = (
        1 + max(
            (s["set_number"] for s in existing if s["exercise_id"] == exercise["id"]),
            default=0,
        )
    )
    return workouts.add_set(
        session_id, exercise["id"], next_set_num, payload.reps, payload.weight_lbs
    )


@app.get("/exercises/{exercise_id}/history")
def exercise_history(exercise_id: int, limit: int = 20):
    df = workouts.get_exercise_history(exercise_id, limit=limit)
    return df.assign(session_date=df["session_date"].astype(str)).to_dict(
        orient="records"
    )


@app.get("/exercises/{exercise_id}/suggestion")
def exercise_suggestion(exercise_id: int, session_id: int):
    suggestion = workouts.suggest_next_weight(exercise_id, session_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Insufficient history")
    return {"exercise_id": exercise_id, "suggested_weight_lbs": suggestion}
