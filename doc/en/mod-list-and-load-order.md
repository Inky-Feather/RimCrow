# Mod List And Load Order

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains how to use RimCrow's main mod lists, and which actions affect the load order that RimWorld actually reads.

Simple view:

- Inactive list: mods you own but do not load right now.
- Active list: the real order loaded by the game.
- Temp list: a manager-only staging area, not used by the game.
- Disabled list: mods explicitly blocked from entering the game.
- Save: writes the current Active list order to the current profile's game config.

## Where Mods Come From

After scanning, RimCrow shows mods from several sources in one management view:

- Local mods: mods under the game folder's `Mods` directory.
- Steam Workshop mods: mods under the Steam Workshop folder.
- Manager mods: mods downloaded by RimCrow through SteamCMD, Git, or direct links.
- Official content: the base game and DLC.

Source affects deployment, updates, and deletion. When duplicates or coexisting versions appear, check the source instead of judging by mod name only.

## The Four Lists

### Inactive List

This contains mods that are not enabled in the current profile. They still exist on disk, in the Workshop library, or in the manager library.

Good for:

- Mods you do not use right now.
- Mods waiting for testing.
- Mods with conflicts that you do not want to delete.

Notes:

- Inactive does not mean deleted.
- Inactive mods can still be searched, grouped, tagged, or enabled again.
- If you only do not need a mod today, inactive is usually better than disabled.

### Active List

This is the current profile's real load order. Higher mods load earlier. Lower mods load later.

Common pattern:

- Frameworks, libraries, and official content are usually early.
- Normal content mods are usually in the middle.
- Patches, language packs, performance mods, and final fixes are usually later.

Still follow mod descriptions, rule hints, and actual testing.

### Temp List

The temporary list is in the right-side helper panel. It works like a staging area for mods you are organizing, testing, or preparing to move in bulk.

Good for:

- Picking candidates from the Inactive list.
- Inspecting an imported list without enabling it.
- Keeping test candidates aside before a test run.
- Temporarily gathering one type of mod while organizing a large list.

Notes:

- Mods in the temporary list do not enter the game load order.
- The temporary list is only an organizing state in RimCrow. Do not treat it as a backup.
- The **Save temporary list** setting controls whether it is restored per profile. If the setting is off, mods in the temporary list return to the top of the Inactive list when saving.
- For long-term mod sets, use groups or backups instead.

### Disabled List

The Disabled list is in the right-side helper panel. It contains mods you clearly do not want the game to see.

Good for:

- Mods confirmed to cause conflicts.
- One copy among several duplicates that should not participate in the current profile.
- Mods disabled from conflict handling or inventory management.
- Strict mod-pack setups where the visible mod range must be controlled.

Notes:

- Disabled is stronger than inactive. Inactive means "not loaded". Disabled means "try to keep the game from seeing it".
- Disabled mods can be filtered, sorted, and re-enabled from the Disabled list.
- Delete and unsubscribe actions affect real sources. Check path and source first.
- With strict disabled mode enabled, scans keep disabled records. If something outside RimCrow restores the mod, RimCrow tries to disable it again.
- For temporary testing, use inactive or temporary first. Disable only when you clearly do not want it in the profile.

## Common Actions

### Enable And Move To Inactive

- Double-click a mod to enable it or move it to Inactive.
- Drag it to another list.
- Select multiple mods for batch enable or batch move to Inactive.

Enabling adds a mod to the current profile's load order. It does not copy files. Moving a mod to Inactive does not delete files.

Do not confuse this with **Disable**. Disable is a stronger action that makes the whole mod temporarily invisible to the game.

### Double-Click

Double-click is the fastest enable/disable action:

- In the Inactive list: move to the Active list.
- In the Active list: move back to the Inactive list.

After double-clicking into the active list, RimCrow tries to insert the mod at a reasonable position allowed by current sorting rules. Save after changes, otherwise the game will not read the new order.

### Drag Sorting

Dragging inside the active list changes load order. The change must be saved before it writes to the game config.

After manual dragging, check issue hints again. It is easy to drag a dependency into a wrong position.

When filtering or view sorting is active, the list is mainly for review. Dragging usually cannot change the real order, but you can still drag selected mods out to other lists. To edit the real order, move target mods to the temporary list, clear filters and view sorting, then move them back.

