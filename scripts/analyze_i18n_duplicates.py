from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCALE_PATH = ROOT / "frontend" / "src" / "locales" / "zh-CN.json"
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][\w.-]*)\}")


def configure_stdout() -> None:
    """避免 Windows GBK 控制台输出多语言文本时报 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def flatten_strings(payload: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in payload.items():
        if not prefix and key == "_meta":
            continue
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


def build_analysis(locale_path: Path, similar_threshold: float) -> dict[str, Any]:
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

    return {
        "locale": locale_path.relative_to(ROOT).as_posix() if locale_path.is_relative_to(ROOT) else str(locale_path),
        "total_keys": len(values),
        "exact_duplicate_groups": [
            {"text": text, "keys": keys, "domains": dict(Counter(domain_of(key) for key in keys))}
            for text, keys in exact_groups
        ],
        "normalized_duplicate_groups": [
            {"normalized": normalized_text, "items": entries}
            for normalized_text, entries in normalized_groups
        ],
        "common_reuse_candidates": [
            {"text": text, "keys": keys, "domains": dict(Counter(domain_of(key) for key in keys))}
            for text, keys in common_groups
        ],
        "cross_domain_exact_duplicates": [
            {"text": text, "keys": keys, "domains": dict(Counter(domain_of(key) for key in keys))}
            for text, keys in cross_domain_groups
        ],
        "same_domain_exact_duplicates": [
            {"text": text, "keys": keys, "domains": dict(Counter(domain_of(key) for key in keys))}
            for text, keys in same_domain_groups
        ],
        "similar_pairs": [
            {"ratio": ratio, "a": {"key": key_a, "text": text_a}, "b": {"key": key_b, "text": text_b}}
            for ratio, key_a, text_a, key_b, text_b in pairs
        ],
    }


def analyze(locale_path: Path, limit: int, similar_limit: int, similar_threshold: float, as_json: bool) -> None:
    result = build_analysis(locale_path, similar_threshold)
    if as_json:
        result = dict(result)
        for key in (
            "exact_duplicate_groups",
            "normalized_duplicate_groups",
            "common_reuse_candidates",
            "cross_domain_exact_duplicates",
            "same_domain_exact_duplicates",
        ):
            result[key] = result[key][:limit]
        result["similar_pairs"] = result["similar_pairs"][:similar_limit]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    exact_groups = [(item["text"], item["keys"]) for item in result["exact_duplicate_groups"]]
    normalized_groups = [(item["normalized"], item["items"]) for item in result["normalized_duplicate_groups"]]
    common_groups = [(item["text"], item["keys"]) for item in result["common_reuse_candidates"]]
    cross_domain_groups = [(item["text"], item["keys"]) for item in result["cross_domain_exact_duplicates"]]
    same_domain_groups = [(item["text"], item["keys"]) for item in result["same_domain_exact_duplicates"]]

    print(f"Locale: {result['locale']}")
    print(f"Total keys: {result['total_keys']}")
    print(f"Exact duplicate groups: {len(exact_groups)}, keys involved: {sum(len(keys) for _, keys in exact_groups)}")
    print(f"Normalized duplicate groups: {len(normalized_groups)}, keys involved: {sum(len(keys) for _, keys in normalized_groups)}")

    print_group("has common.* reuse candidates", common_groups, limit)
    print_group("cross-domain exact duplicates without common.*", cross_domain_groups, limit)
    print_group("same-domain exact duplicates", same_domain_groups, limit)
    print_group("normalized text differs only by punctuation/spacing", normalized_groups, limit)

    print(f"\n# similar pairs >= {similar_threshold} ({len(result['similar_pairs'])} pairs)")
    for item in result["similar_pairs"][:similar_limit]:
        print(f"{item['ratio']:.3f}")
        print(f"  - {item['a']['key']} => {item['a']['text']!r}")
        print(f"  - {item['b']['key']} => {item['b']['text']!r}")


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="分析语言包里的重复、相关和相似文本。")
    parser.add_argument("--locale-file", type=Path, default=DEFAULT_LOCALE_PATH)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--similar-limit", type=int, default=60)
    parser.add_argument("--similar-threshold", type=float, default=0.88)
    parser.add_argument("--json", action="store_true", help="输出完整 JSON，便于自动化统计和对比。")
    args = parser.parse_args()

    locale_path = args.locale_file if args.locale_file.is_absolute() else ROOT / args.locale_file
    analyze(locale_path, args.limit, args.similar_limit, args.similar_threshold, args.json)


if __name__ == "__main__":
    main()
