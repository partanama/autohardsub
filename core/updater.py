"""GitHub-based auto-update engine with atomic staging and rollback backups."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from core.i18n import tr
from core.paths import SUBPROCESS_NO_WINDOW, get_app_root, get_bundle_root, is_frozen

logger = logging.getLogger(__name__)

DEFAULT_VERSION_INFO: dict[str, str] = {
    "version": "1.0.0",
    "codename": "Jemboed Kecelup Santen",
    "changelog": "",
    "github_owner": "partanama",
    "github_repo": "autohardsub",
    "github_branch": "main",
}

_BACKUP_ITEMS: tuple[str, ...] = (
    "core",
    "workers",
    "ui",
    "main.py",
    "version.json",
    "requirements.txt",
)

_PRESERVED_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("assets", "bin"),
    ("assets", "models"),
    ("runtime_python",),
    ("_backup",),
    (".git",),
)

_ALLOWED_ROOT_FILES: set[str] = {
    "version.json",
    "requirements.txt",
}

_USER_AGENT = "AutoHardsub-Updater/1.0"


def load_local_version(app_root: Path | None = None) -> dict[str, str]:
    """Read local version.json with safe fallback defaults."""
    candidates: list[Path] = []
    if app_root is not None:
        candidates.append(Path(app_root) / "version.json")
    else:
        candidates.append(get_app_root() / "version.json")
        bundle_candidate = get_bundle_root() / "version.json"
        if bundle_candidate not in candidates:
            candidates.append(bundle_candidate)

    data = dict(DEFAULT_VERSION_INFO)
    for path in candidates:
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key in DEFAULT_VERSION_INFO:
                        val = loaded.get(key)
                        if isinstance(val, str) and val.strip():
                            data[key] = val.strip()
                break
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to read %s: %s", path, exc)
    return data


def parse_semver(version_str: str) -> tuple[int, ...]:
    """Parse a semantic version string (e.g. '1.2.3' or 'v1.2.3') into a comparable tuple."""
    cleaned = version_str.strip().lstrip("vV")
    core_part = cleaned.split("-", 1)[0].split("+", 1)[0]
    numbers = re.findall(r"\d+", core_part)
    if not numbers:
        return (0, 0, 0)
    parts = [int(n) for n in numbers]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(remote_version: str, local_version: str) -> bool:
    """Return True when remote_version is strictly greater than local_version."""
    return parse_semver(remote_version) > parse_semver(local_version)


def _is_preserved_path(rel_parts: tuple[str, ...]) -> bool:
    lower_parts = tuple(p.lower() for p in rel_parts)
    for prefix in _PRESERVED_PREFIXES:
        if lower_parts[: len(prefix)] == prefix:
            return True
    return False


def _is_updatable_file(rel_path: Path) -> bool:
    """Return True only for lightweight project files allowed to be overwritten."""
    parts = rel_path.parts
    if not parts or _is_preserved_path(parts):
        return False

    lower_parts = tuple(p.lower() for p in parts)
    if "__pycache__" in lower_parts:
        return False

    if len(parts) == 1 and lower_parts[0] in _ALLOWED_ROOT_FILES:
        return True

    if rel_path.suffix.lower() == ".py":
        return True

    if len(parts) >= 3 and lower_parts[0] == "assets" and lower_parts[1] == "fonts":
        return True

    return False


def restart_application(app_root: Path | None = None) -> None:
    """Spawn a fresh instance of AutoHardsub so the current process can exit cleanly."""
    root = Path(app_root) if app_root is not None else get_app_root()
    extra_args = sys.argv[1:]

    if is_frozen():
        cmd = [sys.executable, *extra_args]
    else:
        main_script = root / "main.py"
        cmd = [sys.executable, str(main_script), *extra_args]

    kwargs: dict[str, Any] = {"cwd": str(root)}
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if Path(sys.executable).name.lower() == "pythonw.exe":
            creationflags |= SUBPROCESS_NO_WINDOW
        kwargs["creationflags"] = creationflags

    subprocess.Popen(cmd, **kwargs)


class UpdateCheckWorker(QThread):
    """Background worker that checks GitHub for a newer AutoHardsub release."""

    update_available = Signal(dict)
    up_to_date = Signal(dict)
    check_failed = Signal(str)

    def __init__(
        self,
        *,
        silent: bool = True,
        timeout: float = 5.0,
        app_root: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._silent = silent
        self._timeout = timeout
        self._app_root = Path(app_root) if app_root is not None else get_app_root()

    @property
    def is_silent(self) -> bool:
        return self._silent

    def run(self) -> None:
        local_info = load_local_version(self._app_root)
        owner = local_info["github_owner"]
        repo = local_info["github_repo"]
        branch = local_info["github_branch"]
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/version.json"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw_bytes = resp.read()
            remote_raw = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(remote_raw, dict) or not remote_raw.get("version"):
                raise ValueError("Invalid remote version.json payload.")

            remote_info: dict[str, Any] = {
                "version": str(remote_raw.get("version", "")).strip(),
                "codename": str(
                    remote_raw.get("codename", local_info["codename"])
                ).strip(),
                "changelog": str(remote_raw.get("changelog", "")).strip(),
                "github_owner": str(
                    remote_raw.get("github_owner", owner)
                ).strip() or owner,
                "github_repo": str(
                    remote_raw.get("github_repo", repo)
                ).strip() or repo,
                "github_branch": str(
                    remote_raw.get("github_branch", branch)
                ).strip() or branch,
                "local_version": local_info["version"],
                "silent": self._silent,
            }

            if is_newer_version(remote_info["version"], local_info["version"]):
                self.update_available.emit(remote_info)
            else:
                self.up_to_date.emit(remote_info)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            logger.info("Update check skipped/failed (%s): %s", url, exc)
            self.check_failed.emit(str(exc))


class UpdateInstallWorker(QThread):
    """Downloads, verifies, and applies a GitHub source update with automatic rollback."""

    progress_changed = Signal(int)
    status_changed = Signal(str)
    install_finished = Signal(dict)
    install_failed = Signal(str)

    def __init__(
        self,
        remote_info: dict[str, Any],
        *,
        lang: str = "id",
        timeout: float = 30.0,
        app_root: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._remote_info = dict(remote_info)
        self._lang = lang
        self._timeout = timeout
        self._app_root = Path(app_root) if app_root is not None else get_app_root()

    def _t(self, key: str, **kwargs: Any) -> str:
        return tr(self._lang, key, **kwargs)

    def _create_backup(self, backup_dir: Path) -> None:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

        for item_name in _BACKUP_ITEMS:
            src = self._app_root / item_name
            dst = backup_dir / item_name
            if not src.exists():
                continue
            if src.is_dir():
                shutil.copytree(
                    src,
                    dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _restore_backup(self, backup_dir: Path) -> None:
        if not backup_dir.is_dir():
            return
        for item_name in _BACKUP_ITEMS:
            src = backup_dir / item_name
            dst = self._app_root / item_name
            if not src.exists():
                continue
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _download_archive(self, url: str, dest_zip: Path) -> None:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            total_header = resp.headers.get("Content-Length")
            total_bytes = int(total_header) if total_header and total_header.isdigit() else 0
            downloaded = 0
            chunk_size = 64 * 1024

            with dest_zip.open("wb") as out_file:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = 15 + int((downloaded / total_bytes) * 45)
                        self.progress_changed.emit(min(60, pct))

    def _find_extracted_root(self, staging_dir: Path) -> Path:
        entries = [p for p in staging_dir.iterdir() if p.is_dir()]
        if len(entries) == 1:
            return entries[0]
        return staging_dir

    def _apply_extracted_files(self, extracted_root: Path) -> int:
        copied = 0
        for src_file in extracted_root.rglob("*"):
            if not src_file.is_file():
                continue
            rel_path = src_file.relative_to(extracted_root)
            if not _is_updatable_file(rel_path):
                continue
            dst_file = self._app_root / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
        if copied == 0:
            raise RuntimeError("Archive did not contain any updatable application files.")
        return copied

    def _install_dependencies_if_needed(self, old_req_text: str) -> None:
        req_file = self._app_root / "requirements.txt"
        if not req_file.is_file():
            return
        new_req_text = req_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not new_req_text or new_req_text == old_req_text.strip():
            return

        self.status_changed.emit(self._t("update_status_pip"))
        self.progress_changed.emit(85)

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(req_file),
            "--quiet",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(self._app_root),
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_NO_WINDOW if sys.platform == "win32" else 0,
            timeout=300,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"pip install failed (code {result.returncode}): {detail}")

    def run(self) -> None:
        backup_dir = self._app_root / "_backup"
        temp_dir = Path(tempfile.mkdtemp(prefix="autohardsub_update_"))
        backup_created = False

        local_info = load_local_version(self._app_root)
        owner = str(self._remote_info.get("github_owner") or local_info["github_owner"])
        repo = str(self._remote_info.get("github_repo") or local_info["github_repo"])
        branch = str(self._remote_info.get("github_branch") or local_info["github_branch"])
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

        old_req_file = self._app_root / "requirements.txt"
        old_req_text = (
            old_req_file.read_text(encoding="utf-8", errors="ignore")
            if old_req_file.is_file()
            else ""
        )

        try:
            self.progress_changed.emit(5)
            self.status_changed.emit(self._t("update_status_backup"))
            self._create_backup(backup_dir)
            backup_created = True

            self.progress_changed.emit(15)
            self.status_changed.emit(self._t("update_status_downloading"))
            zip_path = temp_dir / "source.zip"
            self._download_archive(zip_url, zip_path)

            self.progress_changed.emit(65)
            self.status_changed.emit(self._t("update_status_extracting"))
            staging_dir = temp_dir / "extracted"
            staging_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(staging_dir)

            extracted_root = self._find_extracted_root(staging_dir)
            self._apply_extracted_files(extracted_root)

            self.progress_changed.emit(80)
            self._install_dependencies_if_needed(old_req_text)

            self.progress_changed.emit(100)
            self.status_changed.emit(self._t("update_status_done"))
            self.install_finished.emit(self._remote_info)
        except Exception as exc:
            logger.exception("Auto-update failed: %s", exc)
            if backup_created:
                try:
                    self._restore_backup(backup_dir)
                except Exception as restore_exc:
                    logger.exception("Rollback from _backup/ failed: %s", restore_exc)
            self.install_failed.emit(str(exc))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
