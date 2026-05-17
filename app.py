# app.py
import argparse
import ctypes
import os
import subprocess
import sys

import ttkbootstrap as tb

from data.settings import Settings
from front.grabber import get_screen_res
from front.gui import PipelineGUI


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def check_and_restart_if_admin_needed():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--elevate', action='store_true', help='Run as admin')
    args, unknown = parser.parse_known_args()
    if (args.elevate or Settings.request_admin) and not is_admin():
        executable = sys.executable
        if "python.exe" in executable:
            executable = executable.replace("python.exe", "pythonw.exe")
            if not os.path.exists(executable):
                executable = sys.executable
        cmd_args = subprocess.list2cmdline(sys.argv[1:])
        script_path = f'"{os.path.abspath(sys.argv[0])}"'
        if getattr(sys, 'frozen', False):
            final_arguments = cmd_args
        else:
            final_arguments = f"{script_path} {cmd_args}"
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, final_arguments, None, 1)
        sys.exit()


def apply_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def run():
    check_and_restart_if_admin_needed()
    apply_dpi_awareness()
    theme = "darkly" if Settings.darkmode else "flatly"
    root = tb.Window(themename=theme)
    root.tk.call("tk", "scaling", 1.25)
    low_res = get_screen_res()[0] < 1600
    gui = PipelineGUI(root, low_res=low_res)

    def on_close():
        gui.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    run()
