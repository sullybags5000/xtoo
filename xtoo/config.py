import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from .extract import DOCUMENT_EXTENSIONS, MARKUP_EXTENSIONS, SCRIPT_EXTENSIONS, TEXT_EXTENSIONS


def config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "xtoo/config.toml"


def data_path() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "xtoo"


@dataclass(frozen=True)
class Settings:
    folders: tuple[Path, ...]
    data_dir: Path
    interval_seconds: int = 300
    max_file_mb: int = 25
    max_text_chars: int = 1_000_000
    excluded_dirs: tuple[str, ...] = (
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "AppData",
        "$Recycle.Bin",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "site-packages",
        ".terraform",
        ".idea",
        ".vs",
    )
    extra_text_extensions: tuple[str, ...] = ()

    @property
    def text_extensions(self) -> frozenset[str]:
        """Extensions decoded as plain text, including scripts and user additions."""
        return frozenset(TEXT_EXTENSIONS | SCRIPT_EXTENSIONS | set(self.extra_text_extensions))

    @property
    def supported_extensions(self) -> frozenset[str]:
        return self.text_extensions | MARKUP_EXTENSIONS | DOCUMENT_EXTENSIONS


def load_settings(path: Path) -> Settings:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    allowed = {
        "folders",
        "data_dir",
        "interval_seconds",
        "max_file_mb",
        "excluded_dirs",
        "extra_text_extensions",
    }
    if unknown := raw.keys() - allowed:
        raise ValueError(f"Unknown configuration options: {', '.join(sorted(unknown))}")
    folders = raw.get("folders", [])
    if (
        not isinstance(folders, list)
        or not folders
        or not all(isinstance(p, str) and p.strip() for p in folders)
    ):
        raise ValueError("Configure at least one folder in the folders list.")
    paths = tuple(dict.fromkeys(Path(p).expanduser().resolve() for p in folders))
    # Avoid indexing a nested source twice. Missing mounts are reported by the indexer.
    paths = tuple(
        p for p in paths if not any(p != other and p.is_relative_to(other) for other in paths)
    )
    for key, default, minimum in (("interval_seconds", 300, 10), ("max_file_mb", 25, 1)):
        value = raw.get(key, default)
        if type(value) is not int or value < minimum:
            raise ValueError(f"{key} must be an integer of at least {minimum}.")
    excludes = raw.get("excluded_dirs", list(Settings.excluded_dirs))
    if not isinstance(excludes, list) or not all(isinstance(s, str) for s in excludes):
        raise ValueError("excluded_dirs must be a list of directory names.")
    extras = raw.get("extra_text_extensions", [])
    if not isinstance(extras, list) or not all(isinstance(s, str) and s.strip() for s in extras):
        raise ValueError("extra_text_extensions must be a list of extensions such as '.psm1'.")
    extras = tuple(dict.fromkeys("." + s.strip().lower().lstrip(".") for s in extras))
    if invalid := [s for s in extras if s in DOCUMENT_EXTENSIONS | MARKUP_EXTENSIONS]:
        raise ValueError(
            f"These extensions already have a dedicated parser: {', '.join(sorted(invalid))}."
        )
    if "data_dir" in raw and (not isinstance(raw["data_dir"], str) or not raw["data_dir"].strip()):
        raise ValueError("data_dir must be a nonempty path string.")
    return Settings(
        folders=paths,
        data_dir=Path(raw.get("data_dir", str(data_path()))).expanduser().resolve(),
        interval_seconds=raw.get("interval_seconds", 300),
        max_file_mb=raw.get("max_file_mb", 25),
        excluded_dirs=tuple(excludes),
        extra_text_extensions=extras,
    )
