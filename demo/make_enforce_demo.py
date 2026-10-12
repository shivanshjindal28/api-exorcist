"""Build a small git repository whose feature branch breaks every enforcement rule."""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
if root.exists():
    shutil.rmtree(root)
(root / "api").mkdir(parents=True)
(root / "internal").mkdir()
(root / "docs").mkdir()


def git(*args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write(rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")


git("init", "-q", "-b", "main")
git("config", "user.email", "dev@example.test")
git("config", "user.name", "dev")

# ---- main: two documented, owned endpoints --------------------------------
write("api/users.py", '''from flask import Flask
app = Flask(__name__)

@app.route("/v1/users", methods=["GET"])
def list_users():
    return []

@app.route("/v1/legacy/export", methods=["GET"])
def legacy_export():
    return b""
''')
write("docs/openapi.yaml", '''openapi: 3.0.0
info: {title: bank, version: "1"}
paths:
  /v1/users:
    get: {summary: list users}
  /v1/legacy/export:
    get: {summary: old export}
''')
write("CODEOWNERS", "api/ @payments-team\n")
# The policy lives on main. A feature branch cannot exempt its own endpoints:
# enforcement reads .apix.yml from the merge base, not from the change.
write(".apix.yml", '''enforce:
  allow:
    - endpoint: "GET /healthz"
      reason: "liveness probe for the load balancer; infrastructure, not an API"
''')
git("add", "-A")
git("commit", "-q", "-m", "base")

# ---- feature: every rule broken once, one exemption, one clean addition ----
git("checkout", "-q", "-b", "feature")
write("api/users.py", '''from flask import Flask
app = Flask(__name__)

@app.route("/v1/users", methods=["GET"])
def list_users():
    return []

@app.route("/v1/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    return ""

@app.route("/v1/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    return {}

@app.route("/v1/legacy/export", methods=["GET"])
def legacy_export():
    return b""

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok"
''')
write("internal/debug.py", '''from flask import Flask
app = Flask(__name__)

@app.route("/v1/debug/replay", methods=["POST"])
def replay():
    return ""
''')
write("docs/openapi.yaml", '''openapi: 3.0.0
info: {title: bank, version: "1"}
paths:
  /v1/users:
    get: {summary: list users}
  /v1/users/{user_id}:
    get: {summary: one user}
  /v1/reports:
    get: {summary: reports, not built yet}
''')
git("add", "-A")
git("commit", "-q", "-m", "feature")
print(f"fixture at {root}")
