# Quiver – Gaming Emporium list

An auto-updating [Quiver Launcher](https://github.com/tgeorgiadis/quiver-launcher) catalog list built from
[The Gaming Emporium – Decompilations & Recompilations](https://thegamingemporium.com/categories/decompilations-recompilations/).

It only includes projects that are **not** already in the official Quiver community lists.

## How it works

1. `scripts/build_list.py` reads the Gaming Emporium page and picks out every project linked to a GitHub/GitLab repo.
2. It removes anything already in the official Quiver catalog, plus mods, texture packs and launchers.
3. It writes `lists/GamingEmporiumExtras.json` in Quiver's list format.
4. A Windows scheduled task on Dan's PC runs `scripts/sync.cmd` every day, which commits and pushes the file
   if anything changed (output goes to `sync.log`). The site blocks GitHub's servers, so the GitHub Action
   is only kept as a manual fallback.

## Setup (one time)

1. Create a new **public** GitHub repo, e.g. `quiver-emporium-list`.
2. Push this folder to it.
3. Register the daily task (see *Daily sync* below).
4. In Quiver: **App Catalog → Add list** and paste:
   `https://raw.githubusercontent.com/R3ckless-Abandon/quiver-emporium-list/main/lists/GamingEmporiumExtras.json`
5. Remove the old local copy of the list from Quiver if you added one.

## Tweaking

| File | Use it to |
|---|---|
| `lists/manual.json` | Add apps by hand (same format as entries in the list) |
| `lists/exclude.json` | Never include certain repos, e.g. `["owner/repo"]` |

## Run locally

```bash
pip install -r requirements.txt
python scripts/build_list.py --dry-run          # see what would change
python scripts/build_list.py                    # write the list
python scripts/build_list.py --html saved.html  # test against a saved copy of the page
```

## Daily sync

Registered once in PowerShell (runs at 09:00, or as soon as the PC is next on if it was off):

```powershell
$a = New-ScheduledTaskAction -Execute "$PWD\scripts\sync.cmd"
$t = New-ScheduledTaskTrigger -Daily -At 9am
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "Quiver Emporium list sync" -Action $a -Trigger $t -Settings $s
```
