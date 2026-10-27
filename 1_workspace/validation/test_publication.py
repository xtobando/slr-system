"""Check that publishing source cannot silently export a live review."""
import importlib.util
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid

PROJECT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prepare_publication", PROJECT / "1_workspace/validation/prepare_publication.py")
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-publication-", dir=PROJECT / "1_workspace/validation")
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name).resolve() / "source"
        self.destination = self.source / "1_workspace/.publication/release"
        for name in publication.SOURCE_FILES:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, target)
        for name in publication.TEMPLATES:
            target = self.destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("% Empty bibliography\n" if name.endswith(".bib") else "# Empty review template\n", encoding="utf-8")
        with closing(sqlite3.connect(self.destination / "1_workspace/slr_state.sqlite")) as connection:
            for table in ("papers", "screening", "extractions", "audit_log"):
                connection.execute(f"CREATE TABLE {table} (value TEXT)")
            connection.commit()
        publication.git(self.destination, "init", "--quiet")
        self.commit()
        publication.git(self.destination, "update-ref", "refs/remotes/origin/main", "HEAD")

    def commit(self):
        publication.git(self.destination, "add", "--all")
        publication.git(self.destination, "-c", "user.name=Validation",
                        "-c", "user.email=validation@example.invalid", "commit", "--quiet", "-m", "Fixture")

    def test_source_export_omits_live_review_and_secrets(self):
        private = uuid.uuid4().hex
        (self.source / ".env").write_text("API_KEY=" + private, encoding="utf-8")
        (self.source / "1_workspace/protocol.md").write_text(private, encoding="utf-8")
        (self.source / "1_workspace/signed.pdf").write_bytes(private.encode())
        publication.prepare(self.source, self.destination)
        self.assertFalse((self.destination / ".env").exists())
        self.assertFalse((self.destination / "1_workspace/signed.pdf").exists())
        self.assertNotIn(private, (self.destination / "1_workspace/system_source.md").read_text(encoding="utf-8"))
        with closing(sqlite3.connect(self.destination / "1_workspace/slr_state.sqlite")) as connection:
            for table in ("papers", "screening", "extractions", "audit_log"):
                self.assertEqual(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual((self.source / "1_workspace/protocol.md").read_text(encoding="utf-8"), private)

    def test_dirty_destination_is_preserved(self):
        path = self.destination / "1_workspace/protocol.md"
        path.write_text("existing unsaved edits", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "clean"):
            publication.prepare(self.source, self.destination)
        self.assertEqual(path.read_text(encoding="utf-8"), "existing unsaved edits")

    def test_nonempty_upstream_database_is_rejected(self):
        with closing(sqlite3.connect(self.destination / "1_workspace/slr_state.sqlite")) as connection:
            connection.execute("INSERT INTO papers VALUES ('private study')")
            connection.commit()
        self.commit()
        publication.git(self.destination, "update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(ValueError, "not empty"):
            publication.prepare(self.source, self.destination)


if __name__ == "__main__":
    unittest.main()
