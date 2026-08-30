"""Single closed-test gate. It refuses to start if implementation categories are incomplete."""

from __future__ import annotations

import os
import signal
import shutil
import site
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md", ".env.example", "docker-compose.yml", "Makefile",
    "apps/api/app/main.py", "apps/api/app/api/routes.py", "apps/api/app/core/config.py",
    "apps/api/app/db/models.py", "apps/api/app/db/session.py", "apps/api/alembic/versions/0001_initial.py", "apps/api/alembic/versions/0002_media_features.py", "apps/api/alembic/versions/0003_evidence_bound_synthesis.py", "apps/api/alembic/versions/0004_runtime_artifacts.py", "apps/api/alembic/versions/0005_shared_quota_ledger.py", "apps/api/alembic/versions/0006_bigint_public_counters.py", "apps/api/alembic/versions/0007_media_bridge_assessment.py", "apps/api/alembic/versions/0008_snapshot_run_identity.py", "apps/api/alembic/versions/0009_comment_sample_identity.py",
    "apps/api/app/repositories/store.py", "apps/api/app/sources/youtube_api.py", "apps/api/app/sources/fixture_youtube.py",
    "apps/api/app/sources/browser.py", "apps/api/app/sources/fixture_browser.py", "apps/api/app/sources/router.py",
    "apps/api/app/research/planner.py", "apps/api/app/research/orchestrator.py", "apps/api/app/research/evidence_packets.py", "apps/api/app/analytics/metrics.py",
    "apps/api/app/analytics/clustering.py", "apps/api/app/analytics/idea_ceiling.py", "apps/api/app/analytics/recommendation.py", "apps/api/app/analytics/shorts.py", "apps/api/app/analytics/channel_performance.py", "apps/api/app/analytics/comparisons.py",
    "apps/api/app/ai/base.py", "apps/api/app/ai/fake.py", "apps/api/app/ai/deterministic_live.py", "apps/api/app/ai/ollama.py", "apps/api/app/ai/openrouter.py", "apps/api/app/ai/embeddings.py",
    "apps/api/app/sources/assets.py", "apps/api/app/sources/trends.py", "apps/api/app/reports/engine.py",
    "apps/api/app/sources/media_analysis.py", "apps/api/app/sources/ytdlp_youtube.py", "apps/api/app/research/preprocessing.py",
    "apps/api/app/storage/artifacts.py", "apps/api/app/services/jobs.py", "apps/api/app/services/health.py", "workers/research/worker.py", "scripts/cleanup_runtime.py",
    "apps/web/app/page.tsx", "apps/web/app/research/new/page.tsx", "apps/web/app/runs/[id]/page.tsx",
    "apps/web/app/runs/[id]/niches/[candidateId]/page.tsx", "apps/web/lib/api.ts", "apps/web/lib/schemas.ts",
    "fixtures/youtube_api/strong.json", "fixtures/youtube_api/one_hit.json", "fixtures/youtube_api/saturated.json",
    "fixtures/youtube_api/stale.json", "fixtures/browser/strong.json", "fixtures/browser/server.py", "fixtures/ai/strong.json",
    "apps/api/tests/test_analytics.py", "apps/api/tests/test_niche_intelligence.py", "apps/api/tests/test_sources.py", "apps/api/tests/test_openrouter.py", "tests/integration/test_pipeline.py",
    "apps/api/tests/test_preprocessing_media.py", "apps/api/tests/test_fixture_dates.py", "apps/api/tests/test_postgres_driver.py",
    "apps/api/tests/test_storage_lifecycle.py", "apps/api/tests/test_optional_sources.py",
    "apps/api/tests/test_browser_paths.py", "apps/api/tests/test_jobs.py", "apps/api/tests/test_health.py", "apps/api/tests/test_sqlite_runtime.py",
    "tests/integration/test_api.py", "tests/integration/test_browser_fixture.py", "tests/contract/test_contracts.py",
    "apps/web/tests/ui.test.tsx", "apps/web/tests/e2e/dashboard.spec.ts", "tests/e2e/dashboard.spec.ts",
    "scripts/live_smoke_test.py", "scripts/seed_demo.py", "scripts/closed_stack_probe.py",
]


