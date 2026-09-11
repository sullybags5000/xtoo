import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .extract import SUPPORTED, extract_text
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
            self.scan()
            self._wake.wait(self.settings.interval_seconds)

    def scan(self):
        if not self._scan_lock.acquire(blocking=False):
            return self.status()
        started = time.monotonic()
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
                    for name in sorted(files):
                        if self._stop.is_set():
                            break
                        path = Path(current) / name
                        if path.suffix.lower() not in SUPPORTED or name.startswith("~$"):
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
                            content = extract_text(path, self.settings.max_text_chars)
                            after = path.stat()
                            if (after.st_mtime_ns, after.st_size) != (
                                stat.st_mtime_ns,
                                stat.st_size,
                            ):
                                raise ValueError(
                                    "File changed during extraction; will retry next scan"
                                )
                            self.store.upsert(
                                path=key,
                                root=str(root),
                                title=path.name,
                                kind=path.suffix.lower()[1:],
                                modified_ns=stat.st_mtime_ns,
                                size=stat.st_size,
                                content=content,
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
        except Exception as exc:
            error("Index", exc)
        finally:
            self._update(
                running=False,
                last_finished=datetime.now(timezone.utc).isoformat(),
                duration_seconds=round(time.monotonic() - started, 2),
                **counters,
            )
            self._scan_lock.release()
        return self.status()
