# Auto Sort And Rules

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains RimCrow auto sort, rule sources, rule priority, follow behavior, and issue hints. It is for users who have scanned mods and are ready to organize the enabled load order.

Remember this first: auto sort can give you a better base order, but it cannot guarantee that every mod combination is correct.

## What Auto Sort Does

Auto sort reads the current active list, mod dependency data, and available rules, then rearranges the enabled order.

It mainly handles:

- Required dependencies should load before the mods that need them.
- Explicit "load after" or "load before" rules.
- Top, bottom, and weight tendencies.
- Common order advice for language packs, compatibility patches, performance mods, and similar cases.

After sorting, still check red errors and yellow warnings.

## The Simple Sorting Principle

You can understand auto sort in three steps:

1. Handle required relationships first, such as dependencies and before/after rules.
2. Then apply broad position tendencies, such as top, bottom, and weights.
3. Finally do local cleanup, such as keeping related mods closer when this is safe.

Auto sort is not just sorting by name or subscription time. It protects important relationships first, then tries to make the result easier to read.

Example:

```text
A is a framework. B depends on A. C is B's language pack.
```

Sorting usually places A before B. If language-pack follow is enabled, C tries to stay near B instead of floating far away.

If rules conflict with each other, RimCrow tries to keep the more important and more trusted rules, then reports the rules that could not be satisfied.

## What Auto Sort Cannot Guarantee

Auto sort cannot judge every real compatibility case for you.

You still need to confirm these cases manually:

- A mod author did not write complete dependency information.
- Community rules do not cover the mod yet.
- Compatibility is only mentioned on the mod description page.
- The same PackageId exists from multiple sources.
- You are using a mod pack, test build, or old mod version.

## Rule Sources

RimCrow combines multiple rule sources. They can all affect sorting and issue detection.

### Native Rules

Native rules come from the mod's own `About.xml`, dependency declarations, and basic metadata.

They are usually the most reliable because they come from the mod files. Some mods still have incomplete metadata, so other rule sources may be needed.

### User Rules

User rules are rules you create for a mod. They are useful for long-term personal preferences.

Common uses:

- Require a mod to load before or after another mod.
- Set a weight.
- Ignore a hint you have confirmed is harmless.
- Fix a case not covered by community rules.

### Community Rules

Community rules come from a community-maintained sorting rule library. They can supplement sorting advice for many common mods.

Notes:

- Community rules are suggestions, not guarantees for every setup.
- The rule library needs updates, so old cache data may miss new mods.
- If a rule conflicts with your actual test result, use a user rule to adjust or override it.

### Workshop Rules

Workshop rules come from the offline Workshop database and related dependency information. They help identify relationships between Workshop items.

If **Use As Strong Dependency** is enabled, Workshop rules participate in dependency checks more strictly. If you are unsure, keep the default.

### Dynamic Rules

Dynamic rules work like conditional automation:

```text
If a mod matches some conditions -> apply a sorting action
```

They are useful for batch handling mods with shared traits, such as tag, type, author, or name.

## Effective Priority

The rule center lets you adjust rule source priority. Priority affects which source is trusted more when rules conflict.

Simple rules:

- Higher entries have higher priority.
- User rules are usually best placed high because they represent your final decision.
- If unsure, do not change global priority frequently. Fix specific mod problems first.

## Weights

Weights express sorting tendency. Lower numbers sort earlier. Higher numbers sort later.

Common meanings:

- Top: force near the start.
- Bottom: force near the end.
- Set weight: place the mod in a target weight range.
- Weight shift: move earlier or later from its base tendency.

Weights are good for saying "this type of mod should generally be earlier or later". They should not replace real dependency rules.

In short:

- Dependencies and before/after rules are more like requirements.
- Weights are preferences when no hard relationship blocks them.
- Top and bottom are stronger than normal weights. Use them only for mods that really need the ends.

Do not casually set too many mods to top or bottom. Too many end anchors can make the result harder to understand.

## Follow Behavior

Follow behavior is a local cleanup step after auto sort. Its goal is not to change rules, but to keep related mods closer.

Related switches are in settings. When disabled, sorting still uses dependencies, rules, and weights, but without this extra cleanup.

### Language Packs Follow Targets

When enabled, language packs try to stay after their main mod or last enabled prerequisite.

Effects:

- Language packs are easier to check together with their main mods.
- Language packs are less likely to pile up far away at the bottom.
- Large lists with many language packs are easier to read.

Notes:

