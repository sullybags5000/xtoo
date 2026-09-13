import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .enrich import enrichment
from .extract import extract_text
from .store import Store


class Indexer:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self._lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._state = {"running": False, "last_finished": None, "errors": [], "error_count": 0}

    def status(self):
        with self._lock:
            return {**self._state, "errors": list(self._state["errors"])}

    def _update(self, **fields):
        with self._lock:
            self._state.update(fields)

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="xtoo-indexer", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def request_scan(self):
        self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            self._wake.clear()
            self.scan(full=self._full_due())
            self._wake.wait(self.settings.interval_seconds)

    def _full_due(self) -> bool:
        """A full scan is due if one has not finished within the configured window."""
        last = self.store.recall("last_full_scan")
        try:
            return (time.time() - float(last)) > self.settings.full_scan_hours * 3600
        except ValueError:
            return True

    def scan(self, full: bool = True):
        """Look for work. A full scan examines every file; a quick one trusts a folder
        whose timestamp has not moved, which is what makes scanning a large export
        cheap enough to repeat often. A folder's timestamp changes when files are added
        or removed but not when one is edited, so a full scan still has to happen
        regularly; the background loop arranges that."""
        if not self._scan_lock.acquire(blocking=False):
            return self.status()
        started = time.monotonic()
        supported = self.settings.supported_extensions
        text_extensions = self.settings.text_extensions
        counters = {"indexed": 0, "unchanged": 0, "skipped": 0, "removed": 0}
        errors = []
        error_count = 0

        def error(path, exc):
            nonlocal error_count
            error_count += 1
            if len(errors) < 20:
                errors.append({"path": str(path), "message": str(exc)})
            self._update(errors=list(errors), error_count=error_count)

        self._update(running=True, errors=[], error_count=0, **counters)
        try:
            self.store.retain_roots({str(p) for p in self.settings.folders})
            for root in self.settings.folders:
                if self._stop.is_set():
                    break
                if not root.is_dir():
                    error(
                        root, "Folder unavailable. Previous results are retained until it returns."
                    )
                    continue
                old = self.store.inventory(str(root))
                known_times = {} if full else self.store.folder_times(str(root))
                folder_times = {}
                seen = set()
                walk_failed = False

                def walk_error(exc):
                    nonlocal walk_failed
                    walk_failed = True
                    error(exc.filename, exc)

                for current, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
                    if self._stop.is_set():
                        break
                    dirs[:] = sorted(
                        d
                        for d in dirs
                        if (
                            d not in self.settings.excluded_dirs
                            and not (Path(current) / d).is_symlink()
                            and (Path(current) / d).resolve() != self.settings.data_dir
                        )
                    )
                    try:
                        folder_times[current] = os.stat(current).st_mtime_ns
                    except OSError as exc:
                        folder_times.pop(current, None)
                        error(current, exc)
                    if known_times.get(current, -1) == folder_times.get(current, -2):
                        # Nothing was added or removed here since the last full scan.
                        unchanged = self.store.paths_under(str(root), current)
                        seen.update(unchanged)
                        counters["unchanged"] += len(unchanged)
                        self._update(**counters)
                        continue
                    for name in sorted(files):
                        if self._stop.is_set():
                            break
                        path = Path(current) / name
                        if path.suffix.lower() not in supported or name.startswith("~$"):
                            continue
                        key = str(path)
                        if path.is_symlink():
                            continue
                        seen.add(key)
                        try:
                            stat = path.stat()
                            if stat.st_size > self.settings.max_file_mb * 1024 * 1024:
                                counters["skipped"] += 1
                                self.store.remove([key])
                                continue
                            if old.get(key) == (stat.st_mtime_ns, stat.st_size):
                                counters["unchanged"] += 1
                                continue
                            content = extract_text(
                                path,
                                self.settings.max_text_chars,
                                text_extensions,
                                self.settings.attachment_chars,
                            )
                            after = path.stat()
                            if (after.st_mtime_ns, after.st_size) != (
                                stat.st_mtime_ns,
                                stat.st_size,
                            ):
                                raise ValueError(
                                    "File changed during extraction; will retry next scan"
                                )
                            kind = path.suffix.lower()[1:]
                            self.store.upsert(
                                path=key,
                                root=str(root),
                                title=path.name,
                                kind=kind,
                                modified_ns=stat.st_mtime_ns,
                                size=stat.st_size,
                                content=content,
                                **enrichment(content, path.name, kind, stat.st_mtime_ns),
                            )
                            counters["indexed"] += 1
                        except Exception as exc:
                            # Do not continue serving old text after a failed refresh.
                            self.store.remove([key])
                            error(path, exc)
                        finally:
                            self._update(**counters)
                if not walk_failed and not self._stop.is_set():
                    missing = old.keys() - seen
                    self.store.remove(missing)
                    counters["removed"] += len(missing)
                    self.store.record_folders(str(root), folder_times)
        except Exception as exc:
            error("Index", exc)
        finally:
            if full and not self._stop.is_set():
                self.store.remember("last_full_scan", time.time())
            self._update(
                running=False,
                last_finished=datetime.now(timezone.utc).isoformat(),
                duration_seconds=round(time.monotonic() - started, 2),
                **counters,
            )
            self._scan_lock.release()
        return self.status()
