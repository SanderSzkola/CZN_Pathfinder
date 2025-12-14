import tkinter as tk
import ttkbootstrap as tb
from PIL import Image, ImageTk
import numpy as np
import cv2

from calibrator import perform_calibration_exact, get_initial_params


class CalibrationPanel(tb.Toplevel):
    def __init__(
            self,
            parent,
            low_res: bool,
            scr,
            log=None
    ):
        super().__init__(parent)
        if scr is None:
            self.destroy()
            return
        self.parent = parent
        # self.low_res = low_res
        low_res = True  # do not need much space now, leave possibility later
        self.log = log

        if low_res:
            self.window_w = 1280
            self.window_h = 550
            self.map_w = 980
            self.map_h = 550
        else:
            self.window_w = 1600
            self.window_h = 500
            self.map_w = 1300
            self.map_h = 500

        self.geometry(f"{self.window_w}x{self.window_h}")
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

        self._img_tk = None
        self._build_ui()
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
        panel = tb.Frame(parent, width=300, height=self.window_h)
        panel.pack(side="left", fill="both")
        panel.pack_propagate(False)

        self._build_controls(panel)

    def _build_controls(self, parent):
        parent.pack_propagate(False)

        # Grid container
        grid = tb.Frame(parent)
        grid.pack(pady=15, anchor="n")

        grid.columnconfigure(0, weight=0)  # labels
        grid.columnconfigure(1, weight=0)  # fields

        row = 0

        # ----------------------------
        # Resolution
        # ----------------------------
        tb.Label(grid, text="Resolution:", anchor="w", width=14) \
            .grid(row=row, column=0, padx=(5, 8), pady=10, sticky="w")

        tb.Label(
            grid,
            text="Detected resolution from captured screenshot. Should be somewhere around chosen game resolution.\nTemplates res is 1920 x 1080",
            wraplength=260,
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
            wraplength=260,
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
            wraplength=260,
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
            text="Tweak scale and threshold until every node and modifier is correctly labeled.\nInitial values are likely close to ideal ones.",
            wraplength=260,
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

        tb.Button(
            btns,
            text="Recalibrate",
            width=18,
            bootstyle="warning",
            command=self._apply,
            padding=4
        ).pack(pady=4)

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

        tb.Button(col, text="▲", width=2, padding=1,
                  command=lambda: var.set(round(var.get() + step, 5))).pack()
        tb.Button(col, text="▼", width=2, padding=1,
                  command=lambda: var.set(round(var.get() - step, 5))).pack()

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
