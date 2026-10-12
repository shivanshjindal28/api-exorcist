"""
The REST API (Phase 5).

    auth.py        bearer tokens, stored hashed; viewer and approver roles
    workspace.py   the served state: a scan, its gate, a Safe Kill controller
    app.py         FastAPI routes over the workspace

Nothing is imported here on purpose: FastAPI is an optional extra
(`pip install -e ".[api]"`), and importing this package must not fail on a
machine that only uses the CLI.
"""
