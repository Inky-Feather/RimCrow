import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Callable


DEFAULT_ZIP_COMPRESSLEVEL = 6
DISK_SPACE_HEADROOM_BYTES = 256 * 1024 * 1024


def create_sibling_stage_dir(target_path: str | Path, prefix: str) -> Path:
    """
    在目标目录同级创建临时 staging 目录。

    这样后续替换时能尽量走同盘符重命名，避免跨盘复制导致“半覆盖”。
    """
    target_root = Path(target_path)
    parent_dir = target_root.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent_dir)))


def normalize_zip_compresslevel(raw_level: int | None, default_level: int = DEFAULT_ZIP_COMPRESSLEVEL) -> int:
    try:
        normalized_level = int(raw_level if raw_level is not None else default_level)
    except (TypeError, ValueError):
        normalized_level = default_level
    return max(0, min(9, normalized_level))


def summarize_zip_members(
    bundle: zipfile.ZipFile,
    prefixes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, int | float | None]:
    normalized_prefixes = []
    for prefix in prefixes or []:
        normalized = str(prefix or "").strip().replace("\\", "/").strip("/")
        if normalized:
            normalized_prefixes.append(f"{normalized}/")

    file_count = 0
    compressed_bytes = 0
    uncompressed_bytes = 0
    for info in bundle.infolist():
        if info.is_dir():
            continue
        member_name = str(info.filename or "").replace("\\", "/")
        if normalized_prefixes and not any(member_name.startswith(prefix) for prefix in normalized_prefixes):
            continue
        file_count += 1
        compressed_bytes += int(info.compress_size or 0)
        uncompressed_bytes += int(info.file_size or 0)

    return {
        "file_count": file_count,
        "compressed_bytes": compressed_bytes,
        "uncompressed_bytes": uncompressed_bytes,
        "expansion_ratio": (uncompressed_bytes / compressed_bytes) if compressed_bytes > 0 else None,
        "compression_ratio": (compressed_bytes / uncompressed_bytes) if uncompressed_bytes > 0 else None,
    }


def estimate_disk_space_requirement(
    target_path: str | Path,
    required_bytes: int,
    *,
    headroom_bytes: int = DISK_SPACE_HEADROOM_BYTES,
) -> dict[str, int | bool | str]:
    required = max(0, int(required_bytes or 0))
    probe = Path(target_path)
    if probe.exists() and probe.is_file():
        probe = probe.parent
    elif not probe.exists():
        probe = probe.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if not probe.exists():
        probe = Path.cwd()

    free_bytes = int(shutil.disk_usage(probe).free)
    recommended_bytes = required + max(0, int(headroom_bytes or 0)) if required > 0 else 0
    return {
        "path": str(probe),
        "free_bytes": free_bytes,
        "required_bytes": required,
        "headroom_bytes": max(0, int(headroom_bytes or 0)),
        "recommended_bytes": recommended_bytes,
        "enough": free_bytes >= recommended_bytes,
    }


def write_tree_to_zip(
    source_root: str | Path,
    bundle: zipfile.ZipFile,
    prefix: str,
    cancel_check: Callable[[], None] | None = None,
) -> None:
    root = Path(source_root)
    if not root.is_dir():
        raise ValueError(f"目录不存在，无法写入压缩包: {root}")

    normalized_prefix = str(prefix or "").strip().strip("/")
    for child in root.rglob("*"):
        if cancel_check:
            cancel_check()
        if child.is_dir():
            continue
        relative_path = child.relative_to(root).as_posix()
        arcname = f"{normalized_prefix}/{relative_path}" if normalized_prefix else relative_path
        bundle.write(child, arcname=arcname)


def extract_prefix_to_dir(
    bundle: zipfile.ZipFile,
    prefix: str,
    target_root: str | Path,
    cancel_check: Callable[[], None] | None = None,
) -> list[str]:
    normalized_prefix = str(prefix or "").strip().replace("\\", "/").strip("/")
    if not normalized_prefix:
        raise ValueError("缺少压缩包目录前缀")
    normalized_prefix = f"{normalized_prefix}/"

    target_dir = Path(target_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_target_root = target_dir.resolve()
    matched_names = [name for name in bundle.namelist() if name.startswith(normalized_prefix)]
    if not matched_names:
        raise ValueError("压缩包中缺少目标目录内容")

    for member_name in matched_names:
        if cancel_check:
            cancel_check()
        relative_path = member_name[len(normalized_prefix):]
        if not relative_path:
            continue
        target_path = (resolved_target_root / relative_path).resolve()
        if resolved_target_root not in target_path.parents and target_path != resolved_target_root:
            raise ValueError("检测到非法压缩路径，已拒绝解包")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(member_name, "r") as source_handle:
            with open(target_path, "wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
    return matched_names


def replace_dir_atomically(target_path: str | Path, prepared_path: str | Path) -> None:
    """
    用 staging 目录整体替换目标目录。

    替换前先把旧目录改名为备份目录；若新目录落位失败，再回滚旧目录。
    """
    target_root = Path(target_path)
    prepared_root = Path(prepared_path)
    if not prepared_root.is_dir():
        raise ValueError(f"预备目录不存在，无法替换: {prepared_root}")

    target_root.parent.mkdir(parents=True, exist_ok=True)
    backup_root: Path | None = None

    try:
        if target_root.exists():
            backup_root = target_root.parent / f".bundle-backup-{target_root.name}-{uuid.uuid4().hex}"
            target_root.replace(backup_root)
        prepared_root.replace(target_root)
    except Exception:
        if backup_root and backup_root.exists() and not target_root.exists():
            backup_root.replace(target_root)
        raise
    else:
        if backup_root and backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)
