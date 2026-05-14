# build.py
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
import fnmatch
import sys

from data.score_config import CURRENT_SEASON
from data.settings import Settings

BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_SCRIPT = "gui.py"
EXE_NAME = "CZN Pathfinder"
ZIP_NAME = f"CZN_Pathfinder_exe_build_{Settings.local_version}.zip"

# should yell if it detects new item not in expected or ignored
expected_items = [
    "Images/Encounter",
    "Images/Encounter_minimal_1920",
    "Images/Modifier_1920",
    "Images/Encounter_minimal_1600",
    "Images/Modifier_1600",
    "Images/filler_map.png",
    "LICENSE",
    "ManualScreenshotVisualGuide.png",
    "instructions.txt",
    "Images/Icon.ico",
    "Images/Fake_map",

]

release_ignore = [
    "__pycache__/",
    ".idea/",
    ".gitignore",
    "*.py",
    "*.xcf",
    "requirements.txt",
    "README.md",
    "Images/gui_image.png",
    "Images/Demo.gif",

]

DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
FINAL_OUTPUT_DIR = BASE_DIR / "Exe_build_folder"


def insert_custom_backgrounds(expected):
    path = BASE_DIR / "Images" / "Map_background"
    for image in os.listdir(path):
        if image.endswith("_g.png"):
            path_t = path / image
            expected.append(path_t)

def load_gitignore():
    path = BASE_DIR / ".gitignore"
    if not path.exists():
        return []
    rules = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rules.append(stripped)
    return rules


def _pattern_matches_path(p: str, rule: str) -> bool:
    anchored = rule.startswith("/")
    is_dir_rule = rule.endswith("/")
    core = rule.lstrip("/").rstrip("/")

    if is_dir_rule:
        if p == core or p.startswith(core + "/"):
            return True
        if fnmatch.fnmatch(p, rule):
            return True
        return False

    if anchored:
        if p == core or p.startswith(core + "/"):
            return True
        return False

    if fnmatch.fnmatch(p, rule):
        return True
    if fnmatch.fnmatch(Path(p).name, rule):
        return True

    return False


def match_gitignore(path: Path, rules):
    try:
        rel = path.relative_to(Path.cwd())
    except Exception:
        rel = path
    p = rel.as_posix().lstrip("./")

    if p == "git" or p.startswith("git/"):
        return True

    ignored = False
    for rule in rules:
        negate = rule.startswith("!")
        r = rule[1:] if negate else rule
        r = r.replace("\\", "/")

        if _pattern_matches_path(p, r):
            ignored = not negate  # positive rule -> ignore True; negation -> ignore False

    return ignored


def prepare():
    root = BASE_DIR.resolve()
    gitignore_rules = load_gitignore()
    result = []

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        try:
            rel = path.relative_to(root)
        except Exception:
            rel = Path(path.name)
        rel_posix = rel.as_posix()

        if match_gitignore(rel, gitignore_rules):
            continue

        ignore_entry = False
        for entry in release_ignore:
            if entry.endswith("/"):  # folder
                if rel_posix.startswith(entry):
                    ignore_entry = True
                    break
            elif entry.startswith('*'):  # check end
                if rel_posix.endswith(entry[1:]):
                    ignore_entry = True
                    break
            else:  # file
                if rel_posix == entry:
                    ignore_entry = True
                    break
        if ignore_entry:
            continue

        result.append(rel_posix)

    result.sort()
    return result


def expand_expected_items(items):
    expanded = []
    root = BASE_DIR

    for item in items:
        p = BASE_DIR / item
        if not p.exists():
            raise RuntimeError(f"expected_item not found: {item} at path {p}")

        if p.is_file():
            expanded.append(p.relative_to(root).as_posix())
        else:
            for sub in p.rglob("*"):
                if not sub.is_file():
                    continue

                rel = sub.relative_to(root).as_posix()

                # !Images/Map_background/*_g.png
                if rel.startswith("Images/Map_background/"):
                    if sub.suffix == ".png" and sub.name.endswith("_g.png"):
                        continue

                expanded.append(rel)

    expanded.sort()
    return expanded


def check_ready():
    actual = set(prepare())
    expected = set(expand_expected_items(expected_items))
    extras = sorted(actual - expected)

    if extras:
        print("Undefined items found:")
        for e in extras:
            print("  " + e)
        print("Build aborted.")
        sys.exit(1)

    print("Check passed.")


def clean_previous_builds():
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)


def build_executable():
    cmd = [
        "pyinstaller",
        "--clean",
        "CZN Pathfinder.spec"
    ]
    subprocess.run(cmd, check=True, cwd=BASE_DIR)


def create_zip():
    FINAL_OUTPUT_DIR.mkdir(exist_ok=True)
    zip_path = FINAL_OUTPUT_DIR / ZIP_NAME
    expanded = expand_expected_items(expected_items)
    exe_file = EXE_NAME + ".exe"
    exe_path = DIST_DIR / exe_file
    if not exe_path.exists():
        raise FileNotFoundError("No exe found")

    folder_prefix = EXE_NAME + "/"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(str(exe_path), folder_prefix + Path(exe_path).name)
        for item in expanded:
            z.write(BASE_DIR / item, folder_prefix + item)


def main():
    insert_custom_backgrounds(expected_items)
    check_ready()
    clean_previous_builds()
    build_executable()
    create_zip()
    clean_previous_builds()
    print("Build completed.")
    print(f"Version {Settings.local_version}, github {Settings.remote_version}"
          f" | season {CURRENT_SEASON} | CHECK IF THIS IS CORRECT")


if __name__ == "__main__":
    main()
