# CLAUDE.md – handover notes

## What this is
Dan wants an auto-updating Quiver Launcher catalog list built from The Gaming Emporium's
decomp/recomp page, so new projects appear in Quiver when he clicks "Refresh lists".
Dan prefers work broken into small steps.

## Current state
- `lists/GamingEmporiumExtras.json` – a hand-built seed list (202 apps), already working as a local list in Quiver.
- `scripts/build_list.py` – scraper. **Only tested against a made-up HTML sample**, never the live site
  (the previous sandbox was blocked from reaching thegamingemporium.com).
- `.github/workflows/update-list.yml` – daily GitHub Action that runs the script and commits changes.

## Live site findings (2026-10-06)
- Static HTML (not WordPress; `/wp-json/` 404s). All 487 cards are on one page – no pagination
  (`/page/2/` 404s); the old 87k cut-off was the fetch tool, not the site.
- Card markup: `<div class="game-card" data-title=".." data-platform="..">` containing the Platform
  label, then one `<a class="game-card__link" href="..">`. Platform belongs to the same card.
  `scrape()` now reads these attributes directly; `find_card()`/`parse_platform()` were removed.
- 434 distinct GitHub/GitLab repos on the page; all 202 seed-list repos are among them.

## First jobs
Jobs 1–4 done (see above). 2026-10-06: list written as v1.0.2, 262 apps (+60, none lost). Mods are tagged `mod` (title contains the word "mod" or "expansion") and `mod` is a preferred filter. Next: job 5.
1. Fetch the live page and check the real HTML structure. Each card has a title link to the repo,
   a category link ("Decompilations & Recompilations<genre>") to the same repo, and a "Platform<name>" label.
   Note: in copied text the "Platform" label appears *before* the card it belongs to – confirm which card
   it actually belongs to in the HTML before trusting `find_card()`.
2. Fix `find_card()` / `parse_platform()` selectors to match the real markup.
3. Check for pagination or lazy-loading (an earlier fetch seemed to cut off around 87k characters of text).
   A WordPress REST endpoint (`/wp-json/wp/v2/...`) may give cleaner data if the site is WordPress.
4. Run `python scripts/build_list.py --dry-run` and compare against the seed list – the result should be
   at least as large. If the live scrape loses entries, merge rather than replace.
5. Help Dan create the GitHub repo, push, and run the workflow once by hand.

## Quiver list format (from the official catalog)
Top-level: `name`, `description`, `version`, `iconUrl`, `preferredTagFilters`, `hiddenTagFilters`, `apps`.
Each app: `name`, `repository` (`owner/repo`), `folderName`, `appIconUrl` (may be null), `tags`,
optional `project`, `repositorySource` (`"gitlab"` for GitLab), `filesToAdd`.
Official index: https://raw.githubusercontent.com/tgeorgiadis/quiver-community-app-catalog/main/index.json
(entries use `remoteLocation`).

## Nice-to-haves
- Skip repos with no GitHub releases (Quiver can't install them). Use the GitHub API with `GITHUB_TOKEN` in the Action.
- Icons: pull from SteamGridDB the way the official lists do.
- Split into per-platform lists if one big list gets unwieldy.
