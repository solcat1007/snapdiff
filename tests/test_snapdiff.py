"""
Tests for SnapDiff — filesystem snapshot diff tool.
"""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from snapdiff import take_snapshot, diff_snapshots, Snapshot, DiffResult


class TestSnapshot(unittest.TestCase):
    """Test snapshot creation and storage."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, ".snapdiff_store")
        os.makedirs(self.storage, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_snapshot_captures_files(self):
        # Create test files
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "file1.txt").write_text("content1")
        Path(d, "subdir").mkdir()
        Path(d, "subdir", "nested.txt").write_text("nested content")

        snap = take_snapshot(d, "test", self.storage)
        self.assertEqual(len(snap.files), 2)
        self.assertIn("file1.txt", snap.files)
        self.assertIn("subdir/nested.txt", snap.files)

    def test_snapshot_hash(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "file.txt").write_text("hello world")

        snap = take_snapshot(d, "test", self.storage)
        self.assertIn("hash", snap.files["file.txt"])
        self.assertTrue(len(snap.files["file.txt"]["hash"]) > 0)

    def test_save_and_load(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "file.txt").write_text("content")

        snap = take_snapshot(d, "test", self.storage)
        loaded = Snapshot.load("test", self.storage)

        self.assertEqual(loaded.name, "test")
        self.assertEqual(len(loaded.files), 1)
        self.assertIn("file.txt", loaded.files)

    def test_empty_directory(self):
        d = os.path.join(self.tmpdir, "empty")
        os.makedirs(d)
        snap = take_snapshot(d, "empty", self.storage)
        self.assertEqual(len(snap.files), 0)


class TestDiff(unittest.TestCase):
    """Test snapshot diffing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, ".snapdiff_store")
        os.makedirs(self.storage, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_changes(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "file.txt").write_text("same content")

        snap1 = take_snapshot(d, "before", self.storage)
        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.added), 0)
        self.assertEqual(len(result.removed), 0)
        self.assertEqual(len(result.modified), 0)
        self.assertEqual(result.unchanged, 1)

    def test_added_file(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "existing.txt").write_text("old")

        snap1 = take_snapshot(d, "before", self.storage)

        Path(d, "new.txt").write_text("new")
        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.added), 1)
        self.assertIn("new.txt", result.added)

    def test_removed_file(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "keep.txt").write_text("keep")
        Path(d, "delete.txt").write_text("delete")

        snap1 = take_snapshot(d, "before", self.storage)

        os.remove(os.path.join(d, "delete.txt"))
        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.removed), 1)
        self.assertIn("delete.txt", result.removed)

    def test_modified_file(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "file.txt").write_text("original")

        snap1 = take_snapshot(d, "before", self.storage)

        Path(d, "file.txt").write_text("modified content")
        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.modified), 1)
        self.assertIn("file.txt", result.modified)

    def test_moved_file(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "old_name.txt").write_text("same content")

        snap1 = take_snapshot(d, "before", self.storage)

        os.rename(
            os.path.join(d, "old_name.txt"),
            os.path.join(d, "new_name.txt")
        )
        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.moved), 1)
        self.assertEqual(result.moved[0][0], "old_name.txt")
        self.assertEqual(result.moved[0][1], "new_name.txt")

    def test_multiple_changes(self):
        d = os.path.join(self.tmpdir, "testdir")
        os.makedirs(d)
        Path(d, "keep.txt").write_text("unchanged")
        Path(d, "remove.txt").write_text("remove me")
        Path(d, "modify.txt").write_text("original")

        snap1 = take_snapshot(d, "before", self.storage)

        os.remove(os.path.join(d, "remove.txt"))
        Path(d, "modify.txt").write_text("changed")
        Path(d, "added.txt").write_text("new file")

        snap2 = take_snapshot(d, "after", self.storage)

        result = diff_snapshots(snap1, snap2)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(len(result.removed), 1)
        self.assertEqual(len(result.modified), 1)
        self.assertEqual(result.unchanged, 1)


class TestSummary(unittest.TestCase):
    """Test summary output."""

    def test_summary_format(self):
        result = DiffResult()
        result.added = ["a.txt", "b.txt"]
        result.removed = ["c.txt"]
        result.modified = ["d.txt"]
        result.moved = [("e.txt", "f.txt")]
        result.unchanged = 10

        summary = result.summary()
        self.assertIn("Added:      2", summary)
        self.assertIn("Removed:    1", summary)
        self.assertIn("Modified:   1", summary)
        self.assertIn("Moved:      1", summary)
        self.assertIn("Unchanged:  10", summary)

    def test_detail_format(self):
        result = DiffResult()
        result.added = ["new.txt"]
        result.removed = ["old.txt"]
        result.modified = ["changed.txt"]

        detail = result.detail()
        self.assertIn("+ new.txt", detail)
        self.assertIn("- old.txt", detail)
        self.assertIn("~ changed.txt", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
