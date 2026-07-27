from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.i18n.language_registry import get_language_spec, normalize_language_code  # noqa: E402
from extract_i18n_messages import BUILTIN_LOCALES_DIR, UNTRANSLATED_PREFIX, configure_stdout, load_locale  # noqa: E402


def source_path(value: str) -> Path:
    raw = str(value or "").strip()
    path = Path(raw)
    if path.suffix == ".json":
        return path if path.is_absolute() else ROOT / path
    return BUILTIN_LOCALES_DIR / f"{raw}.json"


def build_locale_body(node: Any, mode: str) -> Any:
    if isinstance(node, Mapping):
        return {key: build_locale_body(value, mode) for key, value in node.items() if key != "_meta"}
    if not isinstance(node, str):
        return node
    if mode == "source":
        return node
    if mode == "untranslated":
        return f"{UNTRANSLATED_PREFIX}{node}"
    return ""


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="按现有语言包结构创建一个完整的新语言包骨架，不负责翻译。")
    parser.add_argument("--lang", required=True, help="目标语言码，例如 ru、ko、de。")
    parser.add_argument("--from", dest="source", default="en", help="参考语言包语言码或 JSON 路径，默认 en。")
    parser.add_argument("--mode", choices=("empty", "untranslated", "source"), default="empty", help="字符串填充值：空、未翻译标记、复制源文本。")
    parser.add_argument("--output-dir", type=Path, default=BUILTIN_LOCALES_DIR, help="输出目录，默认 frontend/src/locales。")
    parser.add_argument("--label", default="", help="覆盖 _meta.label。")
    parser.add_argument("--name", default="", help="覆盖 _meta.name。")
    parser.add_argument("--force", action="store_true", help="允许覆盖已有文件。")
    args = parser.parse_args()

    language = normalize_language_code(args.lang)
    if not language:
        print("语言码不能为空。", file=sys.stderr)
        return 1
    spec = get_language_spec(language)
    source_locale_path = source_path(args.source)
    source_payload = load_locale(source_locale_path)
    if not source_payload:
        print(f"参考语言包不存在或格式无效: {source_locale_path}", file=sys.stderr)
        return 1

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    target_path = output_dir / f"{language}.json"
    if target_path.exists() and not args.force:
        print(f"目标文件已存在，使用 --force 覆盖: {target_path}", file=sys.stderr)
        return 1

    payload = {
        "_meta": {
            "type": "builtin_locale" if output_dir.resolve() == BUILTIN_LOCALES_DIR.resolve() else "user_locale",
            "language": language,
            "label": args.label or (spec.label if spec else language),
            "name": args.name or (spec.english_name if spec else language),
        },
        **build_locale_body(source_payload, args.mode),
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已创建语言包: {target_path.relative_to(ROOT).as_posix() if target_path.is_relative_to(ROOT) else target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