def implementation_precheck() -> list[str]:
    return [path for path in REQUIRED_FILES if not (ROOT / path).exists()]


def frontend_prerequisite_errors() -> list[str]:
    errors: list[str] = []
    if shutil.which("node") is None:
        errors.append("node executable is not available")
    if shutil.which("npm") is None:
        errors.append("npm executable is not available")
    if shutil.which("node") is not None:
        version = subprocess.run(["node", "--version"], capture_output=True, text=True, check=False).stdout.strip()
        try:
            major = int(version.removeprefix("v").split(".", 1)[0])
        except ValueError:
            errors.append(f"could not determine the Node.js version from {version!r}")
        else:
            if not 20 <= major < 23:
                errors.append(f"Node.js {version} is unsupported; use the repository's Node 20/22 LTS range")
    modules = ROOT / "apps/web/node_modules"
    if not modules.is_dir():
        errors.append("apps/web/node_modules is missing; run `npm install` in apps/web")
    else:
        for executable in ("vitest", "next", "playwright"):
            if not (modules / ".bin" / executable).exists():
                errors.append(f"frontend dependency executable is missing: {executable}")
        if (modules / ".bin" / "playwright").exists():
            browser_check = subprocess.run(
                ["node", "-e", "const fs=require('node:fs'); const {chromium}=require('playwright'); process.exit(fs.existsSync(chromium.executablePath()) ? 0 : 1)"],
                cwd=ROOT / "apps/web",
                check=False,
            )
            if browser_check.returncode:
                errors.append("Playwright Chromium is missing; run `npx playwright install chromium` in apps/web")
    return errors


def compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, check=False).returncode == 0


def local_stack_prerequisite_errors() -> list[str]:
    required = {"redis-server": shutil.which("redis-server"), "arq": shutil.which("arq"), "uvicorn": shutil.which("uvicorn")}
    postgres_bins = sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    if not postgres_bins:
        required["PostgreSQL server tools"] = None
    return [f"{name} is required for the no-Docker full-stack fallback" for name, path in required.items() if path is None]


