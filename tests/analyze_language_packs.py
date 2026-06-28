from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.models import ModAsset, UserModData, db  # noqa: E402
from backend.database.runtime import init_db  # noqa: E402
from backend.settings import DATA_DIR  # noqa: E402
from backend.utils.tools import normalize_package_id  # noqa: E402


DB_PATH = str(DATA_DIR / "mod_manager.db")
REPORT_DIR = PROJECT_ROOT / "cache" / "analysis"
REPORT_PATH = REPORT_DIR / "language_pack_analysis.json"
TOP_LIMIT = 50
SAMPLE_LIMIT = 30
NOISE_MIN_HITS = 5


def extract_rule_package_ids(rules):
    ids = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        package_id = normalize_package_id(
            rule.get("package_id")
            or rule.get("target_id")
        )
        if package_id:
            ids.append(package_id)
    return list(dict.fromkeys(ids))


def compact_target(package_id, asset_index):
    mod = asset_index.get(package_id)
    if not mod:
        return {
            "package_id": package_id,
            "known": False,
            "name": "",
            "mod_type": "",
            "user_mod_type": "",
        }
    return {
        "package_id": package_id,
        "known": True,
        "name": mod.get("name") or "",
        "mod_type": mod.get("mod_type") or "",
        "user_mod_type": mod.get("user_mod_type") or "",
    }


def build_pack_record(row, asset_index):
    package_id = normalize_package_id(row.get("package_id"))
    dependencies = extract_rule_package_ids(row.get("dependencies_mods"))
    load_after = extract_rule_package_ids(row.get("load_after_mods"))
    combined = list(dict.fromkeys(dependencies + load_after))
    return {
        "package_id": package_id,
        "name": row.get("name") or "",
        "dependencies": dependencies,
        "load_after": load_after,
        "combined": combined,
        "dependency_targets": [compact_target(target_id, asset_index) for target_id in dependencies],
        "load_after_targets": [compact_target(target_id, asset_index) for target_id in load_after],
        "combined_targets": [compact_target(target_id, asset_index) for target_id in combined],
    }


def summarize_pack(pack):
    return {
        "package_id": pack["package_id"],
        "name": pack["name"],
        "dependencies": pack["dependency_targets"],
        "load_after": pack["load_after_targets"],
    }


def sample_packs(packs, limit=SAMPLE_LIMIT):
    return [summarize_pack(pack) for pack in packs[:limit]]


def counter_to_sorted_dict(counter):
    return {str(key): value for key, value in sorted(counter.items(), key=lambda item: item[0])}


def top_targets(counter, asset_index, limit=TOP_LIMIT):
    result = []
    for package_id, hits in counter.most_common(limit):
        target = compact_target(package_id, asset_index)
        result.append({
            **target,
            "hits": hits,
        })
    return result


