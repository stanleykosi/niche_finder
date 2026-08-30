"""Bounded runtime storage with recoverable evidence metadata."""

from __future__ import annotations

import hashlib
import fcntl
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core.config import Settings
from ..core.errors import ErrorCode, NicheIntelError
from ..repositories.store import ResearchRepository


@dataclass(frozen=True)
class CleanupResult:
    files_deleted: int = 0
    bytes_reclaimed: int = 0
    directories_deleted: int = 0


@dataclass(frozen=True)
class DownloadReservation:
    """Cross-process storage capacity claim released after raw media cleanup."""

    token_path: Path
    reserved_bytes: int


class RuntimeArtifactManager:
    def __init__(self, settings: Settings, repository: ResearchRepository | None = None) -> None:
        self.settings = settings
        self.repository = repository
        self.media_root = Path(settings.media_work_root).resolve()
        self.browser_root = Path(settings.browser_profile_root).resolve()
        _validate_artifact_roots(self.media_root, self.browser_root)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.browser_root.mkdir(parents=True, exist_ok=True)
        self.control_root = self.media_root / ".control"
        self.control_root.mkdir(parents=True, exist_ok=True)

    def run_workspace(self, run_id: str) -> dict[str, Path]:
        safe_run_id = _safe_component(run_id)
        root = self.media_root / safe_run_id
        paths = {"root": root, "downloads": root / "downloads", "frames": root / "frames", "temporary": root / "temporary"}
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def reserve_download(self, expected_bytes: int | None = None) -> DownloadReservation:
        self.cleanup_expired()
        reserve = expected_bytes or self.settings.media_unknown_download_reserve_mb * 1024 * 1024
        if reserve <= 0:
            raise ValueError("download reservation must be positive")
        with self._reservation_lock():
            outstanding = self._remove_stale_and_sum_reservations()
            usage = _directory_size(self.media_root, exclude_control=True)
            limit = int(self.settings.media_max_storage_gb * 1024**3)
            free = shutil.disk_usage(self.media_root).free
            minimum_free = int(self.settings.media_min_free_disk_gb * 1024**3)
            if usage + outstanding + reserve > limit:
                raise NicheIntelError("runtime media storage ceiling would be exceeded", ErrorCode.SOURCE_UNAVAILABLE)
            if free - outstanding - reserve < minimum_free:
                raise NicheIntelError("insufficient free disk space for bounded media analysis", ErrorCode.SOURCE_UNAVAILABLE)
            token_path = self.control_root / f"{uuid.uuid4().hex}.reserve"
            token_path.write_text(str(reserve), encoding="utf-8")
            return DownloadReservation(token_path, reserve)

    def release_download(self, reservation: DownloadReservation | None) -> None:
        if reservation is None:
            return
        resolved = reservation.token_path.resolve()
        if not _is_relative_to(resolved, self.control_root) or resolved.suffix != ".reserve":
            raise ValueError("invalid download reservation token")
        with self._reservation_lock():
            resolved.unlink(missing_ok=True)

    def register(self, path: Path, artifact_type: str, run_id: str | None, retention_hours: int | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = path.resolve()
        self._validate_managed_path(resolved)
        now = datetime.now(timezone.utc)
        payload = {
            "research_run_id": run_id,
            "artifact_type": artifact_type,
            "path": str(resolved),
            "sha256": _sha256(resolved) if resolved.is_file() else None,
            "size_bytes": resolved.stat().st_size if resolved.is_file() else 0,
            "state": "available" if resolved.exists() else "missing",
            "metadata_payload": metadata or {},
            "created_at": now,
            "expires_at": now + timedelta(hours=retention_hours) if retention_hours is not None else None,
            "deleted_at": None,
        }
        if self.repository is not None:
            self.repository.upsert_runtime_artifact(payload)
        return payload

    def delete(self, path: Path) -> int:
        resolved = path.resolve()
        self._validate_managed_path(resolved)
        size = resolved.stat().st_size if resolved.is_file() else 0
        if resolved.is_file() or resolved.is_symlink():
            resolved.unlink(missing_ok=True)
        elif resolved.is_dir():
            shutil.rmtree(resolved)
        if self.repository is not None:
            self.repository.mark_runtime_artifact_deleted(str(resolved), datetime.now(timezone.utc))
        return size

    def cleanup_expired(self, now: datetime | None = None) -> CleanupResult:
        observed = now or datetime.now(timezone.utc)
        deleted = reclaimed = directories = 0
        if self.repository is not None:
            for artifact in self.repository.runtime_artifacts(available_only=True):
                expires = _aware(artifact.expires_at)
                if expires is not None and expires <= observed:
                    path = Path(artifact.path)
                    if path.exists():
                        reclaimed += self.delete(path)
                        deleted += 1
                    else:
                        self.repository.mark_runtime_artifact_deleted(str(path.resolve()), observed)
        cutoff = observed.timestamp() - self.settings.media_derived_retention_hours * 3600
        for path in self.media_root.rglob("*"):
            if _is_relative_to(path, self.control_root):
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    reclaimed += self.delete(path)
                    deleted += 1
            except FileNotFoundError:
                continue
        screenshot_cutoff = observed.timestamp() - self.settings.browser_artifact_retention_hours * 3600
        profile_cutoff = observed.timestamp() - self.settings.browser_profile_retention_days * 86400
        for path in self.browser_root.rglob("*"):
            try:
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.stat().st_mtime < screenshot_cutoff:
                    reclaimed += path.stat().st_size
                    path.unlink(missing_ok=True)
                    deleted += 1
            except FileNotFoundError:
                continue
        for path in self.browser_root.iterdir():
            try:
                if path.is_dir() and path.stat().st_mtime < profile_cutoff:
                    shutil.rmtree(path)
                    directories += 1
            except FileNotFoundError:
                continue
        _remove_empty_directories(self.media_root)
        return CleanupResult(deleted, reclaimed, directories)

    def cleanup_run_temporary(self, run_id: str) -> CleanupResult:
        root = self.media_root / _safe_component(run_id)
        paths = {"downloads": root / "downloads", "temporary": root / "temporary"}
        deleted = reclaimed = 0
        for directory in (paths["downloads"], paths["temporary"]):
            if not directory.exists():
                continue
            for path in list(directory.rglob("*")):
                if path.is_file():
                    reclaimed += self.delete(path)
                    deleted += 1
            _remove_empty_directories(directory)
        return CleanupResult(deleted, reclaimed, 0)

    def status(self) -> dict[str, Any]:
        usage = _directory_size(self.media_root, exclude_control=True)
        with self._reservation_lock():
            reserved = self._remove_stale_and_sum_reservations()
        free = shutil.disk_usage(self.media_root).free
        artifacts = self.repository.runtime_artifacts() if self.repository is not None else []
        return {
            "media_root": str(self.media_root),
            "usage_bytes": usage,
            "reserved_download_bytes": reserved,
            "maximum_bytes": int(self.settings.media_max_storage_gb * 1024**3),
            "free_disk_bytes": free,
            "minimum_free_disk_bytes": int(self.settings.media_min_free_disk_gb * 1024**3),
            "available_artifacts": sum(item.state == "available" for item in artifacts),
            "deleted_artifacts": sum(item.state == "deleted" for item in artifacts),
            "raw_delete_after_analysis": True,
            "derived_retention_hours": self.settings.media_derived_retention_hours,
        }

    def _validate_managed_path(self, path: Path) -> None:
        if path in {self.media_root, self.browser_root, self.control_root}:
            raise ValueError(f"refusing to delete an artifact root: {path}")
        if not (_is_relative_to(path, self.media_root) or _is_relative_to(path, self.browser_root)):
            raise ValueError(f"refusing to manage artifact outside runtime roots: {path}")

    @contextmanager
    def _reservation_lock(self) -> Any:
        lock_path = self.control_root / "download.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _remove_stale_and_sum_reservations(self) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        total = 0
        for token in self.control_root.glob("*.reserve"):
            try:
                if token.stat().st_mtime < cutoff:
                    token.unlink(missing_ok=True)
                    continue
                total += max(0, int(token.read_text(encoding="utf-8").strip()))
            except (FileNotFoundError, OSError, ValueError):
                token.unlink(missing_ok=True)
        return total


def _directory_size(root: Path, exclude_control: bool = False) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not (exclude_control and ".control" in path.relative_to(root).parts):
                total += path.stat().st_size
        except FileNotFoundError:
            continue
    return total


def _validate_artifact_roots(media_root: Path, browser_root: Path) -> None:
    forbidden = {Path(media_root.anchor), Path.cwd().resolve(), Path.home().resolve(), Path("/tmp").resolve()}
    if media_root in forbidden or browser_root in forbidden:
        raise ValueError("artifact roots must be dedicated child directories")
    if len(media_root.parts) < 3 or len(browser_root.parts) < 3:
        raise ValueError("artifact roots must be dedicated child directories")
    if any(
        not any(part in {"runtime", ".runtime"} for part in root.parts[:-1])
        for root in (media_root, browser_root)
    ):
        raise ValueError("artifact roots must live beneath a dedicated runtime directory")
    if media_root == browser_root or media_root in browser_root.parents or browser_root in media_root.parents:
        raise ValueError("artifact roots must be separate, non-nested directories")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_empty_directories(root: Path) -> None:
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        if ".control" in path.relative_to(root).parts:
            continue
        try:
            path.rmdir()
        except OSError:
            pass


def _safe_component(value: str) -> str:
    cleaned = "".join(character for character in value if character.isalnum() or character in {"-", "_"})
    if not cleaned:
        raise ValueError("run ID contains no safe path characters")
    return cleaned


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
