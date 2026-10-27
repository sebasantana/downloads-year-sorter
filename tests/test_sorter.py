from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

import sort_downloads_by_year as sorter

YEAR = datetime.now().year


def write(path: Path, content: str, year: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if year is not None:
        ts = time.mktime(datetime(year, 6, 15, 12).timetuple())
        os.utime(path, (ts, ts))
    return path


def run(downloads: Path, *extra: str) -> int:
    return sorter.main(["--downloads", str(downloads), "--date-source", "modified", *extra])


def contents(directory: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(directory.iterdir()) if p.is_file()}


def test_sorts_files_into_year_folders(tmp_path: Path) -> None:
    write(tmp_path / "old.txt", "old", year=2019)
    write(tmp_path / "new.txt", "new", year=2024)

    assert run(tmp_path) == 0

    assert contents(tmp_path / "2019") == {"old.txt": "old"}
    assert contents(tmp_path / "2024") == {"new.txt": "new"}
    assert not (tmp_path / "old.txt").exists()


def test_collision_with_existing_file_gets_suffix(tmp_path: Path) -> None:
    write(tmp_path / str(YEAR) / "foo.txt", "existing")
    write(tmp_path / "foo.txt", "incoming")

    assert run(tmp_path) == 0

    assert contents(tmp_path / str(YEAR)) == {"foo (1).txt": "incoming", "foo.txt": "existing"}


def test_planned_destinations_never_collide(tmp_path: Path) -> None:
    # Regression: "foo (1).txt" and "foo.txt" were both planned to
    # "foo (1).txt", and the second move silently overwrote the first.
    write(tmp_path / str(YEAR) / "foo.txt", "existing")
    write(tmp_path / "foo (1).txt", "AAA")
    write(tmp_path / "foo.txt", "BBB")

    assert run(tmp_path) == 0

    result = contents(tmp_path / str(YEAR))
    assert sorted(result.values()) == ["AAA", "BBB", "existing"]
    assert len(result) == 3


def test_unique_destination_respects_reserved_case_insensitively(tmp_path: Path) -> None:
    reserved = {str(tmp_path / "A.TXT").casefold()}
    assert sorter.unique_destination(tmp_path / "a.txt", reserved) == tmp_path / "a (1).txt"


def test_do_transfer_refuses_to_overwrite(tmp_path: Path) -> None:
    src = write(tmp_path / "src.txt", "new")
    dest = write(tmp_path / "dest.txt", "keep")

    for mode in ("move", "copy"):
        with pytest.raises(FileExistsError):
            sorter.do_transfer(src, dest, mode)
    assert dest.read_text() == "keep"
    assert src.exists()


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    write(tmp_path / "a.txt", "a", year=2020)

    assert run(tmp_path, "--dry-run") == 0

    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "2020").exists()


def test_copy_mode_keeps_source(tmp_path: Path) -> None:
    write(tmp_path / "a.txt", "a", year=2021)

    assert run(tmp_path, "--mode", "copy") == 0

    assert (tmp_path / "a.txt").read_text() == "a"
    assert (tmp_path / "2021" / "a.txt").read_text() == "a"


def test_directories_skipped_unless_included(tmp_path: Path) -> None:
    write(tmp_path / "folder" / "inner.txt", "x", year=2022)
    os.utime(tmp_path / "folder", (time.mktime(datetime(2022, 1, 1).timetuple()),) * 2)

    assert run(tmp_path) == 0
    assert (tmp_path / "folder").is_dir()

    assert run(tmp_path, "--include-dirs") == 0
    assert (tmp_path / "2022" / "folder" / "inner.txt").exists()


def test_year_folders_are_not_reprocessed(tmp_path: Path) -> None:
    write(tmp_path / "2019" / "keep.txt", "k")

    assert run(tmp_path, "--include-dirs") == 0

    assert (tmp_path / "2019" / "keep.txt").exists()
    assert not (tmp_path / str(YEAR) / "2019").exists()


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_skipped_by_default(tmp_path: Path) -> None:
    target = write(tmp_path.parent / f"{tmp_path.name}-target.txt", "t")
    (tmp_path / "link.txt").symlink_to(target)

    assert run(tmp_path) == 0

    assert (tmp_path / "link.txt").is_symlink()


def test_year_path_that_is_a_file_is_skipped(tmp_path: Path) -> None:
    write(tmp_path / "2020", "i am a file named like a year", year=2020)
    write(tmp_path / "a.txt", "a", year=2020)

    assert run(tmp_path) == 0

    assert (tmp_path / "a.txt").exists()


def test_downloads_path_expands_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SORTER_TEST_DIR", str(tmp_path))
    write(tmp_path / "a.txt", "a", year=2018)
    var = "%SORTER_TEST_DIR%" if os.name == "nt" else "$SORTER_TEST_DIR"

    assert sorter.main(["--downloads", var, "--date-source", "modified"]) == 0

    assert (tmp_path / "2018" / "a.txt").exists()


def test_missing_downloads_dir_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        sorter.main(["--downloads", str(tmp_path / "nope")])


def test_creation_time_falls_back_to_mtime_without_birthtime(tmp_path: Path) -> None:
    class FakeStat:
        st_ctime = 0.0
        st_mtime = 1.0

    if os.name != "nt":
        assert sorter.creation_timestamp(FakeStat()) is None  # type: ignore[arg-type]
