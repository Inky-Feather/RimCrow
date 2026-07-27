# Workshop And Download Sources

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains common ways to get mods in RimCrow: Steam subscriptions, SteamCMD downloads, collection import, Git repository subscriptions, and zip direct links.

First remember the difference:

- Steam subscription: managed by the Steam client, for Steam Workshop mods.
- SteamCMD download: downloads Workshop mods into RimCrow's manager mod library, without relying on the Steam client subscription list.
- Git / direct link: for mods published outside the Workshop, usually from repositories or packaged downloads.

## Choose By Scenario

### You Want Steam To Manage Updates

Use Steam subscriptions.

Best for:

- Steam owners of RimWorld.
- Users who want Steam to update Workshop mods automatically.
- Users who do not want to manage download folders manually.

Suggested settings:

- Prefer Steam launch: on.
- Use Workshop mods: off.
- Let Steam handle Workshop subscription, update, and removal.

This is closest to normal RimWorld and Steam behavior.

### You Want Manual Control Over Updates

Use SteamCMD to download mods into the RimCrow manager mod folder.

Best for:

- Users who want to control when Workshop mod files change.
- Users who do not want to depend on the current Steam subscription list.
- Users who want Workshop, Git, and direct-link mods managed together.

After download, enable **Use manager mods** so the game can read these mods through links.

### Workshop Collections

Import a collection URL or Workshop ID from the collection subscription page.

Best for:

- Someone gives you a Steam collection link or ID.
- You want to see what a collection contains.
- You want to check whether collection contents changed.
- You want to fill missing items before applying an order.

### Mods Published Only In Git Repositories

Use Git repository subscriptions.

Best for:

- Mods not uploaded to the Workshop.
- Authors publishing on GitHub, GitLab, or GitGud.
- Authors publishing packaged versions through Releases.

## Inventory Hub

Click **Inventory Hub** to enter the workspace. Main pages include:

- Full Library Data: view Workshop, local, and manager-library inventory.
- Workshop Search: search Workshop items and view details, dependencies, screenshots, and author info.
- Collection Subscription: import Steam collections and check item status.
- Git Repository Subscription: add Git or direct-link sources and view deployment records.

## Steam Subscriptions

Steam subscription adds Workshop items to your Steam subscription list. Download, update, and removal are mainly handled by the Steam client.

Best for:

- Normal Steam RimWorld users.
- Users who want automatic Workshop updates.
- Users who want official behavior.

Notes:

- Steam must be logged in and able to access the Workshop.
- After subscription, Steam may not download the item immediately.
- Unsubscribing does not always remove local files immediately. It depends on Steam cleanup.

## SteamCMD Downloads

SteamCMD is a standalone download tool. RimCrow can use it to download Workshop items into the manager mod library.

Best for:

- Keeping independent mod files.
- Letting the manager library store downloaded content.
- Downloading without using the Steam client subscription list.

Notes:

- Do not put SteamCMD under a path containing Chinese characters.
- On Windows, use an NTFS disk when possible.
- SteamCMD download is usually not the same as Steam client subscription.
- Scan after downloading so the list updates.
- Enable **Use manager mods** before using these mods in the game.

For SteamCMD paths and manager mod paths, see [Profiles and Paths](./environment-and-paths.md).

## Workshop Search

Workshop search can use mod names, package IDs, or Workshop IDs.

Results usually show:

- Mod name and Workshop ID.
- Package ID, author, and version info.
- Subscription status.
- Description, dependencies, screenshots, and related items.

Common actions:

- Subscribe through Steam.
- Unsubscribe.
- Download to the manager library.
- Open the Workshop web page.
- View dependencies, same-author items, or related items.

Enhanced mode can fetch more complete Workshop information. When it is off, RimCrow relies more on local cache and public interfaces, so results may be incomplete.

## Collection Subscription

The collection page is for Steam Workshop collections shared by others.

Recommended flow:

1. Paste a collection URL or enter a collection ID.
2. Select the imported collection record.
3. Check which mods it contains.
4. Check subscribed, installed, and missing states.
5. Subscribe or download missing items in bulk.
6. Apply the collection order only after checking differences and missing items.

Do not overwrite the current active list immediately after import.

## Git Repository Subscriptions

Git repository subscriptions are for mods not uploaded to the Workshop, or mods mainly published on code hosting platforms.

Common public hosts:

- GitHub
- GitLab
- GitGud

Some zip direct links are also supported.

### Source Mode

Source mode fetches branch contents.

Best for:

- Repositories without Releases.
- Users following test builds or latest commits.
- Repositories whose structure is already a usable mod.

Risks:

- Source branches may be unstable.
- Some repositories require a build step before they become usable mods.

### Release Mode

Release mode fetches packaged versions published by the author.

Best for:

- Repositories with formal Releases.
- Users who want a more stable version.
- Users who do not want to handle source folder structure.

If the repository has no Release, this mode is not available.

### Zip Direct Links

Zip direct links are useful for packaged files in recommendation lists or third-party sources.

Notes:

- Zip sources depend on link stability.
- If the link expires, you need another source.
- After download, scan and confirm the mod structure is correct.

## Update Checks

RimCrow can display state changes for Workshop, SteamCMD, and Git sources, but different sources use different update signals.

Common states:

- Installed: local files were found.
- Subscribed: the item exists in the Steam subscription list.
- Changed: obvious local file changes were detected.
- Update available: remote data or records suggest a newer version may exist.
- Removed: files may be missing or removed by the game or another tool.
- Missing: the record exists, but no valid local mod file was found.

When states look inconsistent, scan again first. Then check whether the source is still reachable and handle it with resubscribe, redownload, or another action.

## Recommended Usage

### Normal Steam Players

- Use Steam subscriptions for Workshop mods.
- Launch the game through Steam.
- Do not use the Steam Workshop folder as the manager library.

### Mod Pack Users

- Import shared collections from the collection page.
- Use backups and import/export for load orders.
- Use SteamCMD or Git subscriptions for non-Steam sources.
- Keep backups before large changes.

### Testing New Mods

- Download into the manager library or a separate profile.
- Scan, then enable only a small related set.
- Auto sort and save.
- Test in game before merging into your normal profile.

## FAQ

### I Subscribed But The Mod Is Not In The List

Steam may not have finished downloading. Wait until Steam downloads it, then scan again.

### SteamCMD Downloaded The Mod But The Game Does Not Load It

Check whether the current profile has **Use manager mods** enabled, and whether link sync succeeded before launch.

### A Git Subscription Does Not Work

First check whether files were downloaded successfully. Network failures may leave incomplete files. The repository may also contain source code that is not directly usable, or it may require the Release package. Check the repository README and file structure.

### A Workshop Item Looks Invalid

The item may be removed, hidden, region-blocked, or stale in local cache. Refresh, scan again, then try opening the Workshop page.

## Notes

- Do not mix the official Steam Workshop folder with the manager download folder.
- Subscription, download, and deployment are different actions.
- Scan after updates so the list does not use stale state.
- Before deleting or unsubscribing, check the source to avoid removing the wrong copy.
