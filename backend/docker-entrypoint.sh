#!/bin/sh
# Deliberately inert: schema convergence is the app's job (src/bootstrap.py, run
# from the Streamlit script and the TUI's main()), so a bare `streamlit run` or
# `python -m tui.app` behaves identically to the container.
#
# This used to run `alembic upgrade head`. It no longer does, and nothing should
# be put back here — a migration that only fires when the container starts means
# the code and the schema can disagree depending on how the app was launched.
exec "$@"
