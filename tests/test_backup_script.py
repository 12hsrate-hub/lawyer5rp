from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.backup_web_data import create_backup
from tests.temp_helpers import make_temp_dir


class BackupScriptTests(unittest.TestCase):
    @patch("scripts.backup_web_data.subprocess.run")
    def test_create_backup_writes_manifest_and_postgres_dump(self, mock_run):
        tmpdir = Path(make_temp_dir())
        try:
            source_dir = tmpdir / "source"
            output_dir = tmpdir / "out"
            source_dir.mkdir(parents=True, exist_ok=True)

            def fake_pg_dump(command, check):
                self.assertTrue(check)
                dump_arg = next(item for item in command if str(item).startswith("--file="))
                dump_path = Path(str(dump_arg).split("=", 1)[1])
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_bytes(b"postgres-dump")

            mock_run.side_effect = fake_pg_dump

            text_path = source_dir / "users.json"
            text_path.write_text('{"ok": true}', encoding="utf-8")

            result = create_backup(
                source_dir,
                output_dir,
                keep=2,
                database_url="postgresql://user:secret@localhost:5432/app",
            )
            archive_path = Path(result["archive_path"])

            self.assertTrue(archive_path.exists())
            self.assertEqual(result["file_count"], 1)
            self.assertGreater(int(result["archive_size_bytes"]), 0)

            with ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("users.json", names)
                self.assertIn("postgres/database.dump", names)

                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest["database_backup"]["engine"], "postgresql")
                self.assertEqual(manifest["database_backup"]["artifact"], "postgres/database.dump")
                self.assertIn("localhost:5432/app", manifest["database_backup"]["database_url_masked"])
                self.assertEqual(archive.read("postgres/database.dump"), b"postgres-dump")
        finally:
            for path in sorted(tmpdir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                else:
                    path.rmdir()


if __name__ == "__main__":
    unittest.main()
