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
from path_converter import get_path


class PipelineGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CZN Pathfinder")
        self.root.iconbitmap("Images/Icon.ico")
        self.root.geometry("1600x420")

        self.selected_folder = None
        self.last_map = None
        self.last_image = None
        self.last_path = None
        self.log_file_path = get_path("log_file.log")
        self.score_table = ScoreTable()
        self._delayed_pathfinder_id = None

        self._build_ui()
        self._load_initial_background()
        self.root.after(50, self._periodic_update)

    # ======================================================================
    # UI Construction
    # ======================================================================
    def _build_ui(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        self._build_left_image_panel(main_frame)
        self._build_right_panel(main_frame)

    def _build_left_image_panel(self, parent):
        panel = tk.Frame(parent, width=1190, height=420, bg="gray")
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self.image_label = tk.Label(panel, bg="black")
        self.image_label.pack(fill="both", expand=True)

    def _build_right_panel(self, parent):
        panel = tk.Frame(parent, width=410, height=420)
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self._build_log_display(panel)
        self._build_folder_section(panel)
        self._build_button_rows(panel)
        self._build_score_table(panel)

    def _build_log_display(self, parent):
        frame = tk.Frame(parent)
        frame.pack(fill="x")

        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.log_display = tk.Text(
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

    def _build_folder_section(self, parent):
        self.folder_label = tk.Label(parent, text="Folder: None", anchor="w")
        self.folder_label.pack(pady=5)

    def _build_button_rows(self, parent):
        row1 = tk.Frame(parent)
        row1.pack(pady=5, fill="x")

        tk.Button(row1, text="Choose Folder", width=18, command=self.choose_folder).pack(side="left", padx=2)
        tk.Button(row1, text="Start Automatic Scanner", width=18, command=self.start_automatic_pipeline).pack(
            side="left", padx=2)
        tk.Button(row1, text="Import Score Table", width=18, command=self.import_score_table).pack(side="left", padx=2)

        row2 = tk.Frame(parent)
        row2.pack(pady=10, fill="x")

        tk.Button(row2, text="Clear Folder", width=18, command=self.clear_folder).pack(side="left", padx=2)
        tk.Button(row2, text="Start Offline Scanner", width=18, command=self.start_offline_pipeline).pack(side="left",
                                                                                                          padx=2)
        tk.Button(row2, text="Export Score Table", width=18, command=self.export_score_table).pack(side="left", padx=2)

    def _build_score_table(self, parent):
        panel = tk.Frame(parent)
        panel.pack(fill="both")

        tk.Label(panel, text="Score Table", anchor="w").pack()

        self.score_vars = {}
        columns_frame = tk.Frame(panel)
        columns_frame.pack(fill="x")

        col_left = tk.Frame(columns_frame)
        col_right = tk.Frame(columns_frame)
        col_left.pack(side="left", fill="y")
        col_right.pack(side="left", fill="y")

        items = list(self.score_table.table.items())
        mid = (len(items) + 1) // 2

        for key, val in items[:mid]:
            self._create_score_row(col_left, key, val)

        for key, val in items[mid:]:
            self._create_score_row(col_right, key, val)

    def _create_score_row(self, parent, key, value):
        row = tk.Frame(parent)
        row.pack(fill="x")

        tk.Label(row, text=key, width=5, anchor="w").pack(side="left", padx=1)

        var = tk.IntVar(value=value)
        self.score_vars[key] = var

        tk.Scale(
            row,
            from_=-10,
            to=10,
            orient="horizontal",
            length=140,
            variable=var,
            command=lambda _, k=key: self.update_score_value(k),
            borderwidth=0,
            highlightthickness=0,
            sliderlength=10
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
            self.log_display.insert("end", line + "\n")
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
        self.display_image(img)

    # ======================================================================
    # Folder Management
    # ======================================================================
    def choose_folder(self):
        path = filedialog.askdirectory(initialdir=get_path())
        if path:
            self.selected_folder = path
            self.folder_label.config(text=f"Folder: {path}")

    def clear_folder(self):
        self.selected_folder = None
        self.folder_label.config(text="Folder: None")

    # ======================================================================
    # Pipeline Actions
    # ======================================================================
    def start_automatic_pipeline(self):
        if self.selected_folder:
            if os.listdir(self.selected_folder):
                self.log("Please select empty folder for auto scanning, scanner may get confused on unrelated files")
                return

        if not self.ask_continue_dialog():
            self.log("Scanning task cancelled.")
            return

        threading.Thread(target=self._run_auto_pipeline, daemon=True).start()

    def _run_auto_pipeline(self):
        try:
            self.log("Auto scanner started")
            m, path, img = run_pipeline(
                max_steps=30,
                save_folder=self.selected_folder,
                print_grid=False,
                log=self.log,
                score_table=self.score_table
            )
            self.last_map = m
            self.last_path = path
            self.display_image(img)
        except Exception as e:
            self.log(f"Pipeline error: {e}")

    def start_offline_pipeline(self):
        if not self.selected_folder:
            self.log("Select folder with screenshots first.")
            return

        threading.Thread(target=self._run_offline_pipeline, daemon=True).start()

    def _run_offline_pipeline(self):
        try:
            m, path, img = run_pipeline_offline(
                max_steps=30,
                save_folder=self.selected_folder,
                print_grid=False,
                log=self.log,
                score_table=self.score_table
            )
            self.last_map = m
            self.last_path = path
            self.display_image(img)
        except Exception as e:
            self.log(f"Pipeline error: {e}")

    def rerun_pathfinder(self):
        if not self.last_map:
            self.log("No map loaded.")
            return

        self.log("Re-running pathfinder")

        def task():
            try:
                path, score = run_pathfinder(self.last_map, self.score_table)
                self.last_path = path
                img = draw_map(self.last_map, path)
                self.display_image(img)
            except Exception as e:
                self.log(f"Re-run error: {e}")

        threading.Thread(target=task, daemon=True).start()

    # ======================================================================
    # Score Table Operations
    # ======================================================================
    def update_score_value(self, key):
        self.score_table.table[key] = self.score_vars[key].get()

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
                    self.score_vars[key].set(val)

            self.log("ScoreTable imported.")

            if self.last_map is not None:
                if self._delayed_pathfinder_id is not None:
                    self.root.after_cancel(self._delayed_pathfinder_id)
                self._delayed_pathfinder_id = self.root.after(500, self.rerun_pathfinder)

        except Exception as e:
            self.log(f"Import error: {e}")

    def export_score_table(self):
        try:
            ScoreTable.export(self.score_table)
            self.log("ScoreTable exported.")
        except Exception as e:
            self.log(f"Export error: {e}")

    # ======================================================================
    # Dialogs
    # ======================================================================
    def ask_continue_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Confirm Action")
        win.grab_set()
        win.transient(self.root)

        text = (
            "You are about to start the scanning process.\n"
            "IT MOVES YOUR REAL MOUSE, this is intended behavior.\n"
            "Make sure alt-tab leads to the game, the game has minimap opened and in default position (not moved left/right).\n"
            "Do not touch mouse or keyboard until scanning is done.\n\n"
            "If the scanner behaves incorrectly, quickly move mouse to top left screen corner to stop it.\n"
            "If the script failed to switch window, alt-tab to game and back, then start again."
        )

        tk.Label(win, text=text).pack(padx=20, pady=15)

        result = {"value": False}

        def confirm(_=None):
            result["value"] = True
            win.destroy()

        def cancel():
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)

        btn_ok = tk.Button(btn_frame, text="Continue", width=12, command=confirm)
        btn_ok.pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", width=12, command=cancel).pack(side="right", padx=5)

        btn_ok.focus_set()
        win.bind("<Return>", confirm)
        win.bind("<Escape>", lambda _: cancel())

        self._center_popup(win)
        self.root.wait_window(win)
        return result["value"]

    def _center_popup(self, win):
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - win.winfo_reqwidth() // 2
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - win.winfo_reqheight() // 2
        win.geometry(f"+{x}+{y}")

    # ======================================================================
    # Periodic UI Update
    # ======================================================================
    def _periodic_update(self):
        self.root.after(50, self._periodic_update)


# ======================================================================
# Main
# ======================================================================

if __name__ == "__main__":
    root = tk.Tk()
    PipelineGUI(root)
    root.mainloop()
