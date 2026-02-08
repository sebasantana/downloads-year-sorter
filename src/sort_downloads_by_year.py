from __future__ import annotations

import argparse
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Options:
    downloads: Path
    mode: str              # "move" | "copy"
    date_source: str       # "created" | "modified"
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


def file_year(p: Path, date_source: str) -> int:
    st = p.stat()
    # NOTE:
    # - On Windows, st_ctime is "creation time".
    # - On Unix/macOS, st_ctime is "metadata change time" (not creation).
    if date_source == "created":
        ts = st.st_ctime
    else:
        ts = st.st_mtime
    return datetime.fromtimestamp(ts).year


def unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
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


def iter_entries(root: Path, include_dirs: bool, include_links: bool):
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        # Skip our own year folders to avoid loops
        if entry.is_dir() and entry.name.isdigit() and len(entry.name) == 4:
            continue
        if (entry.is_symlink() or is_windows_junction(entry)) and not include_links:
            continue
        if entry.is_dir() and not include_dirs:
            continue
        yield entry


def plan_ops(opts: Options):
    for entry in iter_entries(opts.downloads, opts.include_dirs, opts.include_links):
        try:
            y = file_year(entry, opts.date_source)
        except Exception as e:
            if opts.verbose:
                print(f"[WARN] Cannot read time for {entry}: {e}")
            continue

        target_dir = opts.downloads / str(y)
        if target_dir.exists() and not target_dir.is_dir():
            print(f"[WARN] Year target is not a directory, skipping {entry}: {target_dir}")
            continue
        if not opts.dry_run:
            try:
                target_dir.mkdir(exist_ok=True)
            except OSError as e:
                print(f"[WARN] Cannot create target dir for {entry}: {e}")
                continue

        dest = unique_destination(target_dir / entry.name)
        yield entry, dest


def do_transfer(src: Path, dest: Path, mode: str):
    if mode == "copy":
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
    else:  # move
        shutil.move(str(src), str(dest))


def main():
    ap = argparse.ArgumentParser(
        description="Sort Windows Downloads into year folders (by created/modified date)."
    )
    ap.add_argument(
        "--downloads",
        default=str(default_downloads_dir()),
        help="Path to Downloads folder (default: ~/Downloads)",
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
        help="Which timestamp decides the year (default: created)",
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
        help="More logs",
    )
    args = ap.parse_args()

    opts = Options(
        downloads=Path(args.downloads).expanduser().resolve(),
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
        return

    for src, dest in ops:
        action = "COPY" if opts.mode == "copy" else "MOVE"
        print(f"{action}  {src.name}  ->  {dest.relative_to(opts.downloads)}")

    if opts.dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    # Execute
    failures = 0
    for src, dest in ops:
        try:
            do_transfer(src, dest, opts.mode)
        except Exception as e:
            failures += 1
            print(f"[ERROR] {src} -> {dest}: {e}")

    if failures:
        raise SystemExit(f"Completed with {failures} failure(s).")
    print("Done.")


if __name__ == "__main__":
    main()
