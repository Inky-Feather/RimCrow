# Profiles And Paths

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains RimCrow profiles, common paths, Workshop mod access, manager-library mod access, launch methods, and profile shortcuts. You do not need to understand the internal implementation. Focus on what each path should point to and when each switch should be enabled.

## Choose By How You Play

### Normal Steam Use

Use this if you want Steam to handle Workshop subscription, updates, and loading.

- Game folder: select the Steam-installed RimWorld folder.
- Steam path: keep auto detection unless it fails.
- Prefer Steam launch: on.
- Use Workshop mods: off.
- Use manager mods: enable only when you need mods from RimCrow's manager library.

This is closest to normal RimWorld and Steam behavior.

### Multiple Saves Or Separate Setups

Use profiles when testing different mod lists, game versions, or mod packs.

- Multiple profiles can share the same game folder.
- Each profile should use its own user data folder.
- If you want to inherit the current setup, copy `Config` and `Saves` when creating the new profile.
- Do not manually add `-savedatafolder`. RimCrow handles it.

Profile isolation mainly separates saves, settings, load order, and logs. It does not copy the game installation automatically.

### Not Launching Through Steam, But Using Existing Workshop Files

Use this when you already have a Steam Workshop folder on this machine, but do not want this profile launched by Steam.

- Workshop folder: set it to `steamapps/workshop/content/294100`.
- Prefer Steam launch: off.
- Use Workshop mods: on.
- Launch through RimCrow so it can sync links before starting the game.

This only reads existing local Workshop files. It does not connect a non-Steam game to Steam Workshop services.

### SteamCMD Downloads Into The Manager Library

Use this when you want RimCrow to download Workshop mods into its manager mod folder without relying on the Steam client subscription list.

- SteamCMD folder: use a path without Chinese characters, such as `D:/Tools/steamcmd`.
- Manager download mod path: use an NTFS disk when possible.
- Do not set the manager download path to the official Steam Workshop folder.
- After download, enable **Use manager mods**, then scan and launch.

SteamCMD downloads and Steam client subscriptions are different sources. Updates and removal are also handled differently.

## Path Relationship

RimWorld mainly reads two places:

```text
Game folder/
  RimWorldWin64.exe
  Mods/

User data folder/
  Config/
    ModsConfig.xml
  Saves/
```

RimCrow mainly does this:

- Select which game folder the current profile uses.
- Select which user data folder the current profile uses.
- Before launch, link manager mods or Workshop mods into `Mods` when needed.
- Start the game with the current profile's launch arguments.

When troubleshooting path problems, first decide whether the path is for the game program, user data, or mod file source.

## What A Profile Saves

A profile is a RimWorld runtime setup. It mainly contains:

- Game folder: where the RimWorld program is.
- User data folder: saves, settings, load order, logs, and related files.
- Launch arguments: extra arguments passed to RimWorld.
- Runtime switches: Prefer Steam launch, Use Workshop mods, and Use manager mods.

The default profile usually points to the system's normal RimWorld user data folder. If a new profile has no custom user data path, RimCrow places it under:

```text
data/profiles/<profile-id>
```

`Config` and `Saves` are created when saving or activating the profile.

## Global Paths And Profile Paths

Some settings belong to the current profile. Others are shared by all profiles.

### Current Profile

- Game folder
- User data folder
- Local mods folder
- Launch arguments
- Prefer Steam launch
- Use Workshop mods
- Use manager mods

### Shared By All Profiles

- Steam path
- SteamCMD folder
- Workshop folder
- Manager download mod path
- Tool mod folder

Switching profiles changes the game folder, user data folder, and runtime switches. It does not create separate SteamCMD or Workshop folders for every profile.

## Key Paths

### Game Folder

Select the RimWorld installation root. Do not select the executable itself, `Data`, or `RimWorldWin64_Data`.

Common executables:

- Windows: `RimWorldWin64.exe` or `RimWorldWin.exe`
- Linux: `RimWorldLinux` or `RimWorldLinux.x86_64`
- macOS: `RimWorldMac.app`

Steam RimWorld is usually under:

```text
SteamLibrary/steamapps/common/RimWorld
```

Steam, copied old Steam versions, GOG, Epic, and official-site versions can all be used as game folders. The main difference is launch method and Workshop access.

### User Data Folder

Select the RimWorld user data root. Do not select `Config`, `Saves`, or `Config/ModsConfig.xml`.

Correct structure:

```text
User data folder/
  Config/
    ModsConfig.xml
  Saves/
```

Common default locations:

- Windows: `%USERPROFILE%/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios`
- macOS: `~/Library/Application Support/RimWorld`
- Linux: `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios`

If the folder does not exist yet, RimCrow can create it when saving or activating the profile, as long as the parent folder exists and is writable.

### Local Mods Folder

The local mods folder is determined by the game folder:

```text
RimWorld/Mods
```

