from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.backup_web_data import create_backup
from tests.temp_helpers import make_temp_dir


class BackupScriptTests(unittest.TestCase):
    def test_create_backup_uses_sqlite_snapshot_and_writes_manifest(self):
        tmpdir = Path(make_temp_dir())
        try:
            source_dir = tmpdir / "source"
            output_dir = tmpdir / "out"
            source_dir.mkdir(parents=True, exist_ok=True)

            db_path = source_dir / "app.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)")
                conn.execute("INSERT INTO demo(value) VALUES ('alpha')")
                conn.commit()
            finally:
                conn.close()

            text_path = source_dir / "users.json"
            text_path.write_text('{"ok": true}', encoding="utf-8")

            result = create_backup(source_dir, output_dir, keep=2)
            archive_path = Path(result["archive_path"])

            self.assertTrue(archive_path.exists())
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["sqlite_snapshot_count"], 1)
            self.assertGreater(int(result["archive_size_bytes"]), 0)

            with ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("app.db", names)
                self.assertIn("users.json", names)

                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest["sqlite_snapshot_count"], 1)
                self.assertEqual(manifest["sqlite_snapshots"][0]["path"], "app.db")

                extracted_db = tmpdir / "restored.db"
                extracted_db.write_bytes(archive.read("app.db"))

            restored = sqlite3.connect(str(extracted_db))
            try:
                row = restored.execute("SELECT value FROM demo").fetchone()
            finally:
                restored.close()
            self.assertEqual(row[0], "alpha")
        finally:
            for path in sorted(tmpdir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                else:
                    path.rmdir()


if __name__ == "__main__":
    unittest.main()
