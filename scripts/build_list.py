#!/usr/bin/env python3
"""
Build a Quiver Launcher catalog list from The Gaming Emporium's
"Decompilations & Recompilations" page.

- Scrapes every project card that links to a GitHub/GitLab repository
- Skips anything already in the official Quiver community catalog
- Keeps hand-added entries from lists/manual.json
- Writes lists/GamingEmporiumExtras.json (only bumps version if apps changed)

Usage:
    python scripts/build_list.py                     # live scrape
    python scripts/build_list.py --html page.html    # parse a saved copy (for testing)
    python scripts/build_list.py --dry-run           # print summary, don't write
"""
import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://thegamingemporium.com/categories/decompilations-recompilations/"
QUIVER_INDEX = "https://raw.githubusercontent.com/tgeorgiadis/quiver-community-app-catalog/main/index.json"

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "lists" / "GamingEmporiumExtras.json"
MANUAL_FILE = ROOT / "lists" / "manual.json"      # optional extra apps you add by hand
EXCLUDE_FILE = ROOT / "lists" / "exclude.json"    # optional list of repos to never include
ICONS_FILE = ROOT / "lists" / "icons.json"        # repo -> SteamGridDB match; edit "url" to override

SGDB_API = "https://www.steamgriddb.com/api/v2"

# Everything from these words onward is about the project, not the game
GAME_NAME_CUT = re.compile(r"\s+(?:native\s+)?(?:pc\s+ports?|ports?|recompilation|recompiled|recomp|"
                           r"decompilation|reimplementation|plus|for steam deck|xbox 360|arcade|with|enhanced|"
                           r"online edition)\b.*$", re.I)

HEADERS = {"User-Agent": "Mozilla/5.0 (QuiverListBuilder; +https://github.com/)"}

REPO_RE = re.compile(r"^https?://(?:www\.)?(github|gitlab)\.com/([^/?#]+)/([^/?#]+)", re.I)

# Words in a title that mean "this isn't an installable app"
SKIP_TITLE_WORDS = ("mods", "mod page", "texture pack", "launcher", "custom levels",
                    "track editor", "rom patcher", "web browser build", "appimage",
                    "ports list", "hub for")

# GitHub owners/repos that are collections or not real app repos
SKIP_REPOS = {"alexbeav/psxrecomp-ports", "crownparkcomputing/xbox360-native-ports"}

PLATFORM_TAGS = {
    "nintendo 64": "n64", "snes": "snes", "nes": "nes", "game boy": "gb",
    "game boy color": "gbc", "game boy colour": "gbc", "game boy advance": "gba",
    "gamecube": "gcn", "wii": "wii", "wii u": "wiiu", "nintendo ds": "nds",
    "nintendo 3ds": "3ds", "virtual boy": "vb", "playstation": "psx",
    "playstation 2": "ps2", "playstation 3": "ps3", "playstation 4": "ps4", "playstation 5": "ps5",
    "psp": "psp", "ps vita": "vita", "xbox": "xbox", "xbox 360": "x360",
    "arcade": "arcade", "windows": "pc", "dos": "dos", "sega megadrive": "genesis",
    "sega mega drive": "genesis", "genesis": "genesis", "sega 32x": "32x",
    "sega dreamcast": "dreamcast", "dreamcast": "dreamcast", "amiga": "amiga",
    "android": "android", "ipod": "ipod", "multiple platforms": "multi",
}


def log(*a):
    print(*a, file=sys.stderr)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def official_repos():
    """Every repository already in the official Quiver catalog (lower-case)."""
    repos = set()
    index = requests.get(QUIVER_INDEX, timeout=60).json()
    entries = index if isinstance(index, list) else index.get("lists", index.get("catalogs", []))
    for e in entries:
        url = e.get("remoteLocation") or e.get("url") or e.get("location") or e.get("remoteUrl") or e.get("path")
        if not url:
            # fall back: any string value that looks like a json URL
            url = next((v for v in e.values() if isinstance(v, str) and v.endswith(".json")), None)
        if not url:
            continue
        data = requests.get(url, timeout=60).json()
        for app in data.get("apps", []):
            if app.get("repository"):
                repos.add(app["repository"].strip("/").lower())
    log(f"official Quiver catalog: {len(repos)} repos")
    return repos


