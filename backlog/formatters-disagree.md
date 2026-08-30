# black and isort disagree, and committed code satisfies neither

    found:  2026-08-28
    status: open
    verify: cd backend && uv run black --check src/ scripts/ ; uv run isort --check-only src/ scripts/

`CLAUDE.md` tells you to run both formatters:

```bash
cd backend && uv run black src/ && uv run isort src/
```

There is no isort configuration anywhere in the repo — no `profile` key in
`pyproject.toml`, no `.isort.cfg`, no `setup.cfg`. So isort runs with its default
grid-wrap style, which is not black's. Running the documented command in that
order leaves the tree isort-shaped; running them the other way leaves it
black-shaped. Neither is stable.

Concretely, isort rewrites this (black's output):

```python
from textual.widgets import (
    Button,
    Footer,
    ...
)
```

into this:

```python
from textual.widgets import (Button, Footer, Input, Label, ListItem,
                             ListView, Static)
```

Measured 2026-08-28 with black 26.5.1 and isort 8.0.1, against `src/` and
`scripts/`:

    black --check       3 files would be reformatted, 10 unchanged
    isort --check-only  2 files fail (tui/habits.py, scripts/backup_to_files.py)

So the committed tree is not clean under either tool. This bit during the
Postgres conformance work: running the documented formatter pair produced a
diff in three files that had nothing to do with the change, and they had to be
reverted by hand to keep the diff readable.

## fix

Add the black profile so isort defers on wrapping, in `backend/pyproject.toml`:

```toml
[tool.isort]
profile = "black"
line_length = 120
```

`line_length` matches the existing flake8 setting (`max-line-length = 120`).
Then run both across `src/`, `scripts/`, and `tests/` once and commit the result
as its own formatting-only commit, so the reformat never rides along with a
behaviour change.

blast radius: a large, purely cosmetic diff touching most files, which is
exactly why it wants to be its own commit rather than being folded into
something else. No runtime effect. Check it does not collide with an
in-progress branch before running it.

not doing yet: out of scope for the conformance work, and a whole-tree reformat
is not something to bundle into a change about the database.
