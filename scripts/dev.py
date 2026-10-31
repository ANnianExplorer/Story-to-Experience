"""One-command development launcher.

Usage (from the repository root):

    ./.venv/Scripts/python.exe scripts/dev.py db          # start PostgreSQL and migrate
    ./.venv/Scripts/python.exe scripts/dev.py api         # API on 127.0.0.1:8000
    ./.venv/Scripts/python.exe scripts/dev.py web         # workbench :5173 + experience :5174
    ./.venv/Scripts/python.exe scripts/dev.py all         # db + api + both frontends

Defaults come from ``xujing_api.config`` (database URL, storage root, model
gateway and key from the environment); nothing here hard-codes a credential.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

APPS = {
    "workbench": (ROOT / "apps" / "workbench", 5173),
    "experience": (ROOT / "apps" / "experience", 5174),
}


def _env() -> dict[str, str]:
    """Environment for the API: repository root importable, no code changes."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(API_DIR), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    return env


def _npm() -> str:
    found = shutil.which("npm")
    if not found:
        raise SystemExit("npm 不可用：请先安装 Node.js 20+。")
    return found


def start_db() -> None:
    """Start the development database and bring the schema to head."""
    if shutil.which("docker") is None:
        raise SystemExit("docker 不可用：请先安装 Docker Desktop。")
    subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "infra" / "compose.dev.yaml"), "up", "-d"],
        check=True,
    )
    # Wait for the health check instead of sleeping a fixed time.
    for _ in range(60):
        probe = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "infra" / "compose.dev.yaml"), "ps", "--status", "running", "-q", "db"],
            capture_output=True,
            text=True,
        )
        if probe.stdout.strip():
            break
        time.sleep(1)
    subprocess.run([PYTHON, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "server", check=True)
    print("数据库就绪（迁移已到 head）。")


def start_api() -> None:
    env = _env()
    print("API: http://127.0.0.1:8000  (Ctrl+C 停止)")
    subprocess.run(
        [PYTHON, "-m", "uvicorn", "xujing_api.asgi:app", "--app-dir", str(API_DIR), "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
        env=env,
        check=False,
    )


def start_web() -> None:
    npm = _npm()
    processes = []
    try:
        for name, (directory, port) in APPS.items():
            if not (directory / "node_modules").exists():
                print(f"{name}: 首次运行，安装依赖…")
                subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=directory, check=True)
            processes.append(
                subprocess.Popen([npm, "run", "dev", "--", "--port", str(port), "--strictPort"], cwd=directory)
            )
            print(f"{name}: http://localhost:{port}")
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            process.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=["db", "api", "web", "all"])
    args = parser.parse_args()

    if args.target == "db":
        start_db()
    elif args.target == "api":
        start_api()
    elif args.target == "web":
        start_web()
    else:
        start_db()
        # The frontends run in the foreground; the API is stopped with them.
        api = subprocess.Popen([PYTHON, str(Path(__file__).resolve()), "api"])
        try:
            start_web()
        finally:
            api.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