def scrape(html):
    """Each project is a <div class="game-card" data-title=... data-platform=...>
    containing one <a class="game-card__link" href=...> (the Platform label sits
    inside the same card, just before the link)."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for card in soup.select("div.game-card"):
        a = card.select_one("a.game-card__link[href]")
        if not a:
            continue
        m = REPO_RE.match(a["href"].strip())
        if not m:
            continue
        host, owner, repo = m.group(1).lower(), m.group(2), m.group(3)
        repo = re.sub(r"\.git$", "", repo)
        if owner.lower() in ("sponsors", "orgs", "topics", "features"):
            continue
        key = f"{owner}/{repo}"
        if key.lower() in found:
            continue
        title_el = card.select_one(".game-card__title")
        title = (card.get("data-title") or (title_el.get_text(" ", strip=True) if title_el else "")).strip()
        platform = (card.get("data-platform") or "").strip() or "Other"
        if title:
            found[key.lower()] = {"title": title, "repo": key, "host": host, "platform": platform}
    items = list(found.values())
    log(f"scraped {len(items)} repo-linked projects")
    return items


def to_app(item):
    t = item["title"]
    p = item["platform"]
    tl = t.lower()
    if re.search(r"\b(mod|expansion)\b", tl):
        kind = "mod"
    else:
        kind = "recomp" if "recomp" in tl else ("decomp" if "decomp" in tl else "port")
    app = {
        "name": t,
        "repository": item["repo"],
        "folderName": re.sub(r"[^A-Za-z0-9]+", "", t)[:60],
        "appIconUrl": None,
        "tags": [kind, PLATFORM_TAGS.get(p.lower(), "other"), p.lower()],
    }
    if item["host"] == "gitlab":
        app["repositorySource"] = "gitlab"
    return app


def game_names(title):
    """Search terms for SteamGridDB, best guess first: the title with the project words
    stripped, then each side of a ' - ' (e.g. 'Outrun - Cannonball')."""
    t = re.sub(r"\([^)]*\)", "", title)
    t = re.sub(r"^decompilation of\s+", "", t, flags=re.I)
    t = re.sub(r"^GTA:?\s", "Grand Theft Auto: ", t)
    names = []
    parts = [t] + t.split(" - ")
    parts += [re.split(r",| and ", p)[0] for p in parts]   # 'Vigilante 8 and Vigilante 8: 2nd Offense'
    for p in parts:
        p = GAME_NAME_CUT.sub("", p).strip(" -,")
        if p and p.lower() not in (n.lower() for n in names):
            names.append(p)
    return names


def sgdb_get(path, key):
    time.sleep(0.2)  # be gentle with the API
    r = requests.get(f"{SGDB_API}{path}", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("data") or []


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


def norm_name(s):
    """Loose form of a game name for comparing: no accents, case, punctuation or 'the',
    roman numerals as digits, GTA spelled out."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\bgta\b", "grand theft auto", s.replace("&", " and "))
    words = [ROMAN.get(w, w) for w in re.findall(r"[a-z0-9]+", s) if w != "the"]
    return " ".join(words)


def name_score(searched, game):
    a, b = norm_name(searched), norm_name(game)
    score = difflib.SequenceMatcher(None, a, b).ratio()
    if a == b:
        return 1.0
    # Same game with a subtitle ('Lufia 2' vs 'Lufia II: Rise of the Sinistrals'), or our title has
    # extra project words ('Hydro Thunder Online' vs 'Hydro Thunder') - but not a sequel ('Shrek Forever After')
    if (b.startswith(a) and re.search(r":| - |\(", game)) or a.startswith(b + " "):
        score = max(score, 0.9)
    return score


def sgdb_art(game_id, key):
    """Top-voted icon, else a square grid, else any grid."""
    art = (sgdb_get(f"/icons/game/{game_id}", key)
           or sgdb_get(f"/grids/game/{game_id}?dimensions=512x512,1024x1024", key)
           or sgdb_get(f"/grids/game/{game_id}", key))
    return art[0]["thumb"] if art else None