### Multi-Select

Common selection methods:

- Click: select one mod.
- `Ctrl+Click`: add or remove one mod from selection.
- `Shift+Click`: select the continuous range from the last selected position to the clicked position.
- `Ctrl+Shift+Click`: add a continuous range while keeping previous selection.
- `Ctrl+A`: select all currently visible items or filter results.

Before batch actions, confirm the active filter. You may be operating only on filtered results.

### Drag Range Selection

The index column or selection trigger area supports drag range selection. Hold the left mouse button and drag from one mod to another to select the visible range between them.

Good for:

- Selecting a continuous block for batch enable, disable, move, or tagging.
- Working faster than many `Ctrl` clicks in large lists.
- Narrowing the list with filters, then selecting a visible range.

Notes:

- Drag range selection follows the current visible order.
- Hold `Ctrl` while dragging to add the range to existing selection.
- If you start dragging from the mod card itself, it may start drag sorting. For range selection, start from the index column or selection trigger area.

### Multi-Select Order

Some actions, such as creating interlocks or batch moving, use the order of selected items. Different selection methods produce that order differently.

Range selection and `Shift` selection are intuitive:

- Drag range selection follows the current list display order.
- `Shift+Click` also follows the current list display order.

So when you create an interlock with range selection or `Shift`, the interlock order is usually the same as the top-to-bottom order on screen. This also applies when filters or issue filters are active.

`Ctrl` multi-select is different. It depends on click order, because clicks can jump around. If you click item 20, then item 5, then item 12, the interlock may look "out of order". It is not random. It follows the order you clicked.

For interlocks:

- Continuous mods: prefer drag range selection or `Shift`.
- Scattered mods: `Ctrl` works, but check the selected order before creating the interlock.
- If the result is unexpected, remove the interlock, then select again in display order.

### Right-Click Menu

The right-click menu handles common actions for one or more mods:

- Open mod folder.
- Open Workshop page.
- Edit alias, tags, notes.
- Enable, disable, delete, subscribe, or unsubscribe.
- Open rule editing or source handling.

For actions that delete or remove something, check the source first. Deleting local files, deleting Workshop files, and unsubscribing are different actions.

### Interlock

Interlock keeps several mods as a group when they should stay next to each other. After creating an interlock, selecting one member also brings the other members. Dragging or moving the group tries to preserve its internal order.

Good for:

- A main mod and its dedicated patch.
- A framework, extension, and compatibility patch set that should move together.
- Mods you do not want to find and regroup manually every time.

Common actions:

- Select multiple mods, then create an interlock from the right-click menu.
- Select an existing interlock member, then remove the interlock from the right-click menu.
- When "missing interlocked mod" or "interlock order error" appears, follow the hint to add, download, subscribe, remove invalid members, or sort again.

Notes:

- Interlock is not a dependency rule. It means "these should stay grouped", not "these are required dependencies".
- Do not interlock too many unrelated mods. It makes later sorting and moving heavier.
- Auto sort still uses dependencies, rules, and weights. Interlock is only one constraint.

## Search And Filter

The main list has two inputs with different purposes:

- Search locate: does not change list contents. It jumps to matching items. Left-click goes next, right-click goes previous.
- Filter: narrows the visible list to matching mods.

After filtering, check the item count. Many "missing mod" cases are just active filters.

### Basic Syntax

Common syntax:

- Keyword: fuzzy search in default fields.
- `field:keyword`: search only in a specific field.
- `-field:keyword`: exclude matching mods.
- `field:+` / `field:-` / `field:_`: check whether a field has a value, has no value, or is unknown.
- Multiple conditions can use AND or OR logic.

Default keyword search matches name, alias, and author. Package ID, Workshop ID, tags, and source are more accurate with field search.

Use `Tab` to apply suggestions. With empty input, suggestions show available fields.

### AND / OR Logic

| Logic | Meaning | Example |
| --- | --- | --- |
| AND | Show only mods matching every condition | `tags:performance` + `source:workshop` |
| OR | Show mods matching any condition | `tags:performance` + `tags:UI` |

Use AND for troubleshooting. Use OR when finding similar mods.

### Common Fields

