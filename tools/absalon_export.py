#!/usr/bin/env python3
"""Export course material from Absalon (KU's Canvas) to a local folder.

Run this on your own computer and point --out at your OneDrive folder;
OneDrive then syncs the files. Your access token never leaves your machine.

    1. Absalon -> Account -> Settings -> "+ New access token". Copy the token.
    2. python absalon_export.py --out "~/OneDrive/Absalon"
       (paste the token when asked, or set CANVAS_TOKEN beforehand)

By default only slide-like files (pdf, ppt, pptx, key, odp) are downloaded.
Use --all for every file. Re-running skips files that already exist.

Besides the files it writes `courses.md` in the output folder: every course
with its term and module titles, as raw material for the skills list.

Only uses the Python standard library.
"""

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://absalon.ku.dk"
SLIDE_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".pps", ".ppsx", ".key", ".odp"}


class Canvas:
    def __init__(self, base_url, token):
        self.api = base_url.rstrip("/") + "/api/v1"
        self.token = token

    def _open(self, url):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        return urllib.request.urlopen(req, timeout=60)

    def get_all(self, path, params=None):
        """GET a list endpoint, following Canvas' Link-header pagination."""
        query = urllib.parse.urlencode({"per_page": 100, **(params or {})}, doseq=True)
        url = f"{self.api}{path}?{query}"
        results = []
        while url:
            with self._open(url) as resp:
                results.extend(json.load(resp))
                url = _next_link(resp.headers.get("Link", ""))
        return results

    def get(self, path):
        with self._open(self.api + path) as resp:
            return json.load(resp)

    def download(self, url, dest):
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self._open(url) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 16):
                f.write(chunk)
        tmp.replace(dest)


def _next_link(header):
    for part in header.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1 : part.find(">")]
    return None


def fix_mojibake(text):
    """Repair UTF-8 read as cp1252, which Absalon has in some course names ("Ã˜konomi")."""
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:150] or "untitled"


def course_files(canvas, course_id):
    """All files in a course, via the Files tab, falling back to modules."""
    try:
        return canvas.get_all(f"/courses/{course_id}/files")
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403, 404):
            raise
    # Files tab hidden for students: collect the files linked from modules.
    files = {}
    for module in canvas.get_all(f"/courses/{course_id}/modules", {"include[]": "items"}):
        for item in module.get("items", []):
            if item.get("type") == "File" and item["content_id"] not in files:
                try:
                    files[item["content_id"]] = canvas.get(f"/courses/{course_id}/files/{item['content_id']}")
                except urllib.error.HTTPError:
                    pass
    return list(files.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output folder, e.g. your OneDrive folder")
    parser.add_argument("--all", action="store_true", help="download every file, not just slides")
    parser.add_argument("--list-only", action="store_true", help="only write courses.md, download nothing")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    token = os.environ.get("CANVAS_TOKEN") or getpass.getpass("Absalon access token: ")
    canvas = Canvas(args.base_url, token)
    out = Path(args.out).expanduser().resolve()
    # Course material is copyrighted and must never be committed to GitHub.
    repo = next((p for p in (out, *out.parents) if (p / ".git").exists()), None)
    if repo:
        sys.exit(f"Refusing to write into the git repository {repo}. Choose a folder outside it, e.g. OneDrive.")
    out.mkdir(parents=True, exist_ok=True)

    courses = canvas.get_all("/courses", {"include[]": "term", "state[]": ["available", "completed"]})
    courses = [c for c in courses if c.get("name")]  # skip access-restricted stubs
    courses.sort(key=lambda c: c.get("term", {}).get("start_at") or "", reverse=True)
    print(f"Found {len(courses)} courses")

    inventory = ["# Absalon courses\n"]
    for course in courses:
        term = course.get("term", {}).get("name", "No term")
        name = fix_mojibake(course["name"])
        print(f"\n== {name} ({term})")

        inventory.append(f"\n## {name}\n\n- Term: {term}\n- Code: {fix_mojibake(course.get('course_code', ''))}\n")
        try:
            modules = canvas.get_all(f"/courses/{course['id']}/modules")
            if modules:
                inventory.append("- Modules:\n")
                inventory.extend(f"  - {m['name']}\n" for m in modules)
        except urllib.error.HTTPError:
            pass

        if args.list_only:
            continue

        try:
            files = course_files(canvas, course["id"])
        except urllib.error.HTTPError as e:
            print(f"   could not list files ({e.code}), skipping")
            continue

        course_dir = out / safe_name(f"{term} - {name}")
        used = set()
        for f in files:
            filename = f.get("display_name") or f.get("filename", "")
            if not args.all and Path(filename).suffix.lower() not in SLIDE_EXTENSIONS:
                continue
            if not f.get("url"):
                continue  # locked or unpublished
            dest = course_dir / safe_name(filename)
            if dest.name in used:  # same name in two Absalon folders
                dest = dest.with_name(f"{dest.stem} ({f['id']}){dest.suffix}")
            used.add(dest.name)
            if dest.exists() and dest.stat().st_size == f.get("size", -1):
                continue
            course_dir.mkdir(parents=True, exist_ok=True)
            print(f"   {filename}")
            try:
                canvas.download(f["url"], dest)
            except (urllib.error.URLError, OSError) as e:
                print(f"   failed: {e}", file=sys.stderr)

    (out / "courses.md").write_text("".join(inventory), encoding="utf-8")
    print(f"\nDone. Course overview written to {out / 'courses.md'}")


if __name__ == "__main__":
    main()