def sgdb_lookup(title, key, min_score=0.86):
    """Best-named SteamGridDB game for one of the title's search terms that has some art."""
    for name in game_names(title):
        games = sgdb_get(f"/search/autocomplete/{requests.utils.quote(name, safe='')}", key)
        ranked = sorted(((name_score(name, g["name"]), g) for g in games), key=lambda x: -x[0])
        for score, game in ranked[:3]:
            if score < min_score:
                break
            url = sgdb_art(game["id"], key)
            if url:
                return {"searched": name, "game": game["name"], "url": url}
    return {"searched": None, "game": None, "url": None}


def add_icons(apps, save):
    """Fill appIconUrl from lists/icons.json, looking up anything new on SteamGridDB.
    Needs the SGDB_API_KEY environment variable; without it only cached icons are used."""
    cache = load_json(ICONS_FILE, {})
    key = os.environ.get("SGDB_API_KEY")
    if not key:
        log("SGDB_API_KEY not set - using cached icons only")
    looked_up = 0
    for app in apps:
        k = app["repository"].lower()
        if k not in cache and key:
            try:
                cache[k] = sgdb_lookup(app["name"], key)
                looked_up += 1
            except requests.RequestException as e:
                log(f"  SteamGridDB lookup failed for {app['name']}: {e}")
                if getattr(e.response, "status_code", None) in (401, 403):
                    log("SteamGridDB rejected the API key - skipping the rest of the lookups")
                    key = None
        if app.get("appIconUrl") is None and k in cache:
            app["appIconUrl"] = cache[k].get("url")
    if looked_up:
        log(f"looked up {looked_up} icons on SteamGridDB")
        if save:
            ICONS_FILE.write_text(json.dumps(dict(sorted(cache.items())), indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    log(f"icons: {sum(1 for a in apps if a.get('appIconUrl'))}/{len(apps)} apps")


def bump(version):
    parts = (version or "1.0.0").split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parse a saved HTML file instead of fetching the site")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    html = Path(args.html).read_text(encoding="utf-8") if args.html else fetch(SOURCE_URL)
    items = scrape(html)
    if len(items) < 50 and not args.html:
        sys.exit(f"Only {len(items)} projects found - site layout may have changed. Not writing.")

    official = official_repos()
    exclude = {r.lower() for r in load_json(EXCLUDE_FILE, [])} | SKIP_REPOS

    apps, seen = [], set()
    for it in items:
        k = it["repo"].lower()
        if k in official or k in exclude or k in seen:
            continue
        if any(w in it["title"].lower() for w in SKIP_TITLE_WORDS):
            continue
        seen.add(k)
        apps.append(to_app(it))

    for app in load_json(MANUAL_FILE, []):
        k = app["repository"].lower()
        if k not in seen and k not in official:
            seen.add(k)
            apps.append(app)

    add_icons(apps, save=not args.dry_run)
    apps.sort(key=lambda a: (a["tags"][2] if len(a.get("tags", [])) > 2 else "", a["name"].lower()))

    old = load_json(OUT_FILE, {})
    changed = old.get("apps") != apps
    catalog = {
        "name": "Gaming Emporium Extras",
        "description": "Ports and recomps from The Gaming Emporium not in the official Quiver lists",
        "version": bump(old.get("version")) if changed else old.get("version", "1.0.0"),
        "iconUrl": None,
        "preferredTagFilters": ["recomp", "decomp", "port", "mod", "n64", "snes", "nes", "gb", "gbc", "gba",
                                "gcn", "wii", "nds", "3ds", "psx", "ps2", "psp", "xbox", "x360",
                                "arcade", "pc"],
        "hiddenTagFilters": sorted({a["tags"][2] for a in apps if len(a.get("tags", [])) > 2}),
        "apps": apps,
    }

    added = {a["repository"] for a in apps} - {a["repository"] for a in old.get("apps", [])}
    removed = {a["repository"] for a in old.get("apps", [])} - {a["repository"] for a in apps}
    log(f"{len(apps)} apps | +{len(added)} -{len(removed)} | changed={changed}")
    for r in sorted(added):
        log(f"  + {r}")
    for r in sorted(removed):
        log(f"  - {r}")

    if not args.dry_run and changed:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
