# Downloads Year Sorter

[![CI](https://github.com/sebasantana/downloads-year-sorter/actions/workflows/ci.yml/badge.svg)](https://github.com/sebasantana/downloads-year-sorter/actions/workflows/ci.yml)

Sort files in your Downloads folder into `YYYY` subfolders by file timestamp.
Built for Windows (OneDrive-aware), works on macOS and Linux too. No dependencies.

## Requirements

- Python 3.10+

## Install

```bash
pipx install git+https://github.com/sebasantana/downloads-year-sorter
```

Or with uv:

```bash
uv tool install git+https://github.com/sebasantana/downloads-year-sorter
```

Or run the script directly without installing:

```bash
python src/sort_downloads_by_year.py --dry-run
```

## Usage

Always preview first:

```bash
downloads-year-sorter --dry-run
```

Options:

- `--downloads PATH`: downloads folder to process. Environment variables are expanded (`%OneDrive%` on Windows, `$HOME` elsewhere). Default: auto-detected.
- `--mode move|copy`: move (default) or copy entries.
- `--date-source created|modified`: timestamp used to choose the year (default: `created`).
- `--dry-run`: preview actions without changing files.
- `--include-dirs`: include directories (default is files only).
- `--include-links`: include symlinks/junctions (default is skip for safety).
- `--verbose`: also log skipped entries and timestamp fallbacks.

Exit code is `0` on success and `1` if any transfer failed.

## Examples

Preview what would happen, including skipped entries:

```bash
downloads-year-sorter --dry-run --verbose
```

Move files in place using modified time:

```bash
downloads-year-sorter --date-source modified
```

Copy files from OneDrive Downloads into year folders:

```bash
downloads-year-sorter --mode copy --downloads "%OneDrive%\Downloads"
```

Include directories too:

```bash
downloads-year-sorter --include-dirs
```

## Which date is "created"?

| Platform | `--date-source created` uses |
|---|---|
| Windows | File creation time |
| macOS | File creation time (`st_birthtime`) |
| Linux | Modified time (most Linux filesystems don't expose creation time to Python) |

`st_ctime` is never used on macOS/Linux, because there it means "metadata last changed", not "created".

## Safety

- Existing files are never overwritten. Name collisions get ` (1)`, ` (2)`, etc. This also covers collisions between files in the same run and is case-insensitive, as on Windows and macOS filesystems.
- Symlinks and Windows junction/reparse points are skipped by default.
- Existing `YYYY` folders are never re-processed.
- If a year path exists as a file (not a directory), that item is skipped with a warning.
- `--dry-run` does not create folders or modify files.
- Individual failures (locked files, permissions) are reported without aborting the remaining operations.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

CI runs the tests on Windows, macOS and Linux with Python 3.10 and 3.13.

Manual checks still worth doing on Windows before a release:

- default path detection (local Downloads and OneDrive Downloads, including files-on-demand placeholders),
- junctions are skipped unless `--include-links` is set,
- long paths, if long-path support is enabled in OS policy.

## License

MIT
