from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from backend.utils.tools import normalize_package_id


HARD_NOISE_IDS = {
    "brrainz.harmony",
    "unlimitedhugs.hugslib",
    "ludeon.rimworld",
}

GENERIC_NAME_NOISE_TOKENS = {
    "pack",
    "patch",
    "addon",
    "continued",
    "forked",
    "translation",
    "translations",
    "localization",
    "localisation",
    "language",
    "lang",
    "mod",
}


def _is_language_pack_mod(mod: dict[str, Any] | None) -> bool:
    mod_type = str((mod or {}).get("user_mod_type") or (mod or {}).get("mod_type") or "").strip()
    return mod_type == "LanguagePack"


def _is_core_or_dlc(package_id: str) -> bool:
    normalized_id = normalize_package_id(package_id)
    return normalized_id == "ludeon.rimworld" or normalized_id.startswith("ludeon.rimworld.")


def _is_hard_noise(package_id: str) -> bool:
    normalized_id = normalize_package_id(package_id)
    return normalized_id in HARD_NOISE_IDS or _is_core_or_dlc(normalized_id)


def _extract_rule_package_ids(rules: list[dict[str, Any]] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        package_id = normalize_package_id(rule.get("package_id") or rule.get("target_id"))
        if not package_id or package_id in seen:
            continue
        seen.add(package_id)
        result.append(package_id)
    return result


def _extract_candidate_package_ids_from_mod(mod: dict[str, Any], category: str) -> list[str]:
    rules = mod.get("rules") or {}
    if isinstance(rules, dict) and isinstance(rules.get(category), list):
        return _extract_rule_package_ids(rules.get(category))
    if category == "dependencies":
        return _extract_rule_package_ids(mod.get("dependencies_mods"))
    if category == "load_after":
        return _extract_rule_package_ids(mod.get("load_after_mods"))
    return []


def _normalize_name(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[_\-+/()[\]{}|.,:;!?]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize_name(value: str) -> list[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return []
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [token for token in tokens if token and token not in GENERIC_NAME_NOISE_TOKENS]


def _name_similarity(left: str, right: str) -> float:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    seq_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = set(_tokenize_name(left_norm))
    right_tokens = set(_tokenize_name(right_norm))
    token_score = 0.0
    if left_tokens and right_tokens:
        token_score = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))

    containment_score = 0.0
    if left_norm in right_norm or right_norm in left_norm:
        containment_score = min(len(left_norm), len(right_norm)) / max(len(left_norm), len(right_norm))

    return max(seq_score * 0.6 + token_score * 0.4, containment_score)


def _build_asset_index(mods: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for mod in mods:
        package_id = normalize_package_id(mod.get("package_id"))
        if not package_id:
            continue
        index[package_id] = {
            "package_id": package_id,
            "name": mod.get("name") or "",
            "mod_type": mod.get("mod_type") or "",
            "user_mod_type": mod.get("user_mod_type") or "",
        }
    return index


def _get_user_rule_override(user_mod_rules: dict[str, Any] | None, package_id: str) -> tuple[list[str], bool]:
    if not user_mod_rules:
        return [], False
    rule = user_mod_rules.get(package_id, {}) or {}
    raw_owner_ids = rule.get("languagePackOwners")
    if not isinstance(raw_owner_ids, dict):
        return [], False

    raw_replace = bool(raw_owner_ids.get("replace"))
    raw_owner_ids = raw_owner_ids.get("owners", [])

    normalized_owner_ids = []
    seen = set()
    values = raw_owner_ids if isinstance(raw_owner_ids, list) else [raw_owner_ids]
    for owner_id in values:
        normalized_id = normalize_package_id(owner_id)
        if not normalized_id or normalized_id in seen:
            continue
        seen.add(normalized_id)
        normalized_owner_ids.append(normalized_id)
    return normalized_owner_ids, bool(raw_replace and normalized_owner_ids)


def _build_candidate(
    package_id: str,
    source_flags: set[str],
    language_pack: dict[str, Any],
    asset_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target = asset_index.get(package_id, {})
    target_name = str(target.get("name") or package_id)
    similarity = _name_similarity(language_pack.get("name") or "", target_name)
    known = bool(target)
    is_language_pack_target = _is_language_pack_mod(target)
    is_hard_noise = _is_hard_noise(package_id)

    score = 0
    if "dependency" in source_flags and "load_after" in source_flags:
        score += 80
    elif "dependency" in source_flags:
        score += 55
    elif "load_after" in source_flags:
        score += 35

    if known:
        score += 10
    else:
        score -= 6

    if is_language_pack_target:
        score -= 20

    if is_hard_noise:
        score -= 120

    score += round(similarity * 35)

    return {
        "package_id": package_id,
        "source_flags": sorted(source_flags),
        "is_hard_noise": is_hard_noise,
        "is_soft_noise": is_language_pack_target or not known,
        "name_similarity": round(similarity, 4),
        "score": score,
    }


def _pick_best_by_name_similarity(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not candidates:
        return None, None
    ordered = sorted(
        candidates,
        key=lambda item: (item.get("name_similarity", 0), item.get("score", 0)),
        reverse=True,
    )
    best = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None
    return best, second


def _resolve_candidate_set(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str]:
    if len(candidates) == 1:
        return (
            [candidates[0]],
            "single",
            "high",
        )

    dependency_candidates = [
        candidate for candidate in candidates
        if "dependency" in candidate["source_flags"]
    ]
    load_after_candidates = [
        candidate for candidate in candidates
        if "load_after" in candidate["source_flags"]
    ]

    if len(dependency_candidates) == 1:
        primary = dependency_candidates[0]
        competing = [
            candidate for candidate in candidates
            if candidate["package_id"] != primary["package_id"]
        ]
        if not competing or all(candidate["is_soft_noise"] for candidate in competing):
            return (
                [primary],
                "single",
                "high",
            )
        return (
            [primary],
            "single",
            "medium",
        )

    if not dependency_candidates and len(load_after_candidates) == 1:
        return (
            [load_after_candidates[0]],
            "single",
            "high",
        )

    if len(dependency_candidates) > 1:
        return (
            dependency_candidates,
            "multiple",
            "medium",
        )

    if len(load_after_candidates) > 1:
        best, second = _pick_best_by_name_similarity(load_after_candidates)
        if best:
            gap = best.get("name_similarity", 0) - (second.get("name_similarity", 0) if second else 0)
            if best.get("name_similarity", 0) >= 0.55 and gap >= 0.12:
                return (
                    [best],
                    "single",
                    "medium",
                )
        return (
            load_after_candidates,
            "multiple",
            "medium",
        )

    if candidates:
        best_by_score = max(candidates, key=lambda item: item.get("score", 0))
        return (
            [best_by_score],
            "single",
            "medium",
        )

    return ([], "unknown", "unknown")


def _finalize_result(
    owners: list[dict[str, Any]],
    relation_type: str,
    confidence: str,
    analyzed_owners: list[dict[str, Any]] | None = None,
    analyzed_relation_type: str | None = None,
    analyzed_confidence: str | None = None,
) -> dict[str, Any]:
    analyzed_owner_rows = analyzed_owners if analyzed_owners is not None else owners
    analyzed_relation_type = analyzed_relation_type if analyzed_relation_type is not None else relation_type
    analyzed_confidence = analyzed_confidence if analyzed_confidence is not None else confidence
    return {
        "owners": [
            {
                "package_id": owner["package_id"],
            }
            for owner in owners
        ],
        "analyzed_owners": [
            {
                "package_id": owner["package_id"],
            }
            for owner in analyzed_owner_rows
        ],
        "relation_type": relation_type,
        "summary_confidence": confidence,
        "analyzed_relation_type": analyzed_relation_type,
        "analyzed_summary_confidence": analyzed_confidence,
    }


def resolve_language_pack_ownership_for_mod(
    language_pack: dict[str, Any],
    asset_index: dict[str, dict[str, Any]],
    user_mod_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _is_language_pack_mod(language_pack):
        return {
            "owners": [],
            "analyzed_owners": [],
            "relation_type": "unknown",
            "summary_confidence": "unknown",
            "analyzed_relation_type": "unknown",
            "analyzed_summary_confidence": "unknown",
        }

    dependency_ids = _extract_candidate_package_ids_from_mod(language_pack, "dependencies")
    load_after_ids = _extract_candidate_package_ids_from_mod(language_pack, "load_after")
    candidate_sources: dict[str, set[str]] = {}

    for package_id in dependency_ids:
        candidate_sources.setdefault(package_id, set()).add("dependency")
    for package_id in load_after_ids:
        candidate_sources.setdefault(package_id, set()).add("load_after")

    pack_id = normalize_package_id(language_pack.get("package_id"))
    override_owner_ids, override_replace = _get_user_rule_override(user_mod_rules, pack_id)
    for package_id in override_owner_ids:
        candidate_sources.setdefault(package_id, set()).add("user_override")

    if not candidate_sources:
        return _finalize_result([], "unknown", "unknown")

    candidates = [
        _build_candidate(package_id, source_flags, language_pack, asset_index)
        for package_id, source_flags in candidate_sources.items()
    ]
    analyzed_candidates = [dict(candidate) for candidate in candidates]
    analyzed_effective_candidates = [candidate for candidate in analyzed_candidates if not candidate["is_hard_noise"]] or analyzed_candidates
    analyzed_owners, analyzed_relation_type, analyzed_confidence = _resolve_candidate_set(
        analyzed_effective_candidates,
    )

    if override_owner_ids:
        for candidate in candidates:
            if candidate["package_id"] not in override_owner_ids:
                continue
            candidate["score"] += 220 if override_replace else 120
    if override_owner_ids and override_replace:
        candidates = [candidate for candidate in candidates if candidate["package_id"] in override_owner_ids]
    effective_candidates = [candidate for candidate in candidates if not candidate["is_hard_noise"]] or candidates

    owners, relation_type, confidence = _resolve_candidate_set(effective_candidates)
    if owners:
        return _finalize_result(
            owners,
            relation_type,
            confidence,
            analyzed_owners=analyzed_owners,
            analyzed_relation_type=analyzed_relation_type,
            analyzed_confidence=analyzed_confidence,
        )

    return _finalize_result(
        [],
        "unknown",
        "unknown",
        analyzed_owners=analyzed_owners,
        analyzed_relation_type=analyzed_relation_type,
        analyzed_confidence=analyzed_confidence,
    )


def resolve_language_pack_ownership_for_mods(
    mods: list[dict[str, Any]],
    user_mod_rules: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    asset_index = _build_asset_index(mods)
    language_packs = [mod for mod in mods if _is_language_pack_mod(mod)]
    result: dict[str, dict[str, Any]] = {}
    for mod in language_packs:
        package_id = normalize_package_id(mod.get("package_id"))
        if not package_id:
            continue
        result[package_id] = resolve_language_pack_ownership_for_mod(
            mod,
            asset_index,
            user_mod_rules=user_mod_rules,
        )
    return result
