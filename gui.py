# gui.py
import ctypes
import sys
import os
import subprocess
import argparse
import threading
import time
import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as tb
import cv2
from pathlib import Path

if not hasattr(cv2, "__version__"):  # random GPT-approved dependency error fix todo: check if i still need it?
    cv2.__version__ = "4"
import numpy as np
from PIL import Image, ImageTk
import webbrowser
import re

from pipeline import run_auto_pipeline, run_offline_pipeline, run_halfauto_pipeline, get_game_screenshot, run_pathfinder
from grabber import get_screen_res, KeyboardListener, switch_window
from calibrator import check_calibration_done
from drawer import draw_map, load_icon
from score_table import ScoreTable
from score_config import SEASONS
from path_converter import get_path
from gui_calibrator import CalibrationPanel
from settings import Settings
from version_checker import check_for_update
from gui_settings import SettingsPanel


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


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


class PipelineGUI:
    def __init__(self, root, low_res=False):
        self.root = root
        self.low_res = low_res
        self.map_scale_normal = Settings.ui_map_image_scale_normal / 100  # as %
        self.map_scale_mini = Settings.ui_map_image_scale_mini / 100  # as %
        self._is_mini = False

        if self.low_res:
            self.left_panel_w = 880
            self.left_panel_h = 490
            self.right_panel_w = 410
            self.right_panel_h = 420
        else:
            self.left_panel_w = 1190
            self.left_panel_h = 490
            self.right_panel_w = 410
            self.right_panel_h = 420

        self._update_geometry()
        self.root.title(f"CZN Pathfinder {Settings.local_version}")
        self.root.iconbitmap("Images/Icon.ico")
        self.root.attributes('-topmost', Settings.ui_window_always_on_top)
        self.root.resizable(False, False)
        self.root.update()

        self.selected_folder = None
        self.last_map = None
        self.last_image = None
        self.last_path = None
        self.log_file_path = get_path("log_file.log")
        self.score_table = ScoreTable()
        self.score_mode = tk.StringVar(value=self.score_table.active_season)
        self._delayed_pathfinder_id = None
        self._icons = {}
        self._blink_state = False
        self._scanner_running = False
        self._demo_params_copy = []
        self._last_pil = None

        self._build_ui()
        self._initiate_keyboard_listener()
        self._load_initial_background()
        self._blink_loop()
        if Settings.auto_import_score and ScoreTable.check_file_exists():
            self.import_score_table()
        self._check_update()

    # ======================================================================
    # UI Construction
    # ======================================================================
    def _scale_to_ui_size(self, val):
        s = self.map_scale_mini if self._is_mini else self.map_scale_normal
        return int(val * s)

    def _update_geometry(self, change: bool = False):
        if change:
            # if leaving mini mode, capture current position
            if self._is_mini:
                self.root.update_idletasks()
                Settings.ui_window_offset_x_mini = self.root.winfo_x()
                Settings.ui_window_offset_y_mini = self.root.winfo_y()
                Settings.save()
            self._is_mini = not self._is_mini

        scaled_w = self._scale_to_ui_size(self.left_panel_w)
        scaled_h = self._scale_to_ui_size(self.left_panel_h)

        # first startup check, place mini at half-length of display
        if Settings.ui_window_offset_x_mini == -1:
            Settings.ui_window_offset_x_mini = int(self.root.winfo_screenwidth() / 2)

        if self._is_mini:
            self.window_w = scaled_w
            self.window_h = scaled_h
            window_x = Settings.ui_window_offset_x_mini if Settings.ui_window_offset_x_mini >= 0 else 0
            window_y = Settings.ui_window_offset_y_mini if Settings.ui_window_offset_y_mini >= 0 else 0
        else:
            self.window_w = scaled_w + self.right_panel_w
            self.window_h = max(scaled_h, self.right_panel_h)
            window_x = Settings.ui_window_offset_x if Settings.ui_window_offset_x >= 0 else 0
            window_y = Settings.ui_window_offset_y if Settings.ui_window_offset_y >= 0 else 0

        self.root.geometry(f"{self.window_w}x{self.window_h}+{window_x}+{window_y}")
        self.root.update()
        if hasattr(self, "_last_pil") and self._last_pil is not None:
            self.display_image(self._last_pil)

    def _build_ui(self):
        main_frame = tb.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        self._build_left_image_panel(main_frame)
        self._build_right_panel(main_frame)

    def _build_left_image_panel(self, parent):
        panel = tb.Frame(
            parent,
            width=self._scale_to_ui_size(self.left_panel_w),
            height=self._scale_to_ui_size(self.left_panel_h),
        )
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self.image_label = tb.Label(panel)
        self.image_label.pack(fill="both", expand=True)
        self.image_label.bind("<Double-Button-1>", lambda e: self._update_geometry(change=True))

    def _build_right_panel(self, parent):
        panel = tb.Frame(parent, width=self.right_panel_w, height=self.right_panel_h)
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self._build_log_display(panel)
        self._build_button_rows(panel)

        # keep ref so it can be rebuilt
        self.score_table_container = tb.Frame(panel)
        self.score_table_container.pack(fill="both", expand=True)
        self._build_score_table(self.score_table_container)

    def _build_log_display(self, parent):
        frame = tb.Frame(parent)
        frame.pack(fill="x")

        scrollbar = tb.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.log_display = tb.Text(
            frame,
            width=40,
            height=6,
            wrap="word",
            state="disabled",
            cursor="arrow",
            yscrollcommand=scrollbar.set,
        )
        self.log_display.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_display.yview)

        def wheel(event):
            self.log_display.yview_scroll(int(-event.delta / 120), "units")

        self.log_display.bind("<Enter>", lambda _: self.log_display.bind_all("<MouseWheel>", wheel))
        self.log_display.bind("<Leave>", lambda _: self.log_display.unbind_all("<MouseWheel>"))

    def _build_button_rows(self, parent):
        row1 = tb.Frame(parent)
        row1.pack(pady=5, fill="x")

        # keep reference so it can blink and annoy user if calibration is wrong
        self.recalibrate_button = tb.Button(row1, text="Calibrator", width=19, command=self.start_calibrator,
                                            padding=4)
        self.recalibrate_button.pack(side="left", padx=3)
        (tb.Button(row1, text="Automatic Scanner", width=19, command=self.start_automatic_pipeline, padding=4)
         .pack(side="left", padx=3))
        (tb.Button(row1, text="Import Score Table", width=19, command=self.import_score_table, padding=4)
         .pack(side="left", padx=3))

        row2 = tb.Frame(parent)
        row2.pack(pady=5, fill="x")

        self.folder_button = tb.Button(row2, text="Choose Folder", width=19, command=self.choose_folder, padding=4)
        self.folder_button.pack(side="left", padx=3)
        (tb.Button(row2, text="Halfauto Scanner", width=19, command=self.start_halfauto_pipeline, padding=4)
         .pack(side="left", padx=3))

        (tb.Button(row2, text="Export Score Table", width=19, command=self.export_score_table, padding=4)
         .pack(side="left", padx=3))

        row3 = tb.Frame(parent)
        row3.pack(pady=5, fill="x")
        (tb.Button(row3, text="Settings", width=19, command=lambda: SettingsPanel(self.root), padding=4)
         .pack(side="left", padx=3))
        (tb.Button(row3, text="Offline Scanner", width=19, command=self.start_offline_pipeline, padding=4)
         .pack(side="left", padx=3))

    def _build_score_table(self, parent):
        # cleanup so it can be rebuilt
        for child in self.score_table_container.winfo_children():
            child.destroy()
        self.score_vars = {}
        self.score_labels = {}
        self._icons = {}

        # real build
        panel = tb.Frame(parent)
        panel.pack(fill="both", expand=True)
        header_row = tb.Frame(panel)
        header_row.pack(fill="x")
        tb.Label(header_row, text="Score Table", anchor="w").pack(side="top")

        tb.Radiobutton(
            header_row,
            text="Season 1-2",
            variable=self.score_mode,
            value="s12",
            command=self._on_score_mode_change
        ).pack(side="left", padx=5)
        tb.Radiobutton(
            header_row,
            text="Season 3",
            variable=self.score_mode,
            value="s3",
            command=self._on_score_mode_change
        ).pack(side="left", padx=5)

        self.score_vars = {}
        self.score_labels = {}
        columns_frame = tb.Frame(panel)
        columns_frame.pack(fill="x")

        active_keys = SEASONS[self.score_mode.get()].active_scores
        items = [
            (k, v)
            for k, v in self.score_table.table.items()
            if k in active_keys
        ]
        nodes = []
        mods = []
        for key, val in items:
            if len(key) == 2:
                nodes.append((key, val))
            else:
                mods.append((key, val))

        mod_idx = 0
        mod_len = len(mods)

        for node_key, node_val in nodes:
            row_frame = tb.Frame(columns_frame)
            row_frame.pack(fill="x")
            row_frame.columnconfigure(0, weight=1, uniform="col")
            row_frame.columnconfigure(1, weight=1, uniform="col")
            left = tb.Frame(row_frame)
            right = tb.Frame(row_frame)
            left.grid(row=0, column=0, sticky="ew")
            right.grid(row=0, column=1, sticky="ew")
            self._create_score_row(left, node_key, node_val)
            if mod_idx < mod_len:
                mod_key, mod_val = mods[mod_idx]
                self._create_score_row(right, mod_key, mod_val)
                mod_idx += 1
            else:
                filler = tb.Frame(right)
                filler.pack(fill="both", expand=True)

            while mod_idx < mod_len and mods[mod_idx][0].startswith(node_key):
                row_frame = tb.Frame(columns_frame)
                row_frame.pack(fill="x")
                row_frame.columnconfigure(0, weight=1, uniform="col")
                row_frame.columnconfigure(1, weight=1, uniform="col")
                left = tb.Frame(row_frame)
                right = tb.Frame(row_frame)
                left.grid(row=0, column=0, sticky="ew")
                right.grid(row=0, column=1, sticky="ew")
                # filler on nodes side so mods are still kinda aligned
                filler = tb.Frame(left)
                filler.pack(fill="both", expand=True)
                mod_key, mod_val = mods[mod_idx]
                self._create_score_row(right, mod_key, mod_val)
                mod_idx += 1

    def _create_score_row(self, parent, key, value):
        def _on_scale_change(val, k=key, label_widget=None):
            if label_widget is not None:
                label_widget.config(text=str(int(float(val))))
            self.update_score_value(k)

        enc_folder = get_path(["Images", "Encounter_minimal_1600"])
        mod_folder = get_path(["Images", "Modifier_1600"])
        row = tb.Frame(parent)
        row.pack(fill="x", expand=True)
        if len(key) == 2:
            img = load_icon(enc_folder, key)
        else:
            img = load_icon(mod_folder, key[2:])
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)

        pil = Image.fromarray(img)
        icon = ImageTk.PhotoImage(pil)
        self._icons[key] = icon
        tb.Label(row, text=key, image=icon, anchor="w").pack(side="left", padx=1)

        value_label = tb.Label(row, text=str(value.value))  # value over slider
        value_label.pack(side="top", anchor="n", padx=1)
        var = tb.IntVar(value=value.value)
        self.score_vars[key] = var
        self.score_labels[key] = value_label
        tk.Scale(
            row,
            from_=-10 if not value.big_scale else -50,
            to=10 if not value.big_scale else 50,
            orient="horizontal",
            length=150,
            variable=var,
            command=lambda v, lb=value_label, k=key: _on_scale_change(v, k, lb),
            borderwidth=1,
            highlightthickness=0,
            sliderlength=10,
            resolution=1 if not value.big_scale else 5,
        ).pack(side="left", padx=1)

    # ======================================================================
    # Logging
    # ======================================================================
    def log(self, msg):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"

        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

        self.root.after(0, lambda: self._append_log_line(line))

    def _append_log_line(self, line):
        try:
            self.log_display.configure(state="normal")
            start_index = self.log_display.index("end-1c")
            self.log_display.insert("end", line + "\n")
            end_index = self.log_display.index("end-1c")

            urls = re.findall(r'https?://\S+', line)
            style = tb.Style()
            link_color = style.colors.info
            for url in urls:
                url_start = self.log_display.search(url, start_index, stopindex=end_index)
                if url_start:
                    url_end = f"{url_start}+{len(url)}c"
                    self.log_display.tag_add(url, url_start, url_end)
                    self.log_display.tag_config(
                        url,
                        foreground=link_color,
                        underline=True
                    )
                    self.log_display.tag_bind(
                        url,
                        "<Button-1>",
                        lambda e, link=url: webbrowser.open(link)
                    )
                    self.log_display.tag_bind(
                        url, "<Enter>", lambda e: self.log_display.config(cursor="hand2")
                    )
                    self.log_display.tag_bind(
                        url, "<Leave>", lambda e: self.log_display.config(cursor="")
                    )

            self.log_display.configure(state="disabled")
            self.log_display.see("end")
        except tk.TclError:
            pass

    # ======================================================================
    # Image Handling
    # ======================================================================
    def display_image(self, obj):
        try:
            im = self._to_image(obj)
            self._last_pil = im
            w, h = im.size
            new_w = self._scale_to_ui_size(w)
            new_h = self._scale_to_ui_size(h)
            im = im.resize((new_w, new_h), Image.Resampling.BILINEAR)

            self.last_image = ImageTk.PhotoImage(im)
            self.image_label.config(image=self.last_image)
        except Exception as e:
            self.log(f"Image error: {e}")

    def _to_image(self, obj):
        if isinstance(obj, str):
            return Image.open(obj)

        if isinstance(obj, Image.Image):
            return obj

        if isinstance(obj, np.ndarray):
            arr = obj.astype(np.uint8)
            if arr.ndim == 2:
                return Image.fromarray(arr, "L")
            if arr.ndim == 3:
                if arr.shape[2] == 3:
                    arr = arr[:, :, ::-1]
                    return Image.fromarray(arr, "RGB")
                if arr.shape[2] == 4:
                    arr = arr[:, :, [2, 1, 0, 3]]
                    return Image.fromarray(arr, "RGBA")
            raise ValueError(f"Unsupported array shape: {arr.shape}")

        if isinstance(obj, tuple):
            return self._to_image(obj[0])

        raise TypeError(f"Unsupported image type: {type(obj)}")

    def _load_initial_background(self):
        img = Image.open(get_path(["Images", "filler_map.png"]))
        if self.low_res:
            img = img.resize((self._scale_to_ui_size(self.right_panel_w),
                              self._scale_to_ui_size(self.right_panel_h)),
                             Image.Resampling.BILINEAR)
        self.display_image(img)

    # ======================================================================
    # Folder Management
    # ======================================================================
    def choose_folder(self):
        if self.selected_folder is None:
            path = filedialog.askdirectory(initialdir=get_path())
            if path:
                self.selected_folder = path
                self.folder_button.configure(text="Clear Folder")
                self.log(f"Selected Folder: {self.selected_folder}")
        else:
            self.selected_folder = None
            self.folder_button.configure(text="Choose Folder")
            self.log(f"Cleared folder selection")

    # ======================================================================
    # Pipeline Actions
    # ======================================================================
    def start_automatic_pipeline(self, from_key=False):
        if self._scanner_running:
            self.log("Tried to run more than one scanner at once, ignoring request")
            return
        if self.selected_folder:
            if os.listdir(self.selected_folder):
                self.log("Please select empty folder for auto scanning, scanner may get confused on unrelated files")
                return

        if not check_calibration_done():
            self.log("Please perform calibration first.")
            return

        if not is_admin():
            self.show_warning_dialog("no_admin")
            return

        if not from_key:
            if not self.ask_continue_dialog("auto"):
                self.log("Scanning task cancelled")
                return

        self._scanner_running = True
        threading.Thread(target=self._run_auto_pipeline, daemon=True).start()

    def _run_auto_pipeline(self):
        try:
            self.log("Auto scanner started")
            m, path, img = run_auto_pipeline(
                save_folder=self.selected_folder,
                log=self.log,
                score_table=self.score_table
            )
            self.last_map = m
            self.last_path = path
            self.display_image(img)
        except Exception as e:
            self.log(f"Pipeline error: {e}")
            switch_window(1)
            if Settings.testmode:
                raise
        finally:
            self._scanner_running = False

    def start_halfauto_pipeline(self, from_key=False):
        if self._scanner_running:
            self.log("Tried to run more than one scanner at once, ignoring request")
            return
        if self.selected_folder:
            if os.listdir(self.selected_folder):
                self.log("Please select empty folder for auto scanning, scanner may get confused on unrelated files")
                return

        if not check_calibration_done():
            self.log("Please perform calibration first.")
            return

        if not is_admin():
            self.show_warning_dialog("no_admin")
            return

        if not from_key:
            if not self.ask_continue_dialog("halfauto"):
                self.log("Scanning task cancelled")
                return

        self._scanner_running = True
        threading.Thread(target=self._run_halfauto_pipeline, daemon=True).start()

    def _run_halfauto_pipeline(self):
        try:
            self.log("Halfauto scanner started")
            m, path, img = run_halfauto_pipeline(
                save_folder=self.selected_folder,
                log=self.log,
                score_table=self.score_table
            )
            self.last_map = m
            self.last_path = path
            self.display_image(img)
        except Exception as e:
            self.log(f"Pipeline error: {e}")
            switch_window(1)
            if Settings.testmode:
                raise
        finally:
            self._scanner_running = False

    def start_offline_pipeline(self):
        if self._scanner_running:
            self.log("Tried to run more than one scanner at once, ignoring request")
            return
        if not self.selected_folder:
            if Settings.testmode:
                self.log("No folder selected, TESTMODE; setting to Last_scan_result")
                self.selected_folder = get_path("Last_scan_result")
            else:
                self.log("Select folder with screenshots first")
                return

        demo_override = True if "Example_scan_result" in str(self.selected_folder) else False
        if demo_override:
            self._prepare_demo()
            self.log("Preparing demo parameters")
        else:
            if not check_calibration_done():
                self.log("Please perform calibration first.")
                return

        self._scanner_running = True
        threading.Thread(target=self._run_offline_pipeline, daemon=True).start()

    def _run_offline_pipeline(self):
        try:
            m, path, img = run_offline_pipeline(
                save_folder=self.selected_folder,
                log=self.log,
                score_table=self.score_table
            )
            self.last_map = m
            self.last_path = path
            self.display_image(img)
        except Exception as e:
            self.log(f"Pipeline error: {e}")
            if Settings.testmode:
                raise
        finally:
            self._scanner_running = False
            if len(self._demo_params_copy) > 0:
                self._restore_after_demo()

    def _prepare_demo(self):
        self._demo_params_copy.clear()
        self._demo_params_copy.append(Settings.screenshot_scale)
        self._demo_params_copy.append(Settings.template_scale)
        self._demo_params_copy.append(Settings.threshold)
        Settings.screenshot_scale = 1.0
        Settings.template_scale = 1.0
        Settings.threshold = 0.97

    def _restore_after_demo(self):
        if len(self._demo_params_copy) != 3:
            raise IOError("Restore impossible, unknown program state")
        Settings.threshold = self._demo_params_copy.pop()
        Settings.template_scale = self._demo_params_copy.pop()
        Settings.screenshot_scale = self._demo_params_copy.pop()

    def rerun_pathfinder(self):
        if not self.last_map:
            self.log("No map loaded")
            return

        self.log("Re-running pathfinder")

        def task():
            try:
                path, encounter_ranges, encounter_counts = run_pathfinder(self.last_map, self.score_table)
                self.last_path = path
                img = draw_map(self.last_map,
                               path,
                               encounter_ranges=encounter_ranges,
                               encounter_counts=encounter_counts)
                self.display_image(img)
            except Exception as e:
                self.log(f"Re-run error: {e}")

        threading.Thread(target=task, daemon=True).start()

    def _get_valid_calibration_folder(self):
        folder = Path(get_path(["Last_scan_result"]))
        if not folder.exists() or not folder.is_dir():
            return None

        try:
            files = CalibrationPanel.scan_folder(folder)
            return folder if files else None
        except Exception:
            return None

    def start_calibrator(self):
        if not self.ask_continue_dialog("calibrator"):
            self.log("Calibrator task cancelled")
            return

        scr = get_game_screenshot(self.log)
        has_game_image = scr is not None and getattr(scr, "size", (0, 0))[0] > 0
        folder = self._get_valid_calibration_folder()

        if not has_game_image and folder is None:
            self.log("Calibration aborted: no game screenshot and no valid image folder found")
            return

        if not has_game_image and folder is not None and not Settings.testmode:
            if not self.ask_continue_dialog("calibrator_no_game"):
                self.log("Calibrator task cancelled")
                return

        CalibrationPanel(
            parent=self.root,
            low_res=self.low_res,
            log=self.log,
            scr=scr if has_game_image else None,
            folder=folder
        )

    # ======================================================================
    # Score Table Operations
    # ======================================================================
    def update_score_value(self, key):
        self.score_table.table[key].value = self.score_vars[key].get()

        if self.last_map is not None:
            if self._delayed_pathfinder_id is not None:
                self.root.after_cancel(self._delayed_pathfinder_id)
            self._delayed_pathfinder_id = self.root.after(500, self.rerun_pathfinder)

    def import_score_table(self):
        try:
            st = ScoreTable.import_()
            self.score_table = st

            for key, val in st.table.items():
                if key in self.score_vars:
                    self.score_vars[key].set(val.value)
                    self.score_labels[key].config(text=str(val.value))

            self.log("ScoreTable imported")

            if self.last_map is not None:
                if self._delayed_pathfinder_id is not None:
                    self.root.after_cancel(self._delayed_pathfinder_id)
                self._delayed_pathfinder_id = self.root.after(500, self.rerun_pathfinder)

        except Exception as e:
            self.log(f"Import error: {e}")

    def export_score_table(self):
        try:
            ScoreTable.export(self.score_table)
            self.log("ScoreTable exported")
        except Exception as e:
            self.log(f"Export error: {e}")

    def _on_score_mode_change(self):
        self.score_table.active_season = self.score_mode.get()
        self.log(f"Score mode changed to: {self.score_table.active_season}")
        # rebuild UI completely
        self._build_score_table(self.score_table_container)

        # optional: rerun pathfinder
        if self.last_map is not None:
            if self._delayed_pathfinder_id is not None:
                self.root.after_cancel(self._delayed_pathfinder_id)
            self._delayed_pathfinder_id = self.root.after(200, self.rerun_pathfinder)

    # ======================================================================
    # Dialogs
    # ======================================================================
    def _base_dialog(self, title):
        win = tb.Toplevel(self.root)
        win.title(title)
        win.grab_set()
        win.transient(self.root)
        return win

    def ask_continue_dialog(self, variant):
        win = self._base_dialog("Confirm Action")

        if variant == "auto":
            text = (
                "You are about to start the scanning process.\n"
                "IT MOVES YOUR REAL MOUSE, this is intended behavior.\n"
                "Make sure alt-tab leads to the game, the game has minimap opened and in default position (not moved left/right).\n"
                "Do not touch mouse or keyboard until scanning is done.\n\n"
                "If the scanner behaves incorrectly, quickly move mouse to top left screen corner to stop it.\n"
                "If the script failed to switch window, alt-tab to game and back, then start again."
            )
        elif variant == "halfauto":
            text = (
                "You are about to start the scanning process.\n"
                "After you confirm this window, every mouse drag move will produce a screenshot.\n"
                "It will stop once the script sees boss or detect no nodes on screen. Or right click is detected.\n\n"
                "Make sure you are ready, then press enter / continue.\n"
            )
        elif variant == "calibrator":
            text = (
                "You are about to start the calibrating process.\n"
                "It will take a game screenshot then then open new gui window.\n"
                "Make sure alt-tab leads to the game, the game has minimap opened and in a position that shows different\n"
                "types of nodes and modifiers, the more the better. Starting position is BAD, move it to the right a bit.\n\n"
                "If the script failed to switch window, alt-tab to game and back, then start again."
            )
        elif variant == "calibrator_no_game":
            text = (
                "Game screenshot capture failed.\n\n"
                "To try again, choose Cancel, alt-tab to game and back, then press Calibrator.\n"
                "To load Last_scan_result folder instead, choose Continue."
            )
        else:
            text = "Not implemented"

        tb.Label(win, text=text).pack(padx=20, pady=15)

        result = {"value": False}

        def confirm(_=None):
            result["value"] = True
            win.destroy()

        def cancel(_=None):
            win.destroy()

        btn_frame = tb.Frame(win)
        btn_frame.pack(pady=10)

        btn_ok = tb.Button(btn_frame, text="Continue", width=12, command=confirm)
        btn_ok.pack(side="left", padx=5)
        tb.Button(btn_frame, text="Cancel", width=12, command=cancel).pack(side="right", padx=5)

        btn_ok.focus_set()
        win.bind("<Return>", confirm)
        win.bind("<Escape>", cancel)

        self._center_popup(win)
        self.root.wait_window(win)
        return result["value"]

    def show_warning_dialog(self, variant):
        win = self._base_dialog("Warning")

        if variant == "no_admin":
            text = (
                "The scanner needs admin elevation to work properly.\n"
                "Please enable 'Request admin on startup' option in settings, then restart the script.\n"
                "Or run script as admin by any other way, for example right click - run as admin.\n\n"
                "Want to run it without admin? Offline scanner does not need it, it just reads images from folder."
            )
        else:
            text = "Not implemented"

        tb.Label(win, text=text).pack(padx=20, pady=15)

        def close(_=None):
            win.destroy()

        btn = tb.Button(win, text="OK", width=12, command=close)
        btn.pack(pady=10)

        btn.focus_set()
        win.bind("<Return>", close)
        win.bind("<Escape>", close)

        self._center_popup(win)
        self.root.wait_window(win)

    def _center_popup(self, win):
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - win.winfo_reqwidth() // 2
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - win.winfo_reqheight() // 2
        win.geometry(f"+{x}+{y}")

    # ======================================================================
    # Periodic UI Update
    # ======================================================================
    def _blink_loop(self):
        if check_calibration_done():
            self.recalibrate_button.config(bootstyle="primary")
            return
        interval = 700
        if self._blink_state:
            self.recalibrate_button.config(bootstyle="danger")
            interval *= 2
        else:
            self.recalibrate_button.config(bootstyle="primary")
        self._blink_state = not self._blink_state

        self.root.after(interval, self._blink_loop)

    def _check_update(self):
        def task():
            try:
                time.sleep(1)
                check_for_update(self.log)
            except Exception as e:
                self.log(f"Update check error: {e}")

        threading.Thread(target=task, daemon=True).start()

    def _initiate_keyboard_listener(self):
        hotkeys = [
            ("auto", Settings.keyboard_input_autoscanner),
            ("halfauto", Settings.keyboard_input_halfautoscanner),
        ]
        if Settings.keyboard_input:
            try:
                self._kb_listener = KeyboardListener(
                    hotkeys=hotkeys,
                    on_trigger=self._on_keyboard_action
                )
                self._kb_listener.start()
            except ValueError as e:
                self._kb_listener = None
                self.log(f"Keyboard detection inactive due to the error: {e}")
        else:
            self._kb_listener = None

    def _on_keyboard_action(self, action):
        self.root.after(0, lambda: self._handle_keyboard_action(action))

    def _handle_keyboard_action(self, action):
        if action == "auto":
            self.start_automatic_pipeline(from_key=True)
        elif action == "halfauto":
            self.start_halfauto_pipeline(from_key=True)

    def shutdown(self):
        if self._kb_listener:
            self._kb_listener.stop()


# ======================================================================
# Main
# ======================================================================
def app_do_not_scale():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass


if __name__ == "__main__":
    app_do_not_scale()
    theme = "darkly" if Settings.darkmode else "flatly"
    root = tb.Window(themename=theme)
    root.tk.call('tk', 'scaling', 1.25)  # todo: check tkinter autoscaling magic somewhere, windows 125% ui scale
    low_res = get_screen_res()[0] < 1600
    gui = PipelineGUI(root, low_res=low_res)


    def on_close():
        gui.shutdown()
        root.destroy()


    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
