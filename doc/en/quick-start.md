# Quick Start

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide is for first-time RimCrow users. The goal is simple: let RimCrow find your game and mods, arrange the load order, save it, then start RimWorld.

If you only want to get through the basic flow, follow this:

```text
Scan -> Auto Sort -> Save -> Launch Game
```

## What To Do First

### 1. Check The Game Path

Select the RimWorld installation folder, not the `.exe` file, `Data`, or `RimWorldWin64_Data`.

For the Steam version, it is usually under:

```text
SteamLibrary/steamapps/common/RimWorld
```

The user data folder should be the RimWorld user data root. It usually contains:

```text
Config/
Saves/
```

For paths, profiles, Steam launch, and Workshop links, see [Profiles and Paths](./environment-and-paths.md).

### 2. Scan Mods

After confirming paths, click **Scan**. RimCrow reads local mods, Workshop mods, manager-library mods, and related metadata visible in the current profile.

A normal scan is enough for daily use. Use a deeper scan when the list looks wrong, files were changed manually, or cache data seems stale.

### 3. Arrange The Active List

The main screen usually has two main lists:

- Inactive list: mods you have but do not load in the current profile.
- Active list: the actual order RimWorld reads.

Common actions:

- Double-click a mod to move it between the Active list and Inactive list.
- Drag a mod to adjust order or move it to another list.
- Select multiple mods with `Ctrl+Click`, `Shift+Click`, `Ctrl+A`, or drag selection from the index column.
- Use the right-click menu for actions such as opening folders, editing info, or handling sources.

Red and yellow hints usually mean dependency, order, compatibility, or missing-file issues. Handle red errors before launching the game.

For list details, see [Mod List and Load Order](./mod-list-and-load-order.md).

### 4. Auto Sort

Click **Auto Sort** to let RimCrow reorder the active list using native mod dependencies, community rules, user rules, dynamic rules, and other known information.

Auto sort is not a magic "perfect order" button. It gives you a reasonable base order. After sorting, still check issue hints and order differences before deciding whether to adjust by hand.

For auto sorting and rules, see [Auto Sort and Rules](./auto-sort-and-rules.md).

### 5. Save The Load Order

Changes made by dragging, enabling, moving to Inactive, or auto sorting only affect RimCrow until you save.

Before saving:

- Check for red errors.
- Confirm you are editing the right profile.
- Keep a backup for important lists.

### 6. Launch The Game

Launch the game after saving. RimCrow starts RimWorld with the current profile settings and syncs required manager links first when needed.

If link sync fails before launch, RimCrow will not continue. Check paths, permissions, and `_Link_...` link status first.

## Recommended Daily Flows

### After Installing New Mods

1. Scan.
2. Move the mods you want to the active list.
3. Auto sort.
4. Handle missing dependencies, order errors, and compatibility hints.
5. Save.
6. Launch the game and test.

### After Updating Or Removing Mods

1. Scan.
2. Check missing, removed, duplicate, or coexisting-mod hints.
3. Auto sort again if needed.
4. Save.
5. Launch the game.

### After Importing Someone Else's List

1. Import the file or share code from the backup page.
2. Check differences and missing items first.
3. Subscribe, download, or manually handle missing items.
4. Load it into the current profile only after the list looks reasonable.
5. Save and launch.

For backups and import/export, see [Backup, Import, and Export](./backup-import-export.md).

## FAQ

### Workshop Mods Do Not Appear After Scanning

Check whether the Workshop folder is correct. It is usually:

```text
steamapps/workshop/content/294100
```

If you use Steam launch, Steam mainly handles Workshop content. If you do not launch through Steam but still want to read an existing Workshop folder, enable **Use Workshop mods**.

### Warnings Remain After Sorting

This is common. Auto sort can only use known rules and recognizable mod metadata. Red errors should be handled first. Yellow warnings can be checked against mod descriptions, rule sources, and your actual setup.

### Nothing Changes In Game After Saving

Check that:

- You saved the current profile.
- The game is not still running an old instance.
- RimWorld is reading the same user data folder as the current profile.
- You did not manually add a wrong `-savedatafolder` launch argument.

### Not Sure What To Click Next

Follow the main flow: scan, auto sort, save, launch. When problems appear, start from the issue summary, then inspect the specific mod hints.

## Notes

- Do not try too many advanced features at once when organizing a large list for the first time.
- Keep a backup before saving important changes.
- Do not delete the database or user data folder to "fix" problems.
- Logs, paths, and exported packages may contain local paths and mod lists. Check them before sharing.
