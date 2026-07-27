from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.i18n.language_registry import normalize_language_code  # noqa: E402
from scripts.extract_i18n_messages import (
    DEFAULT_LOCALE_PATH,
    UNTRANSLATED_PREFIX,
    configure_stdout,
    extract_locale_markers,
    extract_placeholders,
    flatten_string_values,
    load_locale,
    set_nested,
)


DATA_LOCALES_DIR = ROOT / "data" / "locales"


def read_workfile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workfile 必须是 JSON 对象")
    return payload


def extract_messages(payload: dict[str, Any], language: str = "") -> tuple[str, dict[str, str], list[str]]:
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    target_language = normalize_language_code(language or meta.get("language") or "")
    raw_messages = payload.get("messages") if isinstance(payload.get("messages"), dict) else payload
    messages: dict[str, str] = {}
    errors: list[str] = []
    for key, value in raw_messages.items():
        if key == "_meta":
            continue
        if isinstance(value, dict):
            target = value.get("target")
        else:
            target = value
        text = str(target or "").strip()
        if not text or text.startswith(UNTRANSLATED_PREFIX):
            continue
        if not key or "." not in str(key):
            errors.append(f"无效 key: {key!r}")
            continue
        messages[str(key)] = str(target)
    return target_language, messages, errors


def validate_messages(messages: dict[str, str], reference_values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, text in sorted(messages.items()):
        source = reference_values.get(key)
        if source is None:
            errors.append(f"未知 key: {key}")
            continue
        source_params = extract_placeholders(source)
        target_params = extract_placeholders(text)
        if source_params != target_params:
            errors.append(f"参数不一致: {key} 默认={sorted(source_params)} 译文={sorted(target_params)}")
        source_markers = extract_locale_markers(source)
        target_markers = extract_locale_markers(text)
        if source_markers != target_markers:
            errors.append(f"tooltip/格式标记不一致: {key} 默认={source_markers} 译文={target_markers}")
    return errors


def write_user_locale(language: str, messages: dict[str, str]) -> Path:
    target = DATA_LOCALES_DIR / f"{language}.json"
    payload = load_locale(target)
    meta = payload.get("_meta") if isinstance(payload, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    payload["_meta"] = {
        **meta,
        "type": "user_locale",
        "language": language,
    }
    for key, text in messages.items():
        set_nested(payload, key, text)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="校验或导入翻译 workfile。导入只写 data/locales/<language>.json。")
    parser.add_argument("workfile", type=Path)
    parser.add_argument("--language", default="", help="覆盖 workfile _meta.language。")
    parser.add_argument("--import", dest="do_import", action="store_true", help="校验通过后导入到 data/locales。")
    parser.add_argument("--reference", type=Path, default=DEFAULT_LOCALE_PATH, help="参考语言包，默认 zh-CN.json。")
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    workfile = args.workfile if args.workfile.is_absolute() else ROOT / args.workfile
    reference = args.reference if args.reference.is_absolute() else ROOT / args.reference
    try:
        language, messages, errors = extract_messages(read_workfile(workfile), args.language)
        if not language:
            errors.append("缺少目标语言，请在 _meta.language 或 --language 中指定。")
        errors.extend(validate_messages(messages, flatten_string_values(load_locale(reference))))
    except Exception as exc:
        print(f"读取 workfile 失败: {exc}", file=sys.stderr)
        return 1

    if errors:
        limit = max(args.limit, 1)
        print(f"workfile 校验发现 {len(errors)} 个问题，显示前 {min(limit, len(errors))} 个：", file=sys.stderr)
        print("\n".join(errors[:limit]), file=sys.stderr)
        return 1
    if not messages:
        print("workfile 中没有可导入译文。", file=sys.stderr)
        return 1
    if args.do_import:
        target = write_user_locale(language, messages)
        print(f"已导入 {len(messages)} 条译文到 {target.relative_to(ROOT).as_posix()}")
    else:
        print(f"workfile 校验通过，可导入 {len(messages)} 条译文，目标语言: {language}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
