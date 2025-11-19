import os.path
import sys
from pathlib import Path


def get_path(path_strings: str | list[str] | None = None):
    if getattr(sys, 'frozen', False):  # GPT: evaluates to True only when running from a packaged EXE.
        cur_path = Path(sys.executable).parent
    else:
        cur_path = Path(__file__).parent
    if path_strings is None:
        return cur_path
    if type(path_strings) is str:
        return os.path.join(cur_path, path_strings)
    if type(path_strings) is list:
        for s in path_strings:
            cur_path = os.path.join(cur_path, s)
    return cur_path
