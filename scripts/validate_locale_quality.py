from __future__ import annotations

import argparse
import sys
import re
from pathlib import Path
from collections.abc import Mapping

from extract_i18n_messages import (
    BUILTIN_LOCALES_DIR,
    CHINESE_PATTERN,
    DEFAULT_LOCALE_PATH,
    ROOT,
    UNTRANSLATED_PREFIX,
    configure_stdout,
    extract_locale_markers,
    extract_placeholders,
    flatten_string_values,
    load_locale,
)


IGNORED_CHINESE_SPAN_RE = re.compile(r"##.*?##|\{[A-Za-z_][\w.-]*\}")


def locale_paths(values: list[str]) -> list[Path]:
    if values:
        paths: list[Path] = []
        for value in values:
            path = Path(value)
            paths.append(path if path.is_absolute() else ROOT / path)
        return paths
    return sorted(path for path in BUILTIN_LOCALES_DIR.glob("*.json") if path.name != DEFAULT_LOCALE_PATH.name)


def has_unexpected_chinese(text: str) -> bool:
    """保留 ##用户名##、{param} 这类不应翻译的片段，避免质量报告噪音。"""
    return bool(CHINESE_PATTERN.search(IGNORED_CHINESE_SPAN_RE.sub("", text)))


def check_locale(path: Path, reference_values: dict[str, str]) -> list[str]:
    payload = load_locale(path)
    values = flatten_string_values(payload)
    errors: list[str] = []
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    meta = payload.get("_meta") if isinstance(payload, Mapping) else {}
    language = str(meta.get("language") or path.stem).strip().lower() if isinstance(meta, Mapping) else path.stem.lower()
    check_chinese_residue = not language.startswith("zh")

    missing = sorted(set(reference_values) - set(values))
    extra = sorted(set(values) - set(reference_values))
    if missing:
        errors.append(f"{rel} 缺少 key: {', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''}")
    if extra:
        errors.append(f"{rel} 存在未使用 key: {', '.join(extra[:20])}{' ...' if len(extra) > 20 else ''}")

    for key in sorted(set(reference_values) & set(values)):
        text = values[key]
        source = reference_values[key]
        if text == "":
            errors.append(f"{rel} 空译文: {key}")
        if text.startswith(UNTRANSLATED_PREFIX):
            errors.append(f"{rel} 未翻译标记: {key}")
        if check_chinese_residue and has_unexpected_chinese(text):
            errors.append(f"{rel} 残留中文: {key} => {text!r}")
        source_params = extract_placeholders(source)
        locale_params = extract_placeholders(text)
        if source_params != locale_params:
            errors.append(f"{rel} 参数不一致: {key} 默认={sorted(source_params)} 翻译={sorted(locale_params)}")
        source_markers = extract_locale_markers(source)
        locale_markers = extract_locale_markers(text)
        if source_markers != locale_markers:
            errors.append(f"{rel} tooltip/格式标记不一致: {key} 默认={source_markers} 翻译={locale_markers}")
    return errors


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="检查非中文语言包的常见质量问题。")
    parser.add_argument("locales", nargs="*", help="要检查的语言包路径；不传则检查全部内置非中文语言包。")
    parser.add_argument("--reference", type=Path, default=DEFAULT_LOCALE_PATH, help="参考语言包，默认 zh-CN.json。")
    parser.add_argument("--limit", type=int, default=200, help="最多输出的问题数量。")
    args = parser.parse_args()

    reference_path = args.reference if args.reference.is_absolute() else ROOT / args.reference
    reference_values = flatten_string_values(load_locale(reference_path))
    errors: list[str] = []
    for path in locale_paths(args.locales):
        errors.extend(check_locale(path, reference_values))

    if not errors:
        print("语言包质量检查通过。")
        return 0
    limit = max(args.limit, 1)
    print(f"语言包质量检查发现 {len(errors)} 个问题，显示前 {min(limit, len(errors))} 个：", file=sys.stderr)
    print("\n".join(errors[:limit]), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
