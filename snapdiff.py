#!/usr/bin/env python3
"""
SnapDiff — Filesystem snapshot and diff tool. Zero dependencies.

Snapshots a directory tree (file paths + sizes + hashes) and compares
two snapshots to show what was added, removed, modified, or moved.

Usage:
    snapdiff snapshot /path/to/dir --name before      Take snapshot
    snapdiff snapshot /path/to/dir --name after       Take another
    snapdiff diff before after                         Compare snapshots
    snapdiff diff before after --summary               Summary only
    snapdiff diff before after --modified              Only modifications
    snapdiff list                                       List saved snapshots
    snapdiff watch /path --interval 5                   Live monitoring

Snapshots are stored as JSON files in ~/.snapdiff/

Author: solcat1007
License: MIT
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional


class Snapshot:
    """Represents a filesystem snapshot."""

    def __init__(self, name: str, root: str, files: Dict = None, timestamp: str = None):
        self.name = name
        self.root = os.path.abspath(root)
        self.files = files or {}  # {relative_path: {"size": int, "hash": str, "mtime": float}}
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "root": self.root,
            "timestamp": self.timestamp,
            "file_count": len(self.files),
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Snapshot':
        return cls(
            name=data["name"],
            root=data["root"],
            files=data["files"],
            timestamp=data["timestamp"],
        )

    def save(self, storage_dir: str) -> str:
        """Save snapshot to a JSON file."""
        os.makedirs(storage_dir, exist_ok=True)
        filepath = os.path.join(storage_dir, f"{self.name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return filepath

    @classmethod
    def load(cls, name: str, storage_dir: str) -> 'Snapshot':
        """Load a snapshot from a JSON file."""
        filepath = os.path.join(storage_dir, f"{name}.json")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Snapshot not found: {name}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def take_snapshot(directory: str, name: str, storage_dir: str) -> Snapshot:
    """Take a snapshot of a directory tree."""
    root = os.path.abspath(directory)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Directory not found: {root}")

    files = {}
    hash_chunk_size = 65536

    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root).replace("\\", "/")

            try:
                stat = os.stat(full_path)
                file_hash = hashlib.md5()  # Fast enough for diffing

                # Only hash files under 100MB for speed
                if stat.st_size < 100 * 1024 * 1024:
                    with open(full_path, "rb") as f:
                        while chunk := f.read(hash_chunk_size):
                            file_hash.update(chunk)
                    hash_val = file_hash.hexdigest()
                else:
                    # For large files, use size + partial hash
                    with open(full_path, "rb") as f:
                        first = f.read(hash_chunk_size)
                        f.seek(stat.st_size // 2)
                        middle = f.read(hash_chunk_size)
                        f.seek(-hash_chunk_size, 2)
                        last = f.read(hash_chunk_size)
                    file_hash.update(first + middle + last)
                    hash_val = file_hash.hexdigest()

                files[rel_path] = {
                    "size": stat.st_size,
                    "hash": hash_val,
                    "mtime": stat.st_mtime,
                }
            except (PermissionError, OSError):
                files[rel_path] = {"size": 0, "hash": "ERROR", "mtime": 0}

    snapshot = Snapshot(name, root, files)
    snapshot.save(storage_dir)
    return snapshot


class DiffResult:
    """Result of comparing two snapshots."""

    def __init__(self):
        self.added: List[str] = []
        self.removed: List[str] = []
        self.modified: List[str] = []
        self.moved: List[Tuple[str, str]] = []  # (old_path, new_path)
        self.unchanged: int = 0

    def summary(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("  SnapDiff — Snapshot Comparison")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  Added:      {len(self.added)} files")
        lines.append(f"  Removed:    {len(self.removed)} files")
        lines.append(f"  Modified:   {len(self.modified)} files")
        lines.append(f"  Moved:      {len(self.moved)} files")
        lines.append(f"  Unchanged:  {self.unchanged} files")
        lines.append("")
        total_changes = len(self.added) + len(self.removed) + len(self.modified) + len(self.moved)
        lines.append(f"  Total changes: {total_changes}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def detail(self) -> str:
        lines = [self.summary(), ""]

        if self.added:
            lines.append("ADDED:")
            for path in sorted(self.added):
                lines.append(f"  + {path}")
            lines.append("")

        if self.removed:
            lines.append("REMOVED:")
            for path in sorted(self.removed):
                lines.append(f"  - {path}")
            lines.append("")

        if self.modified:
            lines.append("MODIFIED:")
            for path in sorted(self.modified):
                lines.append(f"  ~ {path}")
            lines.append("")

        if self.moved:
            lines.append("MOVED:")
            for old, new in sorted(self.moved):
                lines.append(f"  {old} -> {new}")
            lines.append("")

        return "\n".join(lines)


def diff_snapshots(old: Snapshot, new: Snapshot) -> DiffResult:
    """Compare two snapshots and return the differences."""
    result = DiffResult()

    old_files = old.files
    new_files = new.files

    old_paths = set(old_files.keys())
    new_paths = set(new_files.keys())

    # Added files
    added = new_paths - old_paths
    # Removed files
    removed = old_paths - new_paths
    # Common files
    common = old_paths & new_paths

    # Detect moved files (same hash, different path)
    # Build a hash -> path mapping for removed files
    removed_by_hash: Dict[str, str] = {}
    for path in removed:
        h = old_files[path].get("hash", "")
        if h and h != "ERROR":
            removed_by_hash.setdefault(h, []).append(path)

    moved_from = set()
    moved_to = set()

    for path in added:
        h = new_files[path].get("hash", "")
        if h in removed_by_hash:
            old_path = removed_by_hash[h][0]
            result.moved.append((old_path, path))
            moved_from.add(old_path)
            moved_to.add(path)
            # Remove from removed list
            removed_by_hash[h].remove(old_path)
            if not removed_by_hash[h]:
                del removed_by_hash[h]

    # Filter out moved files from added/removed
    result.added = sorted(added - moved_to)
    result.removed = sorted(removed - moved_from)

    # Check modified files (same path, different hash)
    for path in common:
        old_hash = old_files[path].get("hash", "")
        new_hash = new_files[path].get("hash", "")
        old_size = old_files[path].get("size", 0)
        new_size = new_files[path].get("size", 0)

        if old_hash != new_hash or old_size != new_size:
            result.modified.append(path)
        else:
            result.unchanged += 1

    return result


def get_storage_dir() -> str:
    """Get the storage directory for snapshots."""
    home = Path.home()
    storage = home / ".snapdiff"
    storage.mkdir(parents=True, exist_ok=True)
    return str(storage)


def list_snapshots(storage_dir: str) -> List[str]:
    """List all saved snapshots."""
    if not os.path.isdir(storage_dir):
        return []
    files = [f[:-5] for f in os.listdir(storage_dir) if f.endswith(".json")]
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        prog="snapdiff",
        description="Filesystem snapshot and diff tool. Zero dependencies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s snapshot /project --name before       Take snapshot
  # ... make changes ...
  %(prog)s snapshot /project --name after        Take another
  %(prog)s diff before after                       Compare
  %(prog)s diff before after --summary             Summary only
  %(prog)s list                                    List snapshots
""",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    p_snap = sub.add_parser("snapshot", help="Take a directory snapshot")
    p_snap.add_argument("directory", help="Directory to snapshot")
    p_snap.add_argument("--name", required=True, help="Snapshot name")

    p_diff = sub.add_parser("diff", help="Compare two snapshots")
    p_diff.add_argument("old", help="First snapshot name")
    p_diff.add_argument("new", help="Second snapshot name")
    p_diff.add_argument("--summary", action="store_true", help="Summary only")
    p_diff.add_argument("--added", action="store_true", help="Only show added files")
    p_diff.add_argument("--removed", action="store_true", help="Only show removed files")
    p_diff.add_argument("--modified", action="store_true", help="Only show modified files")
    p_diff.add_argument("--moved", action="store_true", help="Only show moved files")

    sub.add_parser("list", help="List saved snapshots")

    p_watch = sub.add_parser("watch", help="Monitor directory for changes")
    p_watch.add_argument("directory", help="Directory to monitor")
    p_watch.add_argument("--interval", type=int, default=5, help="Check interval (seconds)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    storage = get_storage_dir()

    if args.command == "snapshot":
        try:
            snap = take_snapshot(args.directory, args.name, storage)
            print(f"Snapshot '{args.name}': {len(snap.files)} files captured")
            print(f"  Root: {snap.root}")
            print(f"  Time: {snap.timestamp}")
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "diff":
        try:
            old_snap = Snapshot.load(args.old, storage)
            new_snap = Snapshot.load(args.new, storage)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        result = diff_snapshots(old_snap, new_snap)

        if args.summary:
            print(result.summary())
        elif args.added:
            for path in sorted(result.added):
                print(f"  + {path}")
        elif args.removed:
            for path in sorted(result.removed):
                print(f"  - {path}")
        elif args.modified:
            for path in sorted(result.modified):
                print(f"  ~ {path}")
        elif args.moved:
            for old, new in sorted(result.moved):
                print(f"  {old} -> {new}")
        else:
            print(result.detail())

    elif args.command == "list":
        snaps = list_snapshots(storage)
        if not snaps:
            print("No snapshots found.")
            return
        print(f"Snapshots in {storage}:\n")
        for name in snaps:
            try:
                snap = Snapshot.load(name, storage)
                print(f"  {name:<20} {snap.timestamp}  {len(snap.files)} files  {snap.root}")
            except Exception:
                print(f"  {name:<20} [error loading]")

    elif args.command == "watch":
        print(f"Watching {args.directory} (Ctrl+C to stop)...")
        last_snapshot = None
        try:
            while True:
                current = take_snapshot(args.directory, "_watch_temp", storage)
                if last_snapshot:
                    result = diff_snapshots(last_snapshot, current)
                    total = (len(result.added) + len(result.removed) +
                             len(result.modified) + len(result.moved))
                    if total > 0:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {total} changes:")
                        for p in result.added:
                            print(f"  + {p}")
                        for p in result.removed:
                            print(f"  - {p}")
                        for p in result.modified:
                            print(f"  ~ {p}")
                last_snapshot = current
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
