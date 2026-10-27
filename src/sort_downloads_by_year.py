from __future__ import annotations

import argparse
import logging
import os
import shutil
import stat
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger("downloads_year_sorter")


@dataclass(frozen=True)
class Options:
    downloads: Path
    mode: str  # "move" | "copy"
    date_source: str  # "created" | "modified"
    dry_run: bool
    include_dirs: bool
    include_links: bool
    verbose: bool


def default_downloads_dir() -> Path:
    home = Path.home()
    candidates: list[Path]
    if os.name == "nt":
        candidates = []
        onedrive = os.environ.get("OneDrive")
        if onedrive:
            candidates.append(Path(onedrive) / "Downloads")
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            candidates.append(Path(userprofile) / "Downloads")
        candidates.append(home / "Downloads")
        candidates.append(home / "OneDrive" / "Downloads")
    else:
        candidates = [home / "Downloads"]

    for path in candidates:
        try:
            if path.exists() and path.is_dir():
                return path
        except OSError:
            continue
    return candidates[0]


def creation_timestamp(st: os.stat_result) -> float | None:
    # st_birthtime is the real creation time on macOS/BSD, and on Windows
    # since Python 3.12. Before 3.12, Windows exposed it as st_ctime.
    # On Unix, st_ctime is "metadata change time", so it is never used there.
    birthtime = getattr(st, "st_birthtime", None)
    if birthtime:
        return birthtime
    if os.name == "nt":
        return st.st_ctime
    return None


def file_year(p: Path, date_source: str) -> int:
    st = p.stat()
    ts: float | None = None
    if date_source == "created":
        ts = creation_timestamp(st)
        if ts is None:
            log.debug("No creation time available for %s, using modified time", p)
    if ts is None:
        ts = st.st_mtime
    return datetime.fromtimestamp(ts).year


def _key(p: Path) -> str:
    # Windows and default macOS filesystems are case-insensitive.
    return str(p).casefold()


def unique_destination(dest: Path, reserved: set[str] | None = None) -> Path:
    reserved = reserved if reserved is not None else set()

    def taken(candidate: Path) -> bool:
        return candidate.exists() or _key(candidate) in reserved

    if not taken(dest):
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not taken(candidate):
            return candidate
        i += 1


def is_windows_junction(path: Path) -> bool:
    if os.name != "nt":
        return False
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT) and path.is_dir() and not path.is_symlink()


def is_year_dir(entry: Path) -> bool:
    return entry.is_dir() and entry.name.isdigit() and len(entry.name) == 4


def iter_entries(root: Path, include_dirs: bool, include_links: bool) -> Iterator[Path]:
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        # Skip our own year folders to avoid loops
        if is_year_dir(entry):
            continue
        if (entry.is_symlink() or is_windows_junction(entry)) and not include_links:
            log.debug("Skipping link: %s", entry)
            continue
        if entry.is_dir() and not include_dirs:
            log.debug("Skipping directory: %s", entry)
            continue
        yield entry


def plan_ops(opts: Options) -> Iterator[tuple[Path, Path]]:
    # Destinations already assigned in this run. Without this, two entries
    # could be planned to the same name (e.g. "a (1).txt" and "a.txt" when
    # "a.txt" already exists) and the second transfer would overwrite the first.
    reserved: set[str] = set()
    for entry in iter_entries(opts.downloads, opts.include_dirs, opts.include_links):
        try:
            y = file_year(entry, opts.date_source)
        except OSError as e:
            log.warning("Cannot read time for %s: %s", entry, e)
            continue

        target_dir = opts.downloads / str(y)
        if target_dir.exists() and not target_dir.is_dir():
            log.warning("Year target is not a directory, skipping %s: %s", entry, target_dir)
            continue
        if not opts.dry_run:
            try:
                target_dir.mkdir(exist_ok=True)
            except OSError as e:
                log.warning("Cannot create target dir for %s: %s", entry, e)
                continue

        dest = unique_destination(target_dir / entry.name, reserved)
        reserved.add(_key(dest))
        yield entry, dest


def do_transfer(src: Path, dest: Path, mode: str) -> None:
    # Last line of defense: never overwrite, even if something appeared at
    # dest after planning. shutil.move/copy2 would silently replace it.
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Destination already exists: {dest}")
    if mode == "copy":
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
    else:  # move
        shutil.move(str(src), str(dest))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="downloads-year-sorter",
        description="Sort a Downloads folder into year folders (by created/modified date).",
    )
    ap.add_argument(
        "--downloads",
        default=None,
        help="Path to Downloads folder; environment variables are expanded "
        "(default: auto-detect, OneDrive-aware on Windows)",
    )
    ap.add_argument(
        "--mode",
        choices=("move", "copy"),
        default="move",
        help="Move files (default) or copy them",
    )
    ap.add_argument(
        "--date-source",
        choices=("created", "modified"),
        default="created",
        help="Which timestamp decides the year (default: created; "
        "falls back to modified where creation time is unavailable)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without moving/copying anything",
    )
    ap.add_argument(
        "--include-dirs",
        action="store_true",
        help="Also move/copy directories (default: only files)",
    )
    ap.add_argument(
        "--include-links",
        action="store_true",
        help="Also include symlinks/junctions (default: skip for safety)",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Also log skipped entries and timestamp fallbacks",
    )
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    downloads = Path(os.path.expandvars(args.downloads)) if args.downloads else default_downloads_dir()

    opts = Options(
        downloads=downloads.expanduser().resolve(),
        mode=args.mode,
        date_source=args.date_source,
        dry_run=args.dry_run,
        include_dirs=args.include_dirs,
        include_links=args.include_links,
        verbose=args.verbose,
    )

    if not opts.downloads.exists() or not opts.downloads.is_dir():
        raise SystemExit(f"Downloads path is not a directory: {opts.downloads}")

    ops = list(plan_ops(opts))

    if not ops:
        print("Nothing to do.")
        return 0

    action = "COPY" if opts.mode == "copy" else "MOVE"
    for src, dest in ops:
        print(f"{action}  {src.name}  ->  {dest.relative_to(opts.downloads)}")

    if opts.dry_run:
        print("\n[DRY RUN] No changes made.")
        return 0

    # Execute
    failures = 0
    for src, dest in ops:
        try:
            do_transfer(src, dest, opts.mode)
        except (OSError, shutil.Error) as e:
            failures += 1
            log.error("%s -> %s: %s", src, dest, e)

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