def print_section(title, payload):
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main():
    if not init_db(DB_PATH):
        raise SystemExit(f"failed to init db: {DB_PATH}")

    user_type_index = {
        normalize_package_id(row.get("mod_id")): row.get("user_mod_type") or ""
        for row in UserModData.select(
            UserModData.mod_id,
            UserModData.user_mod_type,
        ).dicts()
        if normalize_package_id(row.get("mod_id"))
    }

    asset_rows = list(
        ModAsset.select(
            ModAsset.package_id,
            ModAsset.name,
            ModAsset.mod_type,
        ).dicts()
    )
    asset_index = {
        normalize_package_id(row.get("package_id")): {
            "name": row.get("name") or "",
            "mod_type": row.get("mod_type") or "",
            "user_mod_type": user_type_index.get(normalize_package_id(row.get("package_id")), ""),
        }
        for row in asset_rows
        if normalize_package_id(row.get("package_id"))
    }

    rows = list(
        ModAsset.select(
            ModAsset.package_id,
            ModAsset.name,
            ModAsset.dependencies_mods,
            ModAsset.load_after_mods,
        )
        .where(ModAsset.mod_type == "LanguagePack")
        .dicts()
    )

    packs = [build_pack_record(row, asset_index) for row in rows]
    total = len(packs)

    dep_count_dist = Counter()
    after_count_dist = Counter()
    combined_count_dist = Counter()

    dependency_target_hits = Counter()
    load_after_target_hits = Counter()
    combined_target_hits = Counter()

    unknown_dependency_hits = Counter()
    unknown_load_after_hits = Counter()
    noise_like_hits = Counter()

    exactly_one_dependency = []
    exactly_one_load_after_only = []
    same_single_dep_and_after = []
    single_dependency_multi_after = []
    multi_dependency = []
    multi_load_after = []
    dep_after_disjoint = []
    empty_rules = []
    dependency_contains_framework_like = []
    load_after_contains_framework_like = []

    framework_like_ids = {
        "brrainz.harmony",
        "unlimitedhugs.hugslib",
        "ludeon.rimworld",
        "ludeon.rimworld.royalty",
        "ludeon.rimworld.ideology",
        "ludeon.rimworld.biotech",
        "ludeon.rimworld.anomaly",
        "ludeon.rimworld.odyssey",
    }

    for pack in packs:
        deps = pack["dependencies"]
        afters = pack["load_after"]
        combined = pack["combined"]

        dep_count_dist[len(deps)] += 1
        after_count_dist[len(afters)] += 1
        combined_count_dist[len(combined)] += 1

        dependency_target_hits.update(deps)
        load_after_target_hits.update(afters)
        combined_target_hits.update(combined)

        for target_id in deps:
            if target_id not in asset_index:
                unknown_dependency_hits[target_id] += 1
        for target_id in afters:
            if target_id not in asset_index:
                unknown_load_after_hits[target_id] += 1
        for target_id in combined:
            if target_id in framework_like_ids:
                noise_like_hits[target_id] += 1

        if not combined:
            empty_rules.append(pack)
        if len(deps) == 1:
            exactly_one_dependency.append(pack)
        if len(afters) == 1 and not deps:
            exactly_one_load_after_only.append(pack)
        if len(deps) == 1 and len(afters) == 1 and deps[0] == afters[0]:
            same_single_dep_and_after.append(pack)
        if len(deps) == 1 and len(afters) > 1:
            single_dependency_multi_after.append(pack)
        if len(deps) > 1:
            multi_dependency.append(pack)
        if len(afters) > 1:
            multi_load_after.append(pack)
        if deps and afters and set(deps) != set(afters):
            dep_after_disjoint.append(pack)
        if any(target_id in framework_like_ids for target_id in deps):
            dependency_contains_framework_like.append(pack)
        if any(target_id in framework_like_ids for target_id in afters):
            load_after_contains_framework_like.append(pack)

    auto_noise_candidates = []
    for package_id, hits in combined_target_hits.most_common():
        if hits < NOISE_MIN_HITS:
            continue
        target = compact_target(package_id, asset_index)
        auto_noise_candidates.append({
            **target,
            "hits": hits,
            "dependency_hits": dependency_target_hits[package_id],
            "load_after_hits": load_after_target_hits[package_id],
        })

    report = {
        "meta": {
            "db_path": DB_PATH,
            "report_path": str(REPORT_PATH),
            "language_pack_total": total,
        },
        "summary": {
            "dependency_count_distribution": counter_to_sorted_dict(dep_count_dist),
            "load_after_count_distribution": counter_to_sorted_dict(after_count_dist),
            "combined_target_count_distribution": counter_to_sorted_dict(combined_count_dist),
            "empty_rules": len(empty_rules),
            "exactly_one_dependency": len(exactly_one_dependency),
            "exactly_one_load_after_only": len(exactly_one_load_after_only),
            "same_single_dep_and_after": len(same_single_dep_and_after),
            "single_dependency_multi_after": len(single_dependency_multi_after),
            "multi_dependency": len(multi_dependency),
            "multi_load_after": len(multi_load_after),
            "dep_after_disjoint": len(dep_after_disjoint),
            "dependency_contains_framework_like": len(dependency_contains_framework_like),
            "load_after_contains_framework_like": len(load_after_contains_framework_like),
        },
        "top_targets": {
            "dependencies": top_targets(dependency_target_hits, asset_index),
            "load_after": top_targets(load_after_target_hits, asset_index),
            "combined": top_targets(combined_target_hits, asset_index),
            "framework_like_known": top_targets(noise_like_hits, asset_index, limit=TOP_LIMIT),
            "auto_noise_candidates": auto_noise_candidates[:TOP_LIMIT],
            "unknown_dependencies": top_targets(unknown_dependency_hits, asset_index, limit=TOP_LIMIT),
            "unknown_load_after": top_targets(unknown_load_after_hits, asset_index, limit=TOP_LIMIT),
        },
        "samples": {
            "empty_rules": sample_packs(empty_rules),
            "exactly_one_dependency": sample_packs(exactly_one_dependency),
            "exactly_one_load_after_only": sample_packs(exactly_one_load_after_only),
            "same_single_dep_and_after": sample_packs(same_single_dep_and_after),
            "single_dependency_multi_after": sample_packs(single_dependency_multi_after),
            "multi_dependency": sample_packs(multi_dependency),
            "multi_load_after": sample_packs(multi_load_after),
            "dep_after_disjoint": sample_packs(dep_after_disjoint),
            "dependency_contains_framework_like": sample_packs(dependency_contains_framework_like),
            "load_after_contains_framework_like": sample_packs(load_after_contains_framework_like),
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print_section("Meta", report["meta"])
    print_section("Summary", report["summary"])
    print_section("Top Combined Targets", report["top_targets"]["combined"][:20])
    print_section("Auto Noise Candidates", report["top_targets"]["auto_noise_candidates"][:20])
    print_section("Single Dependency Multi LoadAfter Samples", report["samples"]["single_dependency_multi_after"][:10])
    print_section("Multi LoadAfter Samples", report["samples"]["multi_load_after"][:10])
    print(f"\nreport written to: {REPORT_PATH}")

    if not db.is_closed():
        db.close()


if __name__ == "__main__":
    main()
