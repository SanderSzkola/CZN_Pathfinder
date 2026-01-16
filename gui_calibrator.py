# gui_calibrator.py
import tkinter as tk
import ttkbootstrap as tb
from PIL import Image, ImageTk
import numpy as np
from pathlib import Path
import cv2
import re

from calibrator import perform_calibration_exact, get_initial_params
from settings import Settings
from path_converter import get_path
from grabber import mock_screenshot


class CalibrationPanel(tb.Toplevel):
    def __init__(
            self,
            parent,
            low_res: bool,
            scr,
            folder: str,
            log=None
    ):
        super().__init__(parent)
        self.log = log

        # image and folder
        if (scr is None or scr.size[0] == 0) and not Settings.testmode:
            self.destroy()
            return

        if Settings.testmode and (scr is None or scr.size[0] == 0):
            self.folder = Path(folder)
            if not self.folder.exists() or not self.folder.is_dir():
                log(f"Calibrator: Wrong folder path {self.folder}")
                self.destroy()
                return

            self._image_files = self._scan_folder(self.folder)
            self._current_index = 0

            if not self._image_files:
                log(f"Calibrator: No images in {self.folder}")
                self.destroy()
                return

            log(f"Calibrator: Loading test image from {self.folder}")
            scr = self._load_image_at_index(0)
            if scr is None:
                log(f"Calibrator: Loading test image from {self.folder} failed somehow")
                self.destroy()
                return

        # rest of init
        self.parent = parent
        # self.low_res = low_res
        low_res = True  # do not need much space now, leave possibility later

        if low_res:
            self.window_w = 1280
            self.window_h = 600
            self.map_w = 900
            self.map_h = 600
        else:
            self.window_w = 1600
            self.window_h = 500
            self.map_w = 1300
            self.map_h = 500

        self.right_panel_width = self.window_w - self.map_w
        x = parent.winfo_x()
        y = parent.winfo_y()
        self.geometry(f"{self.window_w}x{self.window_h}+{x}+{y}")
        self.title("Calibration")
        self.transient(parent)
        self.grab_set()
        self.scr = scr
        self.scr_original = scr.copy()

        _, initial_scale, initial_threshold, w, h = get_initial_params(None, scr)
        self.res_w = tk.IntVar(value=w)
        self.res_h = tk.IntVar(value=h)
        self.scale = tk.DoubleVar(value=initial_scale)
        self.threshold = tk.DoubleVar(value=initial_threshold)
        self.auto_recalibrate = tk.BooleanVar(value=True)
        self._suspend_autocal = False

        self._img_tk = None
        self._build_ui()
        self.scale.trace_add("write", self._on_param_change)
        self.threshold.trace_add("write", self._on_param_change)
        self._reload_preview()

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self):
        main = tb.Frame(self)
        main.pack(fill="both", expand=True)

        self._build_map_panel(main)
        self._build_right_panel(main)

    def _build_map_panel(self, parent):
        panel = tb.Frame(parent, width=self.map_w, height=self.map_h)
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self.image_label = tb.Label(panel, anchor="center")
        self.image_label.pack(fill="both", expand=True)

    def _build_right_panel(self, parent):
        panel = tb.Frame(parent, width=self.right_panel_width, height=self.window_h)
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self._build_tabs(panel)

    def _build_tabs(self, parent):
        notebook = tb.Notebook(parent, bootstyle="secondary")
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        tab_calibration = tb.Frame(notebook)
        notebook.add(tab_calibration, text="Calibration")

        tab_other = tb.Frame(notebook)
        notebook.add(tab_other, text="Other")

        self._build_controls(tab_calibration)
        self._build_other_panel(tab_other)

    def _build_controls(self, parent):
        # Grid container
        grid = tb.Frame(parent)
        grid.pack(pady=15, anchor="n")

        grid.columnconfigure(0, weight=0)  # labels
        grid.columnconfigure(1, weight=0)  # fields

        row = 0

        # ----------------------------
        # Auto recalibrate
        # ----------------------------
        tb.Checkbutton(
            grid,
            text="Auto recalibrate on value change",
            variable=self.auto_recalibrate,
        ).grid(
            row=row,
            column=0,
            columnspan=2,
            padx=10,
            pady=(0, 10),
            sticky="w"
        )

        row += 1

        # ----------------------------
        # Resolution
        # ----------------------------
        tb.Label(grid, text="Resolution:", anchor="w", width=14) \
            .grid(row=row, column=0, padx=(5, 8), pady=10, sticky="w")

        tb.Label(
            grid,
            text="Detected resolution from captured screenshot. Should be somewhere around chosen game resolution.\nTemplates res is 1920 x 1080",
            wraplength=self.right_panel_width - 40,
            justify="left",
        ).grid(
            row=row + 1,
            column=0,
            columnspan=2,
            padx=10,
            pady=(0, 16),
            sticky="w"
        )

        res_frame = tb.Frame(grid)
        res_frame.grid(row=row, column=1, sticky="w")

        tb.Entry(res_frame, textvariable=self.res_w, width=7, state="disabled").pack(side="left")
        tb.Label(res_frame, text=" x ").pack(side="left")
        tb.Entry(res_frame, textvariable=self.res_h, width=7, state="disabled").pack(side="left")

        row += 2

        # ----------------------------
        # Template scale
        # ----------------------------
        tb.Label(grid, text="Template scale:", anchor="w", width=14) \
            .grid(row=row, column=0, padx=(5, 8), pady=10, sticky="w")

        tb.Label(
            grid,
            text="Rescale multiplier for templates. Halved if over 1.\nExample: If your res is 1440p, halved its 720p,\n720 / 1080 ~ 0.667",
            wraplength=self.right_panel_width - 40,
            justify="left",
        ).grid(
            row=row + 1,
            column=0,
            columnspan=2,
            padx=10,
            pady=(0, 16),
            sticky="w"
        )

        scale_frame = tb.Frame(grid)
        scale_frame.grid(row=row, column=1, sticky="w")

        tb.Entry(scale_frame, textvariable=self.scale, width=8, ).pack(side="left")
        self._spin_buttons(scale_frame, self.scale, 0.005)

        row += 2

        # ----------------------------
        # Threshold
        # ----------------------------
        tb.Label(grid, text="Threshold:", anchor="w", width=14) \
            .grid(row=row, column=0, padx=(5, 8), pady=10, sticky="w")

        tb.Label(
            grid,
            text="How accurate a valid match should be. Too high and it skips nodes, too low and it hallucinates them.",
            wraplength=self.right_panel_width - 40,
            justify="left",
        ).grid(
            row=row + 1,
            column=0,
            columnspan=2,
            padx=10,
            pady=(0, 16),
            sticky="w"
        )

        thr_frame = tb.Frame(grid)
        thr_frame.grid(row=row, column=1, sticky="w")

        tb.Entry(thr_frame, textvariable=self.threshold, width=8).pack(side="left")
        self._spin_buttons(thr_frame, self.threshold, 0.005)

        tb.Label(
            grid,
            text="Tweak TEMPLATE SCALE and THRESHOLD until every node and modifier is correctly labeled.\nInitial values are likely close to ideal ones.",
            wraplength=self.right_panel_width - 40,
            justify="left",
            bootstyle="info"
        ).grid(
            row=row + 2,
            column=0,
            columnspan=2,
            padx=10,
            pady=(0, 5),
            sticky="w"
        )

        # ----------------------------
        # Buttons
        # ----------------------------
        btns = tb.Frame(parent)
        btns.pack(pady=5)

        recal_row = tb.Frame(btns)
        recal_row.pack(pady=4)

        if Settings.testmode and hasattr(self, "_image_files"):
            tb.Button(
                recal_row,
                text="<",
                width=3,
                command=self._prev_image
            ).pack(side="left", padx=4)

        tb.Button(
            recal_row,
            text="Recalibrate",
            width=18,
            bootstyle="warning",
            command=self._apply,
            padding=4
        ).pack(side="left")

        if Settings.testmode and hasattr(self, "_image_files"):
            tb.Button(
                recal_row,
                text=">",
                width=3,
                command=self._next_image
            ).pack(side="left", padx=4)

        tb.Button(
            btns,
            text="Show original",
            width=18,
            command=self._show_original,
            padding=4
        ).pack(pady=4)

        tb.Button(
            btns,
            text="Close",
            width=18,
            command=self.destroy,
            padding=4
        ).pack(pady=4)

    def _spin_buttons(self, parent, var, step):
        col = tb.Frame(parent)
        col.pack(side="left", padx=2)

        def inc():
            self._suspend_autocal = True
            var.set(round(var.get() + step, 5))
            self._suspend_autocal = False
            if self.auto_recalibrate.get():
                self._apply()

        def dec():
            self._suspend_autocal = True
            var.set(round(var.get() - step, 5))
            self._suspend_autocal = False
            if self.auto_recalibrate.get():
                self._apply()

        tb.Button(col, text="▲", width=2, padding=0, command=inc).pack()
        tb.Button(col, text="▼", width=2, padding=0, command=dec).pack()

    def _build_other_panel(self, parent):
        parent.pack_propagate(False)

        self._folders = self.list_valid_image_folders()
        self._folder_var = tk.StringVar()

        container = tb.Frame(parent)
        container.pack(fill="both", expand=True, pady=10)

        tb.Label(
            container,
            text="Image folders",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self._folder_list = tk.Listbox(
            container,
            height=18,
            exportselection=False
        )
        self._folder_list.pack(fill="both", expand=True, padx=10)

        for path, selectable, indent in self._folders:
            label = f"{'  ' * indent}{path.name}"
            self._folder_list.insert("end", label)

        self._folder_list.bind("<<ListboxSelect>>", self._on_folder_selected)

    # ==================================================================
    # Preview image
    # ==================================================================
    def _reload_preview(self):

        self.scr = self._fit_image(self.scr, self.map_w, self.map_h)
        self._img_tk = ImageTk.PhotoImage(self.scr)
        self.image_label.config(image=self._img_tk)

    @staticmethod
    def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
        scale = min(max_w / img.width, max_h / img.height)
        w = int(img.width * scale)
        h = int(img.height * scale)
        return img.resize((w, h), Image.Resampling.BILINEAR)

    @staticmethod
    def _to_pil(img):
        if isinstance(img, Image.Image):
            return img

        if isinstance(img, np.ndarray):
            if img.ndim == 2:
                return Image.fromarray(img, "L")

            if img.ndim == 3:
                if img.shape[2] == 3:
                    # BGR -> RGB
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    return Image.fromarray(img, "RGB")

                if img.shape[2] == 4:
                    # BGRA -> RGBA
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                    return Image.fromarray(img, "RGBA")

        raise TypeError(f"Unsupported image type: {type(img)}")

    @staticmethod
    def _scan_folder(folder: Path):
        files = []

        for f in folder.iterdir():
            if not f.is_file():
                continue
            if '.' not in f.name:
                continue

            name, ext = f.name.rsplit('.', 1)

            if name.endswith("preview"):
                continue
            if name.startswith("merged"):
                continue
            if not ext.lower().endswith("png"):
                continue
            if not CalibrationPanel._is_image_height_valid(f, 700):
                continue

            files.append(f)

        files.sort()
        return files

    @staticmethod
    def _is_image_height_valid(path: Path, min_h: int = 700) -> bool:
        try:
            with Image.open(path) as img:
                return img.height > min_h
        except Exception:
            return False

    def _load_image_at_index(self, idx):
        if idx < 0 or idx >= len(self._image_files):
            return None
        return mock_screenshot(str(self._image_files[idx]))

    def list_valid_image_folders(self):
        base = Path(get_path())
        valid_folders = []
        for p in base.rglob("*"):
            if not p.is_dir():
                continue
            if CalibrationPanel._scan_folder(p):
                valid_folders.append(p)

        parents = {}
        for f in valid_folders:
            parents.setdefault(f.parent, []).append(f)
        entries = []
        for parent in sorted(parents.keys(), key=lambda p: p.as_posix().lower()):
            entries.append((parent, False, 0))
            children = sorted(parents[parent], key=lambda p: p.name.lower())
            for child in children:
                entries.append((child, True, 1))

        return entries

    # ==================================================================
    # Actions
    # ==================================================================
    def _apply(self):
        _, _, src_tmp = perform_calibration_exact(
            screenshot=self.scr_original,
            log=self.log,
            template_scale=self.scale.get(),
            threshold=self.threshold.get(),
        )
        self.scr = self._to_pil(src_tmp)
        self._reload_preview()

    def _show_original(self):
        self.scr = self.scr_original
        self._reload_preview()

    def _on_param_change(self, *_):
        if self._suspend_autocal:
            return
        if self.auto_recalibrate.get():
            self._apply()

    def _prev_image(self):
        if self._current_index <= 0:
            return
        self._current_index -= 1
        scr = self._load_image_at_index(self._current_index)
        if scr is not None:
            self.scr_original = scr
            self.scr = scr
            self._reload_preview()
            self._apply()

    def _next_image(self):
        if self._current_index >= len(self._image_files) - 1:
            return
        self._current_index += 1
        scr = self._load_image_at_index(self._current_index)
        if scr is not None:
            self.scr_original = scr
            self.scr = scr
            self._reload_preview()
            self._apply()

    def _on_folder_selected(self, event):
        sel = self._folder_list.curselection()
        if not sel:
            return

        idx = sel[0]
        path, selectable, _ = self._folders[idx]
        if not selectable:
            return  # parent folder → do nothing

        self.folder = path
        self._image_files = self._scan_folder(path)
        self._current_index = 0

        if not self._image_files:
            return
        scr = self._load_image_at_index(0)
        if scr is None:
            return

        self._suspend_autocal = True
        self.scr_original = scr
        self.scr = scr
        self._reload_preview()
        # Recalculate template scale and resolution as if reopening window with normal screenshot
        _, initial_scale, initial_threshold, w, h = get_initial_params(None, scr)
        self.res_w.set(w)
        self.res_h.set(h)
        self.scale.set(initial_scale)
        self.threshold.set(initial_threshold)
        self._suspend_autocal = False

        self._apply()
