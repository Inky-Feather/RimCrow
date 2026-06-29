from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def find_project_root(start_path: Path) -> Path:
    resolved_start = start_path.resolve()
    fallback_root: Path | None = None

    for candidate in (resolved_start, *resolved_start.parents):
        if (candidate / ".git").exists():
            return candidate
        if fallback_root is None and (candidate / ".gitignore").exists():
            fallback_root = candidate

    return fallback_root or resolved_start


def list_files_from_git(project_root: Path) -> list[Path]:
    command = [
        "git",
        "-C",
        str(project_root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    result = subprocess.run(command, capture_output=True, check=True)

    files: list[Path] = []
    seen: set[str] = set()
    for raw_item in result.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw_item:
            continue
        normalized = raw_item.replace("\\", "/")
        if normalized in seen:
            continue
        seen.add(normalized)

        relative_path = Path(raw_item)
        absolute_path = (project_root / relative_path).resolve()
        if absolute_path.is_file():
            files.append(relative_path)

    return sorted(files, key=lambda item: item.as_posix())


def build_output_path(project_root: Path, explicit_output: str | None, project_version: str="") -> Path:
    if explicit_output:
        output_path = Path(explicit_output).expanduser()
        if not output_path.is_absolute():
            output_path = project_root / output_path
        return output_path.resolve()
    project_version = project_version.lstrip("-v")  # Remove leading 'v' if present
    timestamp = datetime.now().strftime("%Y%m%d")
    return (project_root / "dist" / f"{project_root.name}-source-{timestamp}-v{project_version}.zip").resolve()


def create_archive(project_root: Path, output_path: Path, script_path: Path) -> int:
    try:
        files = list_files_from_git(project_root)
    except subprocess.CalledProcessError as exc:
        print("error: failed to enumerate files via git ls-files", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    excluded_paths = {
        script_path.resolve(),
        output_path.resolve(),
    }

    archived_count = 0
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in files:
            absolute_path = (project_root / relative_path).resolve()
            if absolute_path in excluded_paths:
                continue

            archive.write(absolute_path, arcname=relative_path.as_posix())
            archived_count += 1

    print(f"project root: {project_root}")
    print(f"archive: {output_path}")
    print(f"files: {archived_count}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the current git project into a zip archive using .gitignore-aware file selection.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output zip path. Relative paths are resolved from the detected project root.",
    )
    parser.add_argument(
        "--root",
        help="Override project root. Defaults to the nearest parent directory containing .git.",
    )
    return parser.parse_args()


def main() -> int:
    from backend._version import __version__
    project_version = __version__
    args = parse_args()
    script_path = Path(__file__).resolve()
    project_root = Path(args.root).resolve() if args.root else find_project_root(script_path.parent)
    output_path = build_output_path(project_root, args.output, project_version)
    return create_archive(project_root, output_path, script_path)


if __name__ == "__main__":
    raise SystemExit(main())
