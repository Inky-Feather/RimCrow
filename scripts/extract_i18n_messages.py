from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pathspec


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCALE_PATH = ROOT / "frontend" / "src" / "locales" / "zh-CN.json"
SCAN_ROOTS = (
    ROOT / "backend",
    ROOT / "frontend" / "src",
)
BASE_LOCALE_SHAPE: dict[str, Any] = {
    "ui": {},
    "tooltip": {},
    "toast": {},
    "dialog": {},
    "api": {},
    "errors": {},
    "tasks": {},
    "logs": {},
    "ai": {
        "definitions": {},
        "tools": {},
        "actions": {},
        "prompts": {},
    },
}

JS_CALL_PATTERN = re.compile(
    r"(?<![\w$])t\s*\(\s*"
    r"(?P<key>['\"`])(?P<key_text>(?:\\.|(?!\1).)*?)\1\s*,\s*"
    r"(?P<default>['\"`])(?P<default_text>(?:\\.|(?!\3).)*?)\3",
    re.DOTALL,
)


def load_gitignore_spec() -> pathspec.PathSpec:
    patterns: list[str] = []
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
    # .gitignore 未必覆盖所有生成目录；这里补充只和扫描性能有关的硬排除。
    patterns.extend([
        ".git/",
        ".codegraph/",
        ".gitnexus/",
        ".venv/",
        "frontend/node_modules/",
        "frontend/dist/",
        "dist/",
        "build/",
        "data/",
        "cache/",
    ])
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def is_ignored(path: Path, spec: pathspec.PathSpec) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return spec.match_file(rel)


def iter_source_files() -> Iterable[Path]:
    spec = load_gitignore_spec()
    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if path.is_dir() or is_ignored(path, spec):
                continue
            if path.suffix in {".py", ".js", ".vue"}:
                yield path


def decode_js_string(raw: str, quote: str) -> str:
    if quote == "`" and "${" in raw:
        raise ValueError("模板字符串默认文本不能包含 ${...} 插值")
    if quote in {"'", '"'}:
        return ast.literal_eval(f"{quote}{raw}{quote}")
    # 只支持无插值模板字符串，足够覆盖 t('key', `默认文本`) 这类声明。
    body = raw.replace(r"\`", "`").replace('"', r"\"")
    return ast.literal_eval(f'"{body}"')


def extract_js_messages(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    messages: dict[str, str] = {}
    for match in JS_CALL_PATTERN.finditer(source):
        key = decode_js_string(match.group("key_text"), match.group("key"))
        default_text = decode_js_string(match.group("default_text"), match.group("default"))
        if key.strip():
            messages[key.strip()] = default_text
    return messages


def literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def is_tr_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name) and node.func.id == "tr"
        or isinstance(node.func, ast.Attribute) and node.func.attr == "tr"
    )


def extract_python_messages(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    messages: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_tr_call(node) or len(node.args) < 2:
            continue
        key = literal_string(node.args[0])
        default_text = literal_string(node.args[1])
        if key and default_text is not None:
            messages[key.strip()] = default_text
    return messages


def merge_extracted_messages() -> dict[str, str]:
    extracted: dict[str, str] = {}
    origins: dict[str, Path] = {}
    conflicts: list[str] = []
    for path in iter_source_files():
        file_messages = extract_python_messages(path) if path.suffix == ".py" else extract_js_messages(path)
        for key, default_text in file_messages.items():
            if key in extracted and extracted[key] != default_text:
                conflicts.append(
                    f"{key}: {origins[key].relative_to(ROOT).as_posix()}={extracted[key]!r}, "
                    f"{path.relative_to(ROOT).as_posix()}={default_text!r}"
                )
                continue
            extracted[key] = default_text
            origins[key] = path
    if conflicts:
        joined = "\n".join(conflicts)
        raise SystemExit(f"发现相同 i18n key 对应不同默认中文，请先统一：\n{joined}")
    return extracted


def load_locale(path: Path) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(BASE_LOCALE_SHAPE, ensure_ascii=False))
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def set_nested(payload: dict[str, Any], dotted_key: str, value: str) -> None:
    parts = [part for part in dotted_key.split(".") if part]
    if not parts:
        return
    current = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def build_locale_payload(existing: Mapping[str, Any], extracted: Mapping[str, str]) -> dict[str, Any]:
    payload = json.loads(json.dumps(BASE_LOCALE_SHAPE, ensure_ascii=False))
    for key, value in dict(existing or {}).items():
        payload[key] = value
    for key in sorted(extracted):
        set_nested(payload, key, extracted[key])
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 t/tr 调用并增量生成默认中文语言包。")
    parser.add_argument("--check", action="store_true", help="只检查 zh-CN.json 是否已同步，不写入文件。")
    parser.add_argument("--locale-file", type=Path, default=DEFAULT_LOCALE_PATH, help="默认中文语言包路径。")
    args = parser.parse_args()

    locale_path = args.locale_file if args.locale_file.is_absolute() else ROOT / args.locale_file
    extracted = merge_extracted_messages()
    next_payload = build_locale_payload(load_locale(locale_path), extracted)
    next_text = json.dumps(next_payload, ensure_ascii=False, indent=2) + "\n"
    current_text = locale_path.read_text(encoding="utf-8") if locale_path.exists() else ""
    if args.check:
        if current_text != next_text:
            print(f"{locale_path.relative_to(ROOT).as_posix()} 未同步，请运行：uv run python scripts/extract_i18n_messages.py", file=sys.stderr)
            return 1
        print(f"i18n 默认语言包已同步，共 {len(extracted)} 条。")
        return 0
    write_json(locale_path, next_payload)
    print(f"已更新 {locale_path.relative_to(ROOT).as_posix()}，共 {len(extracted)} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
