import os
import threading
import tkinter as tk
from tkinter import filedialog
import numpy as np
from PIL import Image, ImageTk

from pipeline import run_pipeline, run_pipeline_offline
from pathfinder import run_pathfinder
from drawer import draw_map
from score_table import ScoreTable


class PipelineGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CZN Pathfinder")

        # State
        self.selected_folder = None
        self.last_map = None
        self.last_image = None
        self.last_path = None
        self.log_buffer = []
        self.log_file_path = os.path.join(os.getcwd(), "pipeline_gui.log")
        self.score_table = ScoreTable()
        self._pathfinder_task_id = None

        # Queue is not required; we push logs directly into buffer
        # GUI polls every 50 ms to refresh

        self.root.geometry("1600x420")

        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        # Left panel: image preview (1190x420)
        self.left_panel = tk.Frame(main_frame, width=1190, height=420, bg="gray")
        self.left_panel.pack(side="left", fill="both", expand=False)
        self.left_panel.pack_propagate(False)

        self.image_label = tk.Label(self.left_panel, bg="black")
        self.image_label.pack(fill="both", expand=True)

        # Right panel: controls (410x420)
        self.right_panel = tk.Frame(main_frame, width=410, height=420)
        self.right_panel.pack(side="left", fill="both", expand=False)
        self.right_panel.pack_propagate(False)

        # Log display (3 last lines)
        self.log_display = tk.Text(
            self.right_panel,
            width=40,
            height=5,
            wrap="word",
            state="disabled",
            cursor="arrow"
        )
        self.log_display.pack(pady=0, fill="x")
        self.log_lines = []
        self.log_file_path = os.path.join(os.getcwd(), "pipeline_gui.log")

        # Folder selection
        self.folder_label = tk.Label(self.right_panel, text="Folder: None", anchor="w")
        self.folder_label.pack(pady=5)

        # ----- Row 1 -----
        button_row_1 = tk.Frame(self.right_panel)
        button_row_1.pack(pady=5, fill="x")

        btn_sel = tk.Button(button_row_1, text="Choose Folder", command=self.choose_folder, width=18)
        btn_sel.pack(side="left", padx=2)

        btn_real = tk.Button(button_row_1, text="Start Real Scanner", command=self.start_real_pipeline, width=18)
        btn_real.pack(side="left", padx=2)

        btn_import = tk.Button(
            button_row_1,
            text="Import Score Table",
            width=18,
            command=self.import_score_table
        )
        btn_import.pack(side="left", padx=2)

        # ----- Row 2: Action buttons -----
        button_row_2 = tk.Frame(self.right_panel)
        button_row_2.pack(pady=10, fill="x")

        btn_clear = tk.Button(button_row_2, text="Clear Folder", command=self.clear_folder, width=18)
        btn_clear.pack(side="left", padx=2)

        btn_offline = tk.Button(button_row_2, text="Start Offline Scanner", command=self.start_offline_pipeline, width=18)
        btn_offline.pack(side="left", padx=2)

        btn_export = tk.Button(
            button_row_2,
            text="Export Score Table",
            width=18,
            command=self.export_score_table
        )
        btn_export.pack(side="left", padx=2)

        # ----- Score Panel -----
        self.score_panel = tk.Frame(self.right_panel)
        self.score_panel.pack(pady=2, fill="both", expand=False)

        tk.Label(self.score_panel, text="Score Table", anchor="w").pack(pady=0)

        self.score_vars = {}

        # two-column container
        columns_frame = tk.Frame(self.score_panel)
        columns_frame.pack(fill="x")

        left_col = tk.Frame(columns_frame)
        right_col = tk.Frame(columns_frame)

        left_col.pack(side="left", fill="y", padx=1)
        right_col.pack(side="left", fill="y", padx=1)

        # split items
        items = list(self.score_table.table.items())
        total = len(items)
        mid = (total + 1) // 2

        col1_items = items[:mid]
        col2_items = items[mid:]

        def create_row(parent, key, val):
            row = tk.Frame(parent)
            row.pack(fill="x", pady=0)

            tk.Label(row, text=key, width=5, anchor="w").pack(side="left", padx=1)

            var = tk.IntVar(value=val)
            self.score_vars[key] = var

            scale = tk.Scale(
                row,
                from_=-10,
                to=10,
                orient="horizontal",
                length=140,
                variable=var,
                command=lambda _=None, k=key: self.update_score_table(k),
                borderwidth=0,
                highlightthickness=0,
                sliderlength=10
            )
            scale.pack(side="left", padx=1)

        # build both columns
        for key, val in col1_items:
            create_row(left_col, key, val)

        for key, val in col2_items:
            create_row(right_col, key, val)

        # Load background image
        img = Image.open("example_map.png")
        self.display_image(img)

        # Poll UI updates
        self.root.after(50, self.update_ui)

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------
    def log(self, msg: str):
        """
        Thread-safe: can be called from background threads.
        Appends full message to log file; schedules a main-thread UI update for the last 3 lines.
        """
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"

        # write full history to file (safe from any thread)
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

        # maintain last-3-lines buffer (in-memory)
        self.log_lines.append(line)
        if len(self.log_lines) > 3:
            self.log_lines = self.log_lines[-3:]

        # schedule UI update on main thread
        try:
            self.root.after(0, self._refresh_log_display)
        except Exception:
            # if root not available, ignore
            pass

    def _refresh_log_display(self):
        """Run on main thread only. Replace Text contents with current last-3-lines."""
        try:
            self.log_display.configure(state="normal")
            # replace entire widget contents with the last 3 lines
            self.log_display.delete("1.0", "end")
            if self.log_lines:
                self.log_display.insert("1.0", "\n".join(self.log_lines) + "\n")
            self.log_display.configure(state="disabled")
            self.log_display.see("end")
        except tk.TclError:
            # widget destroyed or not yet initialized
            pass

    def update_ui(self):
        # do other UI updates here (image updates, progress, etc.)
        # DO NOT touch the log_display here.
        self.root.after(50, self.update_ui)

    # ------------------------------------------------------------
    # Folder selection
    # ------------------------------------------------------------
    def choose_folder(self):
        f = filedialog.askdirectory()
        if f:
            self.selected_folder = f
            self.folder_label.config(text=f"Folder: {f}")

    def clear_folder(self):
        self.selected_folder = None
        self.folder_label.config(text="Folder: None")

    # ------------------------------------------------------------
    # Image display
    # ------------------------------------------------------------
    def display_image(self, image_obj):
        try:
            # Case 1: file path
            if isinstance(image_obj, str):
                im = Image.open(image_obj)

            # Case 2: PIL Image
            elif isinstance(image_obj, Image.Image):
                im = image_obj

            # Case 3: NumPy array
            elif isinstance(image_obj, np.ndarray):
                arr = image_obj
                # Ensure uint8
                if arr.dtype != np.uint8:
                    arr = arr.astype(np.uint8)
                # Grayscale
                if arr.ndim == 2:
                    im = Image.fromarray(arr, mode="L")
                # Color image
                elif arr.ndim == 3:
                    # Common OpenCV pattern: BGR uint8
                    if arr.shape[2] == 3:
                        # BGR → RGB
                        arr = arr[:, :, ::-1]
                        im = Image.fromarray(arr, mode="RGB")
                    # RGBA but produced in BGR+A layout
                    elif arr.shape[2] == 4:
                        # BGRA → RGBA
                        arr = arr[:, :, [2, 1, 0, 3]]
                        im = Image.fromarray(arr, mode="RGBA")
                    else:
                        raise ValueError(f"Unsupported array shape: {arr.shape}")
                else:
                    raise ValueError(f"Unsupported array shape: {arr.shape}")

            # Case 4: tuple (common from some libraries)
            elif isinstance(image_obj, tuple):
                # Try interpreting first element as the image
                return self.display_image(image_obj[0])

            else:
                raise TypeError(f"Unsupported image type: {type(image_obj)}")

            # Tkinter display
            self.last_image = ImageTk.PhotoImage(im)
            self.image_label.config(image=self.last_image)

        except Exception as e:
            self.log(f"Image error: {e}")

    # ------------------------------------------------------------
    # Pipeline wrappers
    # ------------------------------------------------------------
    def start_real_pipeline(self):
        if self.selected_folder is not None:
            items = os.listdir(self.selected_folder)
            if len(items) != 0:
                self.log("Please select empty folder for real scanning, scanner may get confused on unrelated files")
                return
        if not self.ask_continue_dialog():
            self.log("Scanning task cancelled.")
            return

        def task():
            try:
                self.log("Scanner started")
                map_obj, path, img = run_pipeline(
                    max_steps=30,
                    save_folder=self.selected_folder,
                    print_grid=False,
                    log=self.log,
                    score_table=self.score_table
                )
                self.last_map = map_obj
                self.last_path = path
                self.display_image(img)

            except Exception as e:
                self.log(f"Pipeline error: {e}")

        threading.Thread(target=task, daemon=True).start()

    def start_offline_pipeline(self):
        if not self.selected_folder:
            self.log("Offline mode needs folder with map screenshots, please select it")
            return

        def task():
            try:
                map_obj, path, img = run_pipeline_offline(
                    max_steps=30,
                    save_folder=self.selected_folder,
                    print_grid=False,
                    log=self.log,
                    score_table=self.score_table
                )
                self.last_map = map_obj
                self.last_path = path
                self.display_image(img)

            except Exception as e:
                self.log(f"Pipeline error: {e}")

        threading.Thread(target=task, daemon=True).start()

    def rerun_pathfinder(self):
        if not self.last_map:
            self.log("No map loaded, run real or offline scanner first")
            return

        self.log("Re-running pathfinder")

        def task():
            try:
                path, score = run_pathfinder(self.last_map, self.score_table)
                self.last_path = path

                # redraw
                image = draw_map(self.last_map, path)
                self.display_image(image)

            except Exception as e:
                self.log(f"Re-run error: {e}")

        threading.Thread(target=task, daemon=True).start()

    def ask_continue_dialog(self):
        """Modal popup with Continue/Cancel, Continue is default. Returns True/False."""

        win = tk.Toplevel(self.root)
        win.title("Confirm Action")
        win.grab_set()  # modal window
        win.transient(self.root)

        (tk.Label(win, text=(
            "You are about to start the scanning process.\n"
            "IT MOVES YOUR REAL MOUSE, this is intended behavior.\n"
            "Make sure alt-tab leads to the game, the game has minimap opened and in default position (not moved left/right).\n"
            "Do not touch mouse or keyboard until scanning is done.\n\n"
            "If the scanner behaves incorrectly, quickly move mouse to top left screen corner to stop it.\n"
            "If the script failed to switch to the game window, alt-tab to game and back, then start again."))
         .pack(padx=20, pady=15))

        result = {"value": False}

        def do_continue(event=None):
            result["value"] = True
            win.destroy()

        def do_cancel():
            result["value"] = False
            win.destroy()

        # Buttons
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)

        btn_continue = tk.Button(btn_frame, text="Continue", width=12, command=do_continue)
        btn_continue.pack(side="left", padx=5)

        btn_cancel = tk.Button(btn_frame, text="Cancel", width=12, command=do_cancel)
        btn_cancel.pack(side="right", padx=5)

        # Make "Continue" default (Enter key)
        btn_continue.focus_set()
        win.bind("<Return>", do_continue)
        win.bind("<Escape>", lambda e: do_cancel())

        # Center popup relative to main window
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (win.winfo_reqwidth() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (win.winfo_reqheight() // 2)
        win.geometry(f"+{x}+{y}")

        # Wait until user closes dialog
        self.root.wait_window(win)

        return result["value"]

    def update_score_table(self, key: str):
        self.score_table.table[key] = self.score_vars[key].get()
        if self.last_map is not None:
            if self._pathfinder_task_id is not None:
                self.root.after_cancel(self._pathfinder_task_id)
            self._pathfinder_task_id = self.root.after(500, self.rerun_pathfinder)

    def import_score_table(self):
        try:
            st = ScoreTable.import_()  # loads ScoreTable.json
            self.score_table = st
            for key, val in self.score_table.table.items():
                if key in self.score_vars:
                    self.score_vars[key].set(val)

            self.log("ScoreTable imported.")
            if self.last_map is not None:
                if self._pathfinder_task_id is not None:
                    self.root.after_cancel(self._pathfinder_task_id)
                self._pathfinder_task_id = self.root.after(500, self.rerun_pathfinder)

        except Exception as e:
            self.log(f"Import error: {e}")

    def export_score_table(self):
        try:
            ScoreTable.export(self.score_table)  # saves to ScoreTable.json
            self.log("ScoreTable exported.")
        except Exception as e:
            self.log(f"Export error: {e}")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    gui = PipelineGUI(root)
    root.mainloop()
