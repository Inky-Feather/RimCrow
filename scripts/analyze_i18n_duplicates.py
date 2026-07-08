from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCALE_PATH = ROOT / "frontend" / "src" / "locales" / "zh-CN.json"
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][\w]*)\}")


def flatten_strings(payload: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in payload.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, str):
            result[dotted] = value
        elif isinstance(value, Mapping):
            result.update(flatten_strings(value, dotted))
    return result


def placeholders(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(PLACEHOLDER_RE.findall(str(text or "")))))


def normalize_text(text: str) -> str:
    text = PLACEHOLDER_RE.sub("{}", str(text or ""))
    text = re.sub(r"[\s\u3000]+", "", text)
    return re.sub(r'[，。！？、：；,.!?:;“”"《》「」『』（）()\[\]【】\-—_·/\\]+', "", text)


def domain_of(key: str) -> str:
    parts = key.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else parts[0]


def print_group(title: str, groups: list[tuple[str, list[str]]], limit: int) -> None:
    print(f"\n# {title} ({len(groups)} groups)")
    for text, keys in groups[:limit]:
        domains = dict(Counter(domain_of(key) for key in keys))
        print(f"[{len(keys)}] {text!r} domains={domains}")
        for key in keys[:10]:
            print(f"  - {key}")
        if len(keys) > 10:
            print("  ...")


def analyze(locale_path: Path, limit: int, similar_limit: int, similar_threshold: float) -> None:
    payload = json.loads(locale_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise SystemExit(f"{locale_path} 不是 JSON 对象")
    values = flatten_strings(payload)

    exact: dict[str, list[str]] = defaultdict(list)
    for key, text in values.items():
        if text.strip():
            exact[text].append(key)
    exact_groups = sorted(
        ((text, keys) for text, keys in exact.items() if len(keys) > 1),
        key=lambda item: (-len(item[1]), item[0]),
    )

    normalized: dict[tuple[str, tuple[str, ...]], list[tuple[str, str]]] = defaultdict(list)
    for key, text in values.items():
        normalized_text = normalize_text(text)
        if len(normalized_text) >= 3:
            normalized[(normalized_text, placeholders(text))].append((key, text))
    normalized_groups = sorted(
        (
            (normalized_text, [f"{key} => {text!r}" for key, text in entries])
            for (normalized_text, _), entries in normalized.items()
            if len(entries) > 1 and len({text for _, text in entries}) > 1
        ),
        key=lambda item: (-len(item[1]), item[0]),
    )

    common_groups = [
        (text, keys)
        for text, keys in exact_groups
        if any(key.startswith("common.") for key in keys) and any(not key.startswith("common.") for key in keys)
    ]
    cross_domain_groups = [
        (text, keys)
        for text, keys in exact_groups
        if not any(key.startswith("common.") for key in keys) and len({domain_of(key) for key in keys}) > 1
    ]
    same_domain_groups = [
        (text, keys)
        for text, keys in exact_groups
        if not any(key.startswith("common.") for key in keys) and len({domain_of(key) for key in keys}) == 1
    ]

    pairs: list[tuple[float, str, str, str, str]] = []
    candidates = [
        (key, text, placeholders(text))
        for key, text in values.items()
        if 5 <= len(text) <= 100 and not text.startswith("^^")
    ]
    for index, (key_a, text_a, placeholders_a) in enumerate(candidates):
        for key_b, text_b, placeholders_b in candidates[index + 1:]:
            if text_a == text_b or placeholders_a != placeholders_b or abs(len(text_a) - len(text_b)) > 18:
                continue
            ratio = difflib.SequenceMatcher(None, text_a, text_b).ratio()
            if ratio >= similar_threshold:
                pairs.append((ratio, key_a, text_a, key_b, text_b))
    pairs.sort(key=lambda item: -item[0])

    print(f"Locale: {locale_path.relative_to(ROOT).as_posix() if locale_path.is_relative_to(ROOT) else locale_path}")
    print(f"Total keys: {len(values)}")
    print(f"Exact duplicate groups: {len(exact_groups)}, keys involved: {sum(len(keys) for _, keys in exact_groups)}")
    print(f"Normalized duplicate groups: {len(normalized_groups)}, keys involved: {sum(len(keys) for _, keys in normalized_groups)}")

    print_group("has common.* reuse candidates", common_groups, limit)
    print_group("cross-domain exact duplicates without common.*", cross_domain_groups, limit)
    print_group("same-domain exact duplicates", same_domain_groups, limit)
    print_group("normalized text differs only by punctuation/spacing", normalized_groups, limit)

    print(f"\n# similar pairs >= {similar_threshold} ({len(pairs)} pairs)")
    for ratio, key_a, text_a, key_b, text_b in pairs[:similar_limit]:
        print(f"{ratio:.3f}")
        print(f"  - {key_a} => {text_a!r}")
        print(f"  - {key_b} => {text_b!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="分析语言包里的重复、相关和相似文本。")
    parser.add_argument("--locale-file", type=Path, default=DEFAULT_LOCALE_PATH)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--similar-limit", type=int, default=60)
    parser.add_argument("--similar-threshold", type=float, default=0.88)
    args = parser.parse_args()

    locale_path = args.locale_file if args.locale_file.is_absolute() else ROOT / args.locale_file
    analyze(locale_path, args.limit, args.similar_limit, args.similar_threshold)


if __name__ == "__main__":
    main()
