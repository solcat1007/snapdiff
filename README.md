# SnapDiff

> Filesystem snapshot and diff tool. Zero dependencies.
> Track what changed between two points in time — added, removed, modified, moved.

## Why

You deploy code. Something breaks. What changed on the filesystem between the last good deploy and now? SnapDiff captures a snapshot of file paths, sizes, and hashes, then compares two snapshots to show exactly what was added, removed, modified, or moved.

## Quick Start

```bash
# Take a snapshot before changes
python snapdiff.py snapshot /var/www/app --name before

# ... make changes to the project ...

# Take another snapshot
python snapdiff.py snapshot /var/www/app --name after

# Compare
python snapdiff.py diff before after
```

Output:
```
============================================================
  SnapDiff — Snapshot Comparison
============================================================

  Added:      3 files
  Removed:    1 files
  Modified:   2 files
  Moved:      1 files
  Unchanged:  147 files

  Total changes: 7
============================================================

ADDED:
  + config/local.json
  + scripts/deploy.sh
  + static/logo.png

REMOVED:
  - old_config.ini

MODIFIED:
  ~ app.py
  ~ requirements.txt

MOVED:
  data/users.csv -> data/old_users.csv
```

## Commands

```bash
snapdiff snapshot /dir --name before         Take a snapshot
snapdiff diff before after                     Compare two snapshots
snapdiff diff before after --summary           Summary only
snapdiff diff before after --added             Only added files
snapdiff diff before after --removed            Only removed files
snapdiff diff before after --modified           Only modified files
snapdiff diff before after --moved              Only moved files
snapdiff list                                   List all snapshots
snapdiff watch /dir --interval 5                Live monitoring
```

## How It Works

1. **`snapshot`** walks the directory tree, records every file's path, size, and MD5 hash
2. **`diff`** compares two snapshots:
   - New paths → **added**
   - Missing paths → **removed**
   - Same path, different hash → **modified**
   - Different path, same hash → **moved** (content-based detection)
3. Snapshots are stored as JSON in `~/.snapdiff/`

## Testing

```bash
python snapdiff/tests/test_snapdiff.py -v
```

All 12 tests pass.

## License

MIT

## Author

solcat1007
