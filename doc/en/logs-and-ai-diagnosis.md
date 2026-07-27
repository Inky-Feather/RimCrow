# Logs And AI Diagnosis

> **Translation notice:** This English document was generated with AI assistance from the Chinese source doc. Some descriptions may be inaccurate or not fully aligned with the current UI. Corrections and improvement suggestions are welcome.

This guide explains how RimCrow helps you read game logs, locate errors, and use AI for troubleshooting. It is useful when you see red errors, launch failures, broken saves, stuck loading, or you are not sure which mod caused a problem.

Remember: AI diagnosis is an assistant, not an automatic fix. Before changing your list, still check logs, mod sources, and load order.

## When To Check Logs

Check game logs first when:

- The game fails to launch.
- Loading gets stuck.
- Many red errors appear after entering a save.
- A game UI or feature cannot open.
- Errors repeat during saving, map generation, combat, or events.
- Problems start after adding new mods.

If RimCrow itself reports an error, switch to system logs.

## What The Log Center Shows

The log center mainly has two sources:

- Game logs: RimWorld runtime logs, useful for mod and game errors.
- System logs: RimCrow runtime logs, useful for app operations, paths, downloads, and API issues.

Most players should check game logs first.

## Basic Troubleshooting Flow

### 1. Reproduce The Problem

Try to identify when the problem happens:

- During startup.
- When loading a save.
- After entering the map.
- After clicking a button.
- After a specific event.

Open logs after reproducing. Recent logs are easier to connect to the real problem.

### 2. Find Key Errors

Look for:

- `Error`
- `Exception`
- `Could not load`
- `Failed`
- `PatchOperation`
- The same repeated error block.

Do not only read the last line. The real cause may be near the first red block or the start of repeated errors.

### 3. Match Mod Names And Package IDs

Logs may mention:

- Mod names.
- Package IDs.
- DLL names.
- XML paths.
- Texture or Def paths.

Search these keywords in the main mod list to find suspicious mods.

### 4. Test After Changes

Possible fixes include:

- Add missing dependencies.
- Adjust load order.
- Disable suspicious mods.
- Update or roll back mods.
- Add compatibility patches.
- Clean leftover config.

Change only a few things at a time, so you can tell what worked.

## One-Click Analysis

One-click analysis is useful when logs are long, errors are noisy, and you do not know where to start.

It first compresses and groups global errors, then sends them to AI for analysis.

Good for:

- Too many red errors.
- Repeated errors flooding the log.
- Unclear most important error.
- Needing a priority list.

Results usually include:

- Most suspicious error source.
- Possibly related mods.
- Suggested handling order.
- Information that still needs confirmation.

## Manual Log Selection For AI

If you already know which log block matters, select those log lines manually and open the AI assistant.

Good for:

- Analyzing one specific error block.
- Asking follow-up questions around one mod.
- Reducing unrelated log noise.

After selecting logs, RimCrow estimates token usage. If it approaches the model limit, select a smaller range or use one-click analysis.

## How To Ask AI More Effectively

Avoid asking only "how do I fix this". Better questions:

- "List the top 3 suspicious mods by priority."
- "Decide whether this looks like a missing dependency, order issue, or compatibility conflict."
- "Give me a minimal test plan."
- "Which errors can I ignore for now, and which must be handled first?"
- "If I use binary search, which mods should I disable in the first round?"

The more specific the question, the easier the answer is to apply.

## Tool Permissions

The AI sidebar may allow access to log context, mod metadata, sorting rules, and other information.

For complex problems, keep the default permissions enabled. A single log block is often not enough. AI needs the current list, rules, and mod info to judge better.

If you only want AI to read selected log text, reduce tool permissions.

## Helper Tool Mods

The log center has a **Use Helper Tool Mods** switch. When enabled, RimCrow can automatically enable helper tool mods during save or auto sort to provide more detailed game log information.

Most users can keep the default. Disable it only when you explicitly do not want any helper mod added.

## File Content Search

File content search is useful for finding:

- Which mod defines a Def name.
- XML paths mentioned in logs.
- Keywords appearing in mod files.
- Patches or translation files that may cause a problem.

Search results help turn technical log terms into concrete mod files.

## Common Scenarios

### Startup Errors

Check first:

- Missing prerequisites.
- Wrong load order.
- DLL or version incompatibility.
- Game version and mod version mismatch.

### Errors After Entering A Save

Check first:

- Whether items, factions, buildings, or creatures already in the save came from removed mods.
- Whether a large mod was recently removed.
- Whether a mod update changed save structure.

### Many PatchOperation Errors

These usually relate to XML patches. Possible causes:

- The patch target no longer exists.
- A prerequisite mod is not enabled.
- A mod update changed the path.
- The patch mod is in the wrong order.

### Texture Or Resource Load Failure

Check first:

- Whether the file is missing.
- Whether the mod downloaded completely.
- Path case or special characters.
- Whether texture optimization or cleanup was just performed.

For texture optimization, see [Texture Optimization](./texture-optimization.md).

## Privacy And Safety

Logs and AI requests may contain:

- Local paths.
- Usernames.
- Mod lists.
- Save names.
- Some settings or error context.

Before sharing logs or sending them to AI, check whether they contain anything you do not want to disclose.

Save AI API keys, proxy usernames, and other sensitive fields through settings. Do not write them into logs or chat messages.

## FAQ

### Is AI Always Correct About Suspicious Mods?

No. AI infers from logs and context. Treat it as a troubleshooting priority suggestion, not a final verdict.

### The Log Is Too Long To Send

Use one-click analysis, or select only the most relevant error blocks. Do not send the whole log blindly.

### Should I Read System Logs Or Game Logs?

Use game logs for RimWorld red errors, broken saves, and mod errors. Use system logs for RimCrow operation failures, download failures, and path failures.

### How Do I Confirm A Fix?

Scan again, save, launch the game, and reproduce the same action. Confirm that the original key error no longer appears before adding more mods back or making more changes.

## Notes

- Change only a few things at a time.
- Do not delete many mods based on one log line.
- Combine AI diagnosis with mod descriptions and actual tests.
- Check local paths and personal information before sharing logs.
- Back up first when data looks abnormal. Do not delete the user data folder first.