class LocalClosedStack:
    """Boot the same closed boundaries when Docker integration is unavailable."""

    def __init__(self, base_env: dict[str, str]) -> None:
        self.base_env = base_env
        self.temporary = tempfile.TemporaryDirectory(prefix="niche-finder-closed-")
        self.root = Path(self.temporary.name)
        self.processes: list[tuple[str, subprocess.Popen, object]] = []
        self.postgres_bin = sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)[0]
        self.database_url = "postgresql+psycopg://postgres@127.0.0.1:55432/nicheintel"
        self.redis_url = "redis://127.0.0.1:56379/0"

    def start(self) -> int:
        data_dir = self.root / "postgres"
        init = subprocess.run([
            str(self.postgres_bin / "initdb"), "-D", str(data_dir), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8",
        ], cwd=ROOT, env=self.base_env)
        if init.returncode:
            return init.returncode
        self._start("postgres", [str(self.postgres_bin / "postgres"), "-D", str(data_dir), "-h", "127.0.0.1", "-p", "55432", "-k", str(self.root)])
        if not self._wait_postgres():
            self._show_logs()
            return 1
        created = subprocess.run([
            str(self.postgres_bin / "createdb"), "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "nicheintel",
        ], cwd=ROOT, env=self.base_env)
        if created.returncode:
            return created.returncode
        self._start("redis", [shutil.which("redis-server") or "redis-server", "--port", "56379", "--bind", "127.0.0.1", "--save", "", "--appendonly", "no"])
        if not self._wait_redis():
            self._show_logs()
            return 1

        service_env = {
            **self.base_env,
            "APP_MODE": "closed_test",
            "AI_PROVIDER": "fake",
            "CLOSED_TEST_BLOCK_NETWORK": "true",
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "BROWSER_EXECUTABLE_PATH": self._chromium_path(),
            "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000",
            "PYTHONPATH": os.pathsep.join(filter(None, [site.getusersitepackages(), self.base_env.get("PYTHONPATH", "")])),
            "HOSTNAME": "127.0.0.1",
            "PORT": "3000",
        }
        migration = subprocess.run([sys.executable, "-m", "apps.api.app.db.migrate"], cwd=ROOT, env=service_env)
        if migration.returncode:
            return migration.returncode
        frontend_build = subprocess.run(["npm", "run", "build"], cwd=ROOT / "apps/web", env=service_env)
        if frontend_build.returncode:
            return frontend_build.returncode
        standalone_static = ROOT / "apps/web/.next/standalone/.next/static"
        shutil.copytree(ROOT / "apps/web/.next/static", standalone_static, dirs_exist_ok=True)
        self._start("fixture", [sys.executable, "-m", "uvicorn", "fixtures.browser.server:app", "--host", "127.0.0.1", "--port", "8765"], service_env)
        self._start("backend", [sys.executable, "-m", "uvicorn", "apps.api.app.main:app", "--host", "127.0.0.1", "--port", "8000"], service_env)
        self._start("worker", [shutil.which("arq") or "arq", "workers.research.worker.WorkerSettings"], service_env)
        self._start("frontend", ["node", ".next/standalone/server.js"], service_env, ROOT / "apps/web")
        for url in ("http://127.0.0.1:8765/health", "http://127.0.0.1:8000/health", "http://127.0.0.1:3000"):
            if not _wait_http(url):
                self._show_logs()
                return 1
        if any(process.poll() is not None for _, process, _ in self.processes):
            self._show_logs()
            return 1
        return 0

    def browser_probe(self) -> int:
        env = {
            **self.base_env,
            "BROWSER_EXECUTABLE_PATH": self._chromium_path(),
            "FIXTURE_BASE_URL": "http://127.0.0.1:8765",
        }
        result = subprocess.run([sys.executable, "scripts/closed_stack_probe.py"], cwd=ROOT, env=env).returncode
        if result:
            self._show_logs()
        return result

    def stop(self) -> None:
        for _, process, _ in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for _, process, _ in reversed(self.processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    print(f"closed-stack cleanup could not reap pid {process.pid}")
        for _, _, handle in self.processes:
            handle.close()
        self.temporary.cleanup()

    def _start(self, name: str, command: list[str], env: dict[str, str] | None = None, cwd: Path = ROOT) -> None:
        handle = (self.root / f"{name}.log").open("w+")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env or self.base_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.processes.append((name, process, handle))

    def _wait_postgres(self) -> bool:
        for _ in range(60):
            if subprocess.run([str(self.postgres_bin / "pg_isready"), "-h", "127.0.0.1", "-p", "55432"], capture_output=True).returncode == 0:
                return True
            time.sleep(.25)
        return False

    def _wait_redis(self) -> bool:
        for _ in range(60):
            if subprocess.run([shutil.which("redis-cli") or "redis-cli", "-p", "56379", "ping"], capture_output=True).returncode == 0:
                return True
            time.sleep(.25)
        return False

    def _chromium_path(self) -> str:
        result = subprocess.run([
            "node", "-e", "const {chromium}=require('playwright'); process.stdout.write(chromium.executablePath())",
        ], cwd=ROOT / "apps/web", capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def _show_logs(self) -> None:
        for name, _, handle in self.processes:
            handle.flush()
            content = (self.root / f"{name}.log").read_text(errors="replace")
            print(f"--- {name} log tail ---\n{content[-3000:]}")


def _wait_http(url: str) -> bool:
    for _ in range(120):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(.25)
    return False


def main() -> int:
    missing = implementation_precheck()
    if missing:
        print("IMPLEMENTATION INCOMPLETE")
        for path in missing:
            print(f" - {path}")
        return 2
    use_compose = compose_available()
    frontend_errors = frontend_prerequisite_errors()
    prerequisite_errors = frontend_errors if use_compose else [*frontend_errors, *local_stack_prerequisite_errors()]
    if prerequisite_errors:
        print("CLOSED TEST BLOCKED: full-stack prerequisites are required")
        for error in prerequisite_errors:
            print(f" - {error}")
        return 2
    os.environ["APP_MODE"] = "closed_test"
    os.environ["AI_PROVIDER"] = "fake"
    os.environ["CLOSED_TEST_BLOCK_NETWORK"] = "true"
    print("implementation precheck: PASS")
    print("closed mode: external networking blocked; live sources disabled")
    compose = ["docker", "compose", "--project-name", "niche-finder-closed-test"] if use_compose else None
    local_stack = None if use_compose else LocalClosedStack(os.environ.copy())
    if compose is not None:
        subprocess.run([*compose, "down", "--volumes", "--remove-orphans"], cwd=ROOT, check=False)
    else:
        print("Docker Compose unavailable; booting the strict local six-process stack")
    try:
        if compose is not None:
            stack_result = subprocess.run([*compose, "up", "--build", "--detach", "--wait"], cwd=ROOT, env=os.environ.copy()).returncode
            if stack_result == 0:
                stack_result = subprocess.run([*compose, "exec", "-T", "backend", "python", "-m", "apps.api.app.db.migrate"], cwd=ROOT, env=os.environ.copy()).returncode
            browser_probe = subprocess.run([*compose, "exec", "-T", "backend", "python", "scripts/closed_stack_probe.py"], cwd=ROOT, env=os.environ.copy()).returncode if stack_result == 0 else stack_result
        else:
            assert local_stack is not None
            stack_result = local_stack.start()
            browser_probe = local_stack.browser_probe() if stack_result == 0 else stack_result
        if stack_result:
            print("closed full stack or migration: FAIL")
            return stack_result
        if browser_probe:
            print("Chromium fixture-site integration: FAIL")
            return browser_probe

        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=os.environ.copy())
        if result.returncode:
            print("backend and integration suite: FAIL")
            return result.returncode
        smoke = subprocess.run(["node", "apps/web/tests/ui_smoke.mjs"], cwd=ROOT, env=os.environ.copy())
        if smoke.returncode:
            print("frontend closed smoke: FAIL")
            return smoke.returncode
        frontend_tests = subprocess.run(["npm", "test"], cwd=ROOT / "apps/web", env=os.environ.copy())
        if frontend_tests.returncode:
            print("frontend unit suite: FAIL")
            return frontend_tests.returncode
        if compose is not None:
            frontend_build = subprocess.run(["npm", "run", "build"], cwd=ROOT / "apps/web", env=os.environ.copy())
            if frontend_build.returncode:
                print("frontend type/build gate: FAIL")
                return frontend_build.returncode
        e2e_env = {**os.environ, "PLAYWRIGHT_EXTERNAL_SERVER": "true", "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000"}
        frontend_e2e = subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "apps/web", env=e2e_env)
        if frontend_e2e.returncode:
            if local_stack is not None:
                local_stack._show_logs()
            print("full-stack Playwright E2E: FAIL")
            return frontend_e2e.returncode
    finally:
        if compose is not None:
            subprocess.run([*compose, "down", "--volumes", "--remove-orphans"], cwd=ROOT, check=False)
        elif local_stack is not None:
            local_stack.stop()
    print("closed test summary: PASS")
    print(" - implementation precheck: PASS")
    print(" - backend/unit/integration/contract suite: PASS")
    print(" - browser fixture checks: PASS")
    print(" - frontend Vitest + static/UI smoke: PASS")
    print(" - frontend strict Next.js build: PASS")
    print(" - PostgreSQL + Redis + FastAPI + ARQ + fixture + Next.js: PASS")
    print(" - system Chromium -> fixture search/video/transcript: PASS")
    print(" - UI submission through completed report/evidence: PASS")
    print(" - live services contacted: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
