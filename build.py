import os
import shutil
import subprocess
import zipfile
from pathlib import Path
import fnmatch
import sys

SOURCE_SCRIPT = "gui.py"
EXE_NAME = "CZN Pathfinder"
ZIP_NAME = "CZN_Pathfinder_exe_build.zip"

# should yell if it detects new item not in expected or ignored
expected_items = [
    "Example_scan_result",
    "Images/Encounter",
    "Images/Encounter_minimal_1920",
    "Images/Modifier_1920",
    "Images/Encounter_minimal_1600",
    "Images/Modifier_1600",
    "Images/background_img.png",
    "Images/filler_map.png",
    "LICENSE",
    "ManualScreenshotVisualGuide.png",
    "instructions.txt",
    "Images/Demo.gif",

]

release_ignore = [
    "__pycache__/",
    ".idea/",
    ".gitignore",
    "*.py",
    "*.xcf",
    "requirements.txt",
    "README.md",
    "Images/Icon.ico",
    "Images/background_img_blank.png",
    "Images/gui_image.png",

]

DIST_DIR = Path("dist")
BUILD_DIR = Path("build")
FINAL_OUTPUT_DIR = Path("Exe_build_folder")


def load_gitignore():
    path = Path(".gitignore")
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
    root = Path(".").resolve()
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
    """
    Expand all expected items into a file list (posix-style relative paths)
    relative to the current working directory.
    """
    expanded = []
    root = Path(".")

    for item in items:
        p = Path(item)
        if not p.exists():
            raise RuntimeError(f"expected_item not found: {item}")

        if p.is_file():
            expanded.append(p.relative_to(root).as_posix())
        else:
            for sub in p.rglob("*"):
                if sub.is_file():
                    expanded.append(sub.relative_to(root).as_posix())

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
    files = os.listdir()
    to_be_removed = []
    for f in files:
        if f.endswith('.spec'):
            to_be_removed.append(f)

    for f in os.listdir("Example_scan_result"):
        if not f.startswith("map"):
            to_be_removed.append(os.path.join("Example_scan_result", f))
    for f in to_be_removed:
        os.remove(f)


def build_executable():
    cmd = [
        "pyinstaller",
        "--onefile",
        "--clean",
        "--noconsole",
        "--icon=Images/Icon.ico",
        f"--name={EXE_NAME}",
        SOURCE_SCRIPT
    ]
    subprocess.run(cmd, check=True)


def create_zip():
    FINAL_OUTPUT_DIR.mkdir(exist_ok=True)
    zip_path = FINAL_OUTPUT_DIR / ZIP_NAME
    expanded = expand_expected_items(expected_items)
    exe_file = EXE_NAME + ".exe"
    exe_path = Path("dist") / exe_file
    if not exe_path.exists():
        raise FileNotFoundError("No exe found")

    folder_prefix = EXE_NAME + "/"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(str(exe_path), folder_prefix + Path(exe_path).name)
        for item in expanded:
            z.write(item, folder_prefix + item)


def main():
    check_ready()
    clean_previous_builds()
    build_executable()
    create_zip()
    clean_previous_builds()
    print("Build completed.")


if __name__ == "__main__":
    main()
