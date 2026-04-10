from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from shared.ogp_temp import get_named_temp_root


TEST_TEMP_ROOT = get_named_temp_root("tests")


class ManagedTempDirectory:
    def __init__(self, path: Path):
        self.name = str(path)
        self._path = path

    def cleanup(self) -> None:
        shutil.rmtree(self._path, ignore_errors=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()


def _create_temp_path() -> Path:
    path = TEST_TEMP_ROOT / f"tmp{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def make_temp_dir() -> str:
    return str(_create_temp_path())


def make_temporary_directory() -> ManagedTempDirectory:
    return ManagedTempDirectory(_create_temp_path())


def get_test_temp_root() -> Path:
    return TEST_TEMP_ROOT
