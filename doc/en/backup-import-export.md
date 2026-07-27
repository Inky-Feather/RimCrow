# Backup, Import, And Export

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains load order backups, external list import/export, share codes, RimCrow data packages, and mod file packages.

First separate two things:

- Load order: which mods are enabled in the current profile, and in what order.
- Data or files: RimCrow settings, rules, profile data, or real mod files.

## Load Order Backups

A load order backup saves the active list and its order for the current profile. It is not a full backup of mod files.

Common uses:

- Keep a rollback point before large sorting changes.
- Compare before and after auto sort.
- Test different mod combinations.
- Restore an old order from another profile.

The backup page may show:

- Temporary imports: lists just imported from external files or share codes.
- Latest backups: recent related backups.
- Today's changes: backups created today.
- History: older backups.
- Manual backups: backups you saved or organized yourself.

## Import Load Orders

Import reads an external list and opens it in the comparison view. Do not overwrite your current list immediately. Check differences and missing items first.

Common supported formats include:

- `ModsConfig.xml`
- `ModList.xml`
- `.rml`
- RimPy XML
- RimSort JSON
- Plain text lists
- Workshop ID lists
- RimWorld save files, `.rws`
- RimCrow share codes

After import, you may see:

- Mods already available in the current profile.
- Mods missing from the current profile.
- Items with only a package ID and no known source yet.
- Items with Workshop IDs that can be subscribed to or downloaded.

## Export Load Orders

Export saves the current active list as an external file for sharing or migration.

| Format | Best For |
| --- | --- |
| `ModsConfig.xml` | RimWorld or other tools, package order only |
| `ModList.xml` | Sharing lists with Workshop ID information |
| `RML` | RimWorld-like list format for some external workflows |
| Share code | Quick copy and import |

If you want others to fill missing mods more easily, use a format that includes Workshop IDs or source information.

## Before Loading A Backup

Loading a backup replaces the current active list with the backup state. Unsaved changes will be lost.

Check before loading:

- Which profile the backup came from.
- Whether there are missing items.
- Whether it matches the current game version.
- Whether it will overwrite manual changes you have not saved yet.

If you only want to inspect differences, select the backup and view it first. Do not load it immediately.

## View Backups Across Profiles

The backup page can display backups from other profiles. This is useful when checking an old setup or test profile.

Notes:

- Viewing another profile's backup does not switch the current profile.
- Before loading it into the current profile, check missing items and path differences.
- Different profiles may use different game versions and user data folders.

## Share Codes

Share codes are useful for quickly sending an enabled load order to someone else.

They are good for:

- Temporary list sharing.
- Letting someone import and check missing items.
- Avoiding file transfer.

Notes:

- Share codes do not contain real mod files.
- The other person still needs access to the corresponding mod sources.
- More complete source information makes missing items easier to fill.

## Recommendation List Export

Recommendation list export creates readable material for sharing a mod pack.

Common formats:

- Text: simple copy and paste.
- Markdown: forums, repositories, and docs.
- DOCX / PDF: formal sharing.
- Image: social sharing.
- GIF: showing list or load order effects.

A recommendation list is for display and explanation. It is not a full data backup.

## RimCrow Data Import And Export

RimCrow data packages are for moving RimCrow's own data.

Common contents:

- Settings.
- Rules.
- Prompts.
- Profile data.
- Other manager configuration.

Useful for:

- Moving to another computer.
- Reinstalling the app.
- Backing up your configuration.
- Syncing manager settings between machines.

Keep a current data backup before importing, so you can roll back if something is overwritten.

## Mod File Packages

Mod file packages include real mod files, so they are heavier than load order exports.

Useful for:

- Moving local mods to another machine.
- Preserving mods without stable download sources.
- Saving the current file state of a mod pack.

Before exporting:

- File size may be large.
- Steam Workshop mods are managed by Steam, and copied files may not update the same way later.
- Check disk space.
- During import, handle paths, conflicts, and overwrite risks.

If you only want to share a list, do not use a mod file package. Use a recommendation list, share code, or load order export instead.

## Recommended Flows

### Before Large Sorting Changes

1. Save the current list.
2. Create a manual backup.
3. Auto sort or batch edit.
4. Compare differences.
5. Save after confirming the result.

### Importing Someone Else's List

1. Import the file or share code.
2. View differences.
3. Check missing items.
4. Subscribe or download missing mods.
5. Decide whether to load it into the current profile.
6. Save.

### Moving To Another Computer

1. Export a RimCrow data package.
2. Export a mod file package only if you need real mod files.
3. On the new computer, configure game and user data paths first.
4. Import data.
5. Scan.
6. Check missing items and path issues.

## FAQ

### Do Backups Save Mod Files?

Normal load order backups do not save real mod files. They mainly save the enabled order and related list information.

### Why Are Items Missing After Import?

The imported file contains package IDs that the current profile cannot find. Subscribe, download, or remove those missing items manually.

### What Is The Difference Between `ModsConfig.xml` And A Recommendation List?

`ModsConfig.xml` is mainly for the game or tools to read. A recommendation list is mainly for people to read and share.

### Data Package Or Mod Pack?

Use a data package for RimCrow settings, rules, and profile data. Use a mod file package only when you need to include real mod files.

## Notes

- Loading a backup overwrites the current active list.
- Check differences after importing external lists.
- Share codes and list files are not mod files.
- Check disk space and source permissions before exporting file packages.
- If data looks wrong, keep existing folders and backups. Do not delete the database first.
