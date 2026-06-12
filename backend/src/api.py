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


@app.get("/workouts/volume")
def workout_volume(days: int = 365):
    return {d.isoformat(): v for d, v in workouts.get_volume_by_date(days=days).items()}


@app.get("/workouts/{workout_date}")
def workout_for_date(workout_date: date):
    return {
        "workout_date": workout_date.isoformat(),
        "sets": workouts.get_sets_for_date(workout_date),
    }


@app.post("/workouts/{workout_date}/sets")
def log_set(workout_date: date, payload: SetIn):
    exercise = workouts.get_or_create_exercise(payload.exercise_name)
    return workouts.add_set(
        workout_date, exercise["id"], payload.reps, payload.weight_lbs
    )


@app.delete("/sets/{set_id}")
def remove_set(set_id: int):
    workouts.delete_set(set_id)
    return {"deleted": set_id}


@app.get("/exercises/{exercise_id}/history")
def exercise_history(exercise_id: int, limit_days: int = 365):
    df = workouts.get_exercise_history(exercise_id, limit_days=limit_days)
    if df.empty:
        return []
    return df.assign(workout_date=df["workout_date"].astype(str)).to_dict(
        orient="records"
    )


@app.get("/exercises/{exercise_id}/suggestion")
def exercise_suggestion(exercise_id: int, workout_date: date):
    suggestion = workouts.suggest_next_weight(exercise_id, workout_date)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Insufficient history")
    return {"exercise_id": exercise_id, "suggested_weight_lbs": suggestion}