You do not need to fill it separately. Profiles sharing the same game folder also share the same local `Mods` folder.

### Workshop Folder

Set this to the Steam folder where RimWorld Workshop mods are downloaded. RimWorld's Steam AppID is `294100`:

```text
SteamLibrary/steamapps/workshop/content/294100
```

This folder is managed by Steam. Subscription, updates, and removal are still Steam's job. RimCrow does not automatically update or edit files inside it. Do not use it as the manager download library.

If `294100` does not exist, subscribe to or download a RimWorld Workshop item in Steam first.

### Manager Download Mod Path

This folder stores mods downloaded and managed by RimCrow through SteamCMD, Git, or direct links. By default it is under RimCrow's `mods` folder, but you can move it elsewhere.

Do not set it to the official Steam Workshop folder. If Steam and RimCrow both think they manage the same files, troubleshooting becomes harder.

If you set it to the game's `Mods` folder, disable **Use manager mods** to avoid duplicate links.

### Steam Path

The Steam path is used for Steam launch, subscriptions, and Workshop status. RimCrow can usually detect it automatically. If detection fails, select the Steam installation folder.

If this path is invalid, Steam launch and Steam Workshop features may be unavailable. Direct game launch can still work.

### SteamCMD Folder

Select the folder containing `steamcmd.exe` or `steamcmd.sh`.

Notes:

- Avoid Chinese characters in the path.
- On Windows, prefer an NTFS disk.
- SteamCMD downloads into its own standard structure:

```text
SteamCMD folder/steamapps/workshop/content/294100
```

RimCrow tries to connect this download structure with the manager download mod path, so SteamCMD can keep its official layout while the manager can see downloaded mods.

### Tool Mod Folder

The tool mod folder stores RimCrow-provided or helper mods. Normal users usually do not need to change it. They are scanned and linked only when the related tool mod switch is enabled.

## Auto Detection

RimCrow does not blindly scan the whole disk. It first checks stable locations:

- Steam install information.
- Steam `libraryfolders.vdf`.
- RimWorld `appmanifest_294100.acf`.
- Common platform install paths.
- Common platform user data paths.

This is faster and avoids unrelated folders. If you moved Steam libraries, copied the game manually, or deleted Steam configuration files, auto detection may be incomplete. Select paths manually when needed.

After a manually selected path passes validation, RimCrow uses that path for later actions.

## How Mods Enter The Game

RimWorld naturally reads `Mods` under the game folder, and Steam Workshop content when launched through Steam. RimCrow decides whether to deploy links before launch based on your switches.

### Local Mods

Mods under `RimWorld/Mods` are read directly by the game. RimCrow does not need extra links for them.

### Steam Workshop Mods

There are two ways:

| Method | Best For | Main Switch |
| --- | --- | --- |
| Steam launch | Steam users who want Steam to handle Workshop mods | Prefer Steam launch on |
| Link mounting | Not launching through Steam, but reading existing Workshop files | Prefer Steam launch off, Use Workshop mods on |

Do not use both at the same time. When Steam launch is enabled, RimCrow disables Workshop link mounting to avoid duplicate handling.

### Manager Mods

Mods in the manager download path are not read by RimWorld automatically. When **Use manager mods** is enabled, RimCrow links needed manager mods into the current game folder's `Mods` directory before launch.

The game then sees:

- Real local mods inside `Mods`.
- `_Link_...` links created by RimCrow.

### Duplicate Mods

If multiple sources contain the same PackageId, RimCrow chooses the higher-priority copy to avoid loading the same mod from several places.

Approximate priority:

```text
DLC / official content > local Mods > manager mods > Steam Workshop mods > tool mods
```

## Link Deployment Mode

Link deployment only manages links with the `_Link_` prefix. It does not delete normal local mod folders.

### Incremental Deployment

Recommended default. RimCrow keeps correct existing links, removes invalid or unneeded links, then creates missing ones.

### Full Rebuild

RimCrow deletes all old `_Link_` links first, then recreates links for the current profile.

Most users should keep incremental deployment. Use full rebuild only when `_Link_` folders were manually changed, profile switching left suspicious links, or link status is clearly wrong.

## Launch Methods

### Direct Game Launch

RimCrow runs the RimWorld executable and passes the current profile's launch arguments.

Common arguments:

- `-popupwindow`: borderless window mode
- `-quicktest`: quick test

Best for:

- Non-Steam versions.
- Users who do not want Steam launch.
- Profiles using links for manager mods or existing Workshop files.
- Testing different user data profiles.

If links need syncing, RimCrow does it before launch. If sync fails, launch stops to avoid entering the game with the wrong mod state.

### Steam Client Launch

RimCrow starts RimWorld through Steam, usually like:

```text
steam.exe -applaunch 294100 ...arguments
```

This can carry profile launch arguments, so it works for profiles that need `-savedatafolder`.

### Steam URL Launch

Steam URL looks like:

```text
steam://run/294100
```

It is simple and can work even without setting the Steam path, but it cannot carry extra launch arguments. Use it only when the current profile has no launch arguments.

### Launch Choice For Different Game Sources

For RimWorld in the current main Steam install folder, Steam launch is usually best. Steam handles official Workshop content, while RimCrow handles profile paths and launch arguments.

Some profiles use a game folder that is not the current main Steam install, such as a copied old Steam version, backup version, or mod-pack folder. If your Steam account owns RimWorld and Steam can take over that executable, you can try launching it through Steam. This may let that profile run through Steam and use official Workshop content. Stability depends on the game files, Steam client, and account state.

GOG, Epic, and official-site versions can be launched directly as separate profiles. They normally cannot use the official Steam Workshop service directly. If you already have a local Steam Workshop folder, you can turn off Steam launch and enable **Use Workshop mods** so RimCrow links existing Workshop files into local `Mods`.

## Profile Shortcuts

Profile shortcuts reuse the current profile's launch method and launch arguments. You do not need to write commands by hand.

### Direct Game Shortcut

This shortcut points to the RimWorld executable and includes current profile arguments.

Best for:

- Non-Steam profiles or profiles not launched through Steam.
- Profiles using links for manager mods or existing Workshop files.
- Test profiles that must start a specific game folder.

It does not let Steam take over launch or automatically handle official Workshop subscriptions.

### Steam Official AppID Shortcut

This shortcut points to Steam and uses `-applaunch 294100`.

Best for profiles based on the current main Steam RimWorld install. It can carry current profile arguments and let Steam handle Workshop content officially.

If the Steam path is invalid, RimCrow falls back to a direct game shortcut and shows a hint.

### Steam Local Library Shortcut

This is for Steam game folders outside the current main Steam install, such as copied old versions, backups, or mod-pack game folders.

On Windows, RimCrow can add that executable as a non-Steam game in Steam's local library, then create a desktop shortcut. The flow is roughly:

1. Fully exit Steam first, so its config is not overwritten.
2. RimCrow writes or updates Steam's `shortcuts.vdf`.
3. Steam restarts.
4. Steam generates a stable `steam://rungameid/...`.
5. RimCrow creates a desktop URL shortcut.

Difference from the official AppID shortcut: the official AppID launches the RimWorld managed by Steam. The local library shortcut launches the exact RimWorld executable you selected.

Possible shortcut types:

- Windows normal launch: `.lnk`
- Windows Steam URL: `.url`
- Linux: `.desktop`
- macOS: `.command`

Depending on the profile, the shortcut may point to:

- The game executable.
- Steam with `-applaunch 294100`.
- A Steam URL such as `steam://rungameid/...`.

If multiple profiles share the same game folder, shortcuts can only guarantee the launch target and arguments. Links inside `Mods` still depend on the most recent RimCrow launch or sync for that game folder.

## FAQ

### Auto Detection Cannot Find The Game

Make sure Steam or the system can actually find RimWorld. If detection still fails, manually select the RimWorld installation root. Do not select the executable, `Data`, or `RimWorldWin64_Data`.

### Workshop Path Validation Fails

Check that the path is `steamapps/workshop/content/294100`. If `294100` does not exist, subscribe to or download one RimWorld Workshop item in Steam first.

### SteamCMD Path Cannot Contain Chinese Characters

Move SteamCMD to an English-only path, such as `D:/Tools/steamcmd`. Chinese paths can cause SteamCMD download or update failures.

### `_Link_...` Appeared In Local Mods

These are runtime links created by RimCrow so the game can read manager mods, tool mods, or linked Workshop mods. They are not full copied mods. Normally do not rename or move them manually.

### Link Sync Fails Before Launch

Check:

- The game folder's `Mods` directory exists and is writable.
- The manager mod folder or Workshop folder still exists.
- The current disk supports directory links.
- Antivirus or file managers are not locking `_Link_` folders.
- RimCrow-created links were not manually deleted or renamed.

If needed, switch link deployment to full rebuild, then scan and launch again.

### Steam Launch Or Workshop Link Mounting?

If Steam can launch the game and load subscribed Workshop mods normally, prefer Steam launch. Enable Workshop link mounting only when you are not launching through Steam but need to read files from a local Workshop folder.

## Important Notes

- Profile isolation mainly separates user data. It does not copy the game installation.
- Profiles sharing one game folder also share the same local `Mods` folder.
- Do not manually add `-savedatafolder`. Multi-profile handling does this for you.
- Link deployment only manages `_Link_` links. It does not delete normal local mod folders.
- The official Steam Workshop folder is managed by Steam. Do not use it as the manager download library.
- SteamCMD download folders and manager mod paths may be connected through junctions or links. Seeing a junction is normal.
- Paths closer to standard Steam and RimWorld layouts are easier to detect. Moved Steam libraries, portable Steam, and compatibility-layer paths may need manual setup.
