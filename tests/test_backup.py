"""Check that complete collection ZIPs can be recovered outside the source."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from kbforge.backup import backup_collections
from kbforge.repository import initialize_collection


class BackupTest(unittest.TestCase):
    def test_archive_and_restore_multiple_collections(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            collections = root / "collections"
            collections.mkdir()
            for name in ("first", "second"):
                collection = collections / name
                initialize_collection(collection, name, "DOC", 5, "en-US")
                asset = collection / "branding" / "asset.txt"
                asset.parent.mkdir()
                asset.write_bytes(name.encode())
            (collections / "unrelated").mkdir()
            output = root / "backup.zip"
            self.assertEqual(
                backup_collections(collections, output, all_collections=True), 2
            )
            recovered = root / "restored"
            with ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                archive.extractall(recovered)
            for name in ("first", "second"):
                original, restored = collections / name, recovered / name
                self.assertTrue((restored / "articles").is_dir())
                for path in ("kbforge.yaml", "registry/ids.yaml", "branding/asset.txt"):
                    self.assertEqual(
                        (restored / path).read_bytes(), (original / path).read_bytes()
                    )
            with self.assertRaises(FileExistsError):
                backup_collections(collections / "first", output)
            with self.assertRaisesRegex(ValueError, "outside"):
                backup_collections(
                    collections / "first", collections / "first/copy.zip"
                )

    def test_symlink_cannot_leak_an_external_file_into_backup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection"
            initialize_collection(collection, "Collection", "DOC", 5, "en-US")
            outside = root / "external.txt"
            outside.write_text("external file", encoding="utf-8")
            try:
                (collection / "link.txt").symlink_to(outside)
            except OSError:
                self.skipTest("Creating symbolic links is unavailable")
            output = root / "backup.zip"
            with self.assertRaisesRegex(ValueError, "symlink"):
                backup_collections(collection, output)
            self.assertFalse(output.exists())