| Field | Meaning | Example |
| --- | --- | --- |
| `name` | Mod name | `name:Harmony` |
| `alias_name` | Custom alias | `alias_name:core` |
| `author` | Author | `author:Oskar` |
| `package_id` | Package ID | `package_id:ludeon` |
| `workshop_id` | Workshop ID | `workshop_id:2009463077` |
| `tags` | Tags | `tags:performance` |
| `groups` | Groups | `groups:medieval` |
| `sign_color` | Color mark | `sign_color:red` |
| `mod_type` | Type | `mod_type:language` |
| `source` | Source | `source:workshop` |
| `store` | Storage location | `store:self` |
| `supported_versions` | Supported versions | `supported_versions:1.6` |
| `supported_languages` | Supported languages | `supported_languages:zh` |
| `multiplayer_compat` | Multiplayer compatibility | `multiplayer_compat:compatible` |
| `ignored_issues` | Ignored issues | `ignored_issues:missing` |

Field suggestions in the input are the best reference. Some fields also have shorter aliases.

### State Fields

State fields are useful for checking whether something exists:

| Field | Meaning | Example |
| --- | --- | --- |
| `last_active` | Was enabled recently | `last_active:+` |
| `coexist_variant` | Has coexisting versions | `coexist_variant:+` |
| `shadow_paths` | Has disabled copies | `shadow_paths:+` |
| `replacement` | Has replacement | `replacement:+` |
| `save_breaking` | Marked as save-breaking risk | `save_breaking:+` |

Value meanings:

- `+`: has value / yes.
- `-`: no value / no.
- `_`: unknown / empty.

Examples:

- `replacement:+`: show mods with replacements.
- `save_breaking:+`: show mods with save-breaking risk.
- `coexist_variant:-`: show mods without coexisting versions.

### Exclusion Search

Add `-` before a field to exclude matches.

Examples:

- `-tags:test`: hide mods tagged as test.
- `-source:workshop`: hide Workshop sources.
- `-author:unknown`: exclude items whose author contains unknown.

Exclusion can be combined with other conditions. For example, `tags:performance` + `-source:local` means mods tagged as performance but not from local source.

### Search And Sorting Notes

- Filters and view sorting are mainly for review. They do not mean the real load order changed.
- When filtering or sorting is active, dragging usually cannot change the actual order.
- Clear filters and restore default sorting to see the real current list order.
- Search locate does not change visible content. Filter does.
- `Ctrl+A`, `Shift` selection, and drag range selection follow the current visible list.

### Search In The Disabled List

The Disabled list uses a simpler search box. It can filter by name, package ID, Workshop ID, and path. It can also sort by source, time, size, and name.

Disabled-list sorting is only for viewing. It does not mean these mods enter the load order.

## Groups, Tags, Colors, And Notes

These features help organization. They do not always affect game loading behavior.

### Groups

Groups work like collections or themed sets, such as "medieval pack", "test pack", or "common UI".

Dragging a group to the Active list or Inactive list can batch enable mods or move them to Inactive. The group itself is not the game load order file.

### Tags

Tags are long-term marks, such as "performance", "race", "building", or "to test". They can be used later for search, filters, and dynamic rules.

### Colors

Colors help you quickly identify important mods, such as core frameworks, problem mods, or mods you often edit.

### Notes

Notes are for your own decisions, such as "do not update this version", "must load after X", or "not for multiplayer".

## Issue Hints

Issue hints come from dependency, order, compatibility, missing-file, language-pack, interlock, and multiplayer compatibility checks. They are not decoration. Before launch, at least check the issue count in the active list.

Simple severity guide:

- Red errors: handle first. They may affect game loading, cause launch failure, trigger save errors, or lead to more errors.
- Yellow warnings: check when relevant. They usually do not immediately break the game, but may affect order, language display, interlock integrity, or specific play styles.
- Blue info: usually explains the current state, such as a dependency being satisfied by a replacement.

If time is limited, handle red errors first. Decide on yellow warnings based on what you care about.

### Where To See Issues

Common entry points:

- Issue count in the list header.
- Hint icons on mod rows. Hover to see details.
- Issue filter. Click the issue count to show only mods with issues.
- Right-click menu. Some issues support ignore, restore warning, subscribe, download, or interlock repair actions.