- If no target is found, the language pack keeps its normal lower position.
- If moving it would break dependencies or sorting rules, RimCrow will not force it.
- If ownership detection is wrong, adjust by hand or write a user rule.

### Regular Mods Follow Dependencies

When enabled, regular mods try to stay near their last enabled direct dependency.

Effects:

- Related mods or same-series mods stay closer.
- The list is less scattered by broad weight ranges alone.
- Dependency inspection becomes more intuitive.

Notes:

- This mainly moves mods within the same weight area. It does not jump across important sections freely.
- Top, bottom, and language-pack special positions are not forced apart by regular follow behavior.
- If before/after rules do not allow the move, RimCrow keeps the safer order.

### Follow Does Not Mean Forced Adjacency

Follow means "try to stay close", not "must be directly next to each other".

If dependencies, patches, frameworks, or other rules must sit between two related mods, they may still be separated. This is usually not a sorting failure. It is protecting more important load relationships.

## How Rule Conflicts Are Handled

Sometimes rules form a loop, making it impossible to satisfy every rule.

Example:

```text
A must be before B
B must be before C
C must be before A
```

No order can satisfy all three.

RimCrow first produces the best current order it can, then shows **Sort Rule Conflict**. In the conflict view:

- Red rule lines are rules ignored in this sort result.
- Other rule lines are still kept.
- The right side shows rule sources so you can decide what to adjust.

Suggested handling:

- If a user rule is wrong, edit or delete it.
- If a dynamic rule is too broad, narrow its condition or disable it.
- If a community or Workshop rule does not fit your setup, disable that source for the affected mod.
- If it is a native rule, it comes from the mod files and cannot be individually disabled. Adjust other rules or handle it manually.

A conflict hint does not mean auto sort completely failed. It means RimCrow produced a usable current result, but at least one rule could not be satisfied at the same time.

## Issue Hints

### Missing Dependencies

The active list is missing a required or suggested prerequisite.

What to do:

- If you need this mod, add the dependency.
- If it is optional, confirm whether it matters.
- If it came from an imported list, subscribe or download the missing item.

### Order Errors

The current order does not satisfy a dependency or sorting rule.

What to do:

- Try auto sort first.
- If it is still wrong, adjust by hand.
- If you need the same order long term, write a user rule.

### Incompatibility

Rules say two mods should not be used together, or a compatibility patch may be needed.

What to do:

- Check the mod description or Workshop page.
- Keep only one of them.
- Install a compatibility patch.
- Ignore or write a rule only after you confirm it is harmless.

### Language Pack Hints

Language packs usually need to follow their main mod. RimCrow tries to identify ownership, but some language packs have incomplete metadata.

What to do:

- Check whether the main mod is enabled.
- Place the language pack in a suitable position.
- If ownership is wrong, specify it with a rule.

## Recommended Workflow

### Normal Sorting

1. Scan.
2. Enable the mods you need.
3. Click auto sort.
4. Check red errors.
5. Handle problems that auto sort cannot solve.
6. Save.

### Creating Your Own Rules

Use this when the same sorting problem appears repeatedly.

1. Find the related mod.
2. Open rule editing.
3. Add before/after, weight, or ignore rules.
4. Save the rule.
5. Run auto sort again and check the result.

Do not write many rules for one-time tests. Dragging by hand is simpler for temporary changes.

### Using Dynamic Rules

Use dynamic rules when you already organize mods by tags, types, or groups and want a batch sorting effect.

Examples:

- Mods tagged "language pack" go later.
- A framework series by one author goes earlier.
- Visual replacements go later.

Dynamic rules can affect many mods. Before saving, make sure the condition is not too broad.

## FAQ

### Are More Rules Always Better?

No. Too many rules, conflicting sources, or broad dynamic conditions can make results harder to understand. Keep rules that are useful and explainable.

### What If Community Rules Conflict With User Rules?

If you know your setup needs a specific order, express it with a user rule. User rules are best for your final decision.

### Why Did Nothing Change After Editing Rules?

Usually you need to run auto sort again. Saving rules changes the basis for sorting, but it does not always rearrange the current list immediately.

### Is It Safe To Ignore Warnings?

Only ignore a warning after you understand it and confirm it does not affect your current profile. Do not use ignore to hide red errors.

## Notes

- Scan before auto sort so mod data is current.
- Save after sorting to write the load order.
- Use user rules for long-term decisions. Use manual drag for temporary tests.
- Keep dynamic rule conditions narrow to avoid affecting too many mods.
