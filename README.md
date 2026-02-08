# Downloads Year Sorter

Sort files in your Downloads folder into `YYYY` subfolders by file timestamp.

## Requirements

- Python 3.10+

## Usage

Run from the repository root:

```bash
python src/sort_downloads_by_year.py --dry-run
```

Common options:

- `--downloads PATH`: downloads folder to process.
- `--mode move|copy`: move (default) or copy entries.
- `--date-source created|modified`: timestamp used to choose year.
- `--dry-run`: preview actions without changing files.
- `--include-dirs`: include directories (default is files only).
- `--include-links`: include symlinks/junctions (default is skip for safety).
- `--verbose`: print warnings for skipped/problem entries.

## Examples

Preview what would happen:

```bash
python src/sort_downloads_by_year.py --dry-run --verbose
```

Move files in place using modified time:

```bash
python src/sort_downloads_by_year.py --date-source modified
```

Copy files from OneDrive Downloads into year folders:

```bash
python src/sort_downloads_by_year.py --mode copy --downloads "%OneDrive%\\Downloads"
```

Include directories too:

```bash
python src/sort_downloads_by_year.py --include-dirs
```

## Safety Notes

- Name collisions are handled by appending ` (1)`, ` (2)`, etc.
- Symlinks and Windows junction/reparse points are skipped by default.
- If a year path exists as a file (not a directory), that item is skipped with a warning.
- `--dry-run` does not create folders or modify files.

## Manual Test Plan

1. Create a temp folder with:
   - two files from different years,
   - one file that collides with a name already inside a year folder,
   - one subdirectory,
   - one symlink/junction (if supported),
   - one file set to read-only.
2. Run `--dry-run --verbose` and verify:
   - planned actions look correct,
   - symlink/junction is skipped unless `--include-links` is set,
   - no folders/files are created or moved.
3. Run in `--mode copy` and verify:
   - source files remain,
   - copies appear in year folders,
   - collision file gets a suffixed name.
4. Run in `--mode move` and verify:
   - source files are moved,
   - failures (for locked/permission cases) are reported without crashing all operations.
5. On Windows, test with:
   - default path detection (local Downloads and OneDrive Downloads),
   - long path examples if long-path support is enabled in OS policy.