When there are many issues, do not read from the first row manually. Use the issue summary filter and handle red errors first.

### Red Errors

Red errors usually mean the current list clearly violates game or rule requirements. Launching has a higher chance of failing.

Common causes:

- Local files are missing or the mod failed to parse.
- Required prerequisites are missing.
- Dependencies are not enabled.
- Dependency order is wrong.
- Explicit incompatibility exists.
- Multiplayer is explicitly incompatible.

Suggested order:

1. Fix missing files and required prerequisites.
2. Enable disabled dependencies.
3. Auto sort or manually adjust order.
4. Handle explicit incompatibilities by choosing one, adding a compatibility patch, or confirming alternatives.

Do not use ignore to hide red errors. Only consider ignoring after you are very sure the current profile is not affected.

### Yellow Warnings

Yellow warnings usually mean "possibly not ideal" or "not enough information". They normally do not directly prevent game launch, but are still worth checking.

Common causes:

- Suggested prerequisites may be missing.
- Language pack target is unclear.
- Current language lacks a language pack, or the language pack's main mod is not enabled.
- Sorting advice is not fully satisfied.
- Mod supported version does not match the current game version.
- Interlock group has missing members or members are not adjacent.
- Multiplayer compatibility is poor or unknown.
- Source information is incomplete.

Suggested handling:

- Dependency or order: auto sort first, then check again.
- Language packs: if you do not need that language, you may skip it. If you need it, add or enable the language pack.
- Version: check the mod page, update state, and game version.
- Interlock: keep interlocked members adjacent, or remove invalid members.
- Multiplayer: important only if you play Multiplayer.

Warnings can be ignored, but only after you understand them. Ignoring stops the hint from bothering you. It does not fix the issue.

### Blue Info

Blue info usually explains the current list state and may need no action.

Common cases:

- A dependency is satisfied by a replacement mod.
- Compatibility information is only a reminder.

If the game works, blue info can usually stay.

### Recommended Issue Flow

1. Scan so list state is current.
2. Click the issue summary to show mods with issues.
3. Handle red errors first.
4. Auto sort, then check remaining issues.
5. Handle yellow warnings you care about.
6. Check issue count again before saving.
7. Launch and test.

Do not change too much at once. For large lists, handle one type of issue at a time.

### When It Is Okay To Ignore

Good cases:

- You read the mod description and confirmed the warning does not affect your play.
- The rule library is conservative, but your actual test works.
- The hint is about language packs or multiplayer and does not matter for your setup.

Avoid ignoring:

- Missing required prerequisites.
- Dependencies not enabled.
- Explicit incompatibility.
- Missing files.
- Errors already appear during launch or in saves.

If unsure, do not ignore. Keeping the hint helps later troubleshooting.

## Duplicate, Coexisting, And Missing Mods

### Duplicate Package IDs

When the same PackageId appears from multiple sources, RimCrow detects duplicate or coexisting states. Do not judge by name only. Different folders may be copies of the same mod.

### Coexisting Versions

Sometimes you have both local and Workshop versions. RimCrow tries to show source differences and choose a suitable copy at runtime.

If you keep multiple versions long term, write notes so you remember why.

### Missing Items

Missing items usually come from imported lists, old backups, or someone else's load order. The list contains a package ID, but the current profile cannot find the mod file.

You can subscribe, download, or remove the missing item manually.

## Save And Backup

List changes are not written to the game config automatically. Click save.

Before saving:

- Handle red errors.
- Confirm the current profile.
- Keep backups for important lists.
- If you imported an external list, check differences before loading.

For more, see [Backup, Import, and Export](./backup-import-export.md).

## FAQ

### Will Inactive Mods Be Deleted?

No. Moving a mod to inactive only removes it from the current profile's load order. It does not delete files or unsubscribe.

### Why Does The Game Not Change After Dragging?

You need to save. Dragging and auto sort only change the manager state until saved.

### Why Does One Mod Appear In Multiple Versions?

Usually there are copies in local, Workshop, or manager-library sources. Check the source, then decide whether to keep, disable, delete, or convert to local.

### Why Are There Still Issues After Auto Sort?

Auto sort depends on known rules and recognizable mod information. Missing rules, rule conflicts, or incomplete metadata still need manual judgment.
