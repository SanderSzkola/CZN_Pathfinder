# gui_calibrator.py
import tkinter as tk
import ttkbootstrap as tb
from PIL import Image, ImageTk
import numpy as np
from pathlib import Path
import cv2

from data.settings import Settings
from front.grabber import mock_screenshot
from front.unified_preview import UnifiedPreview
from processing.calibrator import perform_or_validate_calibration, get_initial_params
from processing.detect_connections import detect_connections
from processing.detect_nodes import detect_nodes
from processing.template_library import TemplateLibrary
from utils.path_converter import get_path


class CalibrationPanel(tb.Toplevel):
    def __init__(
            self,
            parent,
            low_res: bool,
            scr,
            folder: str | Path | None,
            log=None
    ):
        super().__init__(parent)
        self.log = log

        self._from_folder = False
        self.folder = None
        self._image_files = []
        self._current_index = 0

        # try folder-based calibration
        if scr is None or getattr(scr, "size", (0, 0))[0] == 0:
            if folder is None:
                self.log("Calibrator: No image source available")
                self.destroy()
                return
            self.folder = Path(folder)
            if not self.folder.exists() or not self.folder.is_dir():
                self.log(f"Calibrator: Invalid folder {self.folder}")
                self.destroy()
                return
            self._image_files = self.scan_folder(self.folder)
            if not self._image_files:
                self.log(f"Calibrator: No valid images in {self.folder}")
                self.destroy()
                return
            self._from_folder = True
            self._current_index = 0
            scr = self._load_image_at_index(0)
            if scr is None:
                self.log("Calibrator: Failed to load image from folder")
                self.destroy()
                return

        # rest of init
        # self.low_res = low_res
        low_res = True  # do not need much space now, leave possibility later

        if low_res:
            self.window_w = 1270
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
        self.scr_original_pil = self._to_pil(scr)
        self.scr_display_pil = self.scr_original_pil.copy()
        self.preview = None
        self.templates = TemplateLibrary()

        screenshot_scale, initial_scale, initial_threshold, w, h = get_initial_params(scr)
        self.res_w = tk.IntVar(value=w)
        self.res_h = tk.IntVar(value=h)
        self.templates_scale = tk.DoubleVar(value=initial_scale)
        self.threshold = tk.DoubleVar(value=initial_threshold)
        self.screenshot_scale = screenshot_scale
        Settings.template_scale = initial_scale
        Settings.screenshot_scale = screenshot_scale
        self.auto_recalibrate = tk.BooleanVar(value=True)
        self._suspend_autocal = False

        self._img_tk = None
        self._build_ui()
        self.templates_scale.trace_add("write", self._on_param_change)
        self.threshold.trace_add("write", self._on_param_change)
        self._reload_preview()
        self._update_map_label()
        self._update_nav_buttons()

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
        content = tb.Frame(panel)
        content.pack(expand=True)

        self._map_label = tb.Label(
            content,
            anchor="center",
            justify="center",
            font=("Segoe UI", 12)
        )
        self._map_label.pack(fill="x", pady=(0, 4))
        self.image_label = tb.Label(
            content,
            anchor="center"
        )
        self.image_label.pack()

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
        self._build_controls(tab_calibration)

        tab_overlays = tb.Frame(notebook)
        notebook.add(tab_overlays, text="Overlays")
        self._build_overlays_panel(tab_overlays)

        tab_folders = tb.Frame(notebook)
        notebook.add(tab_folders, text="Folders")
        self._build_folders_panel(tab_folders)

        tab_help = tb.Frame(notebook)
        notebook.add(tab_help, text="Help")
        self._build_help_panel(tab_help)

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
            style="info"
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
            style="info"
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

        tb.Entry(scale_frame, textvariable=self.templates_scale, width=8, ).pack(side="left")
        self._spin_buttons(scale_frame, self.templates_scale, 0.005)

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
            style="info"
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
            text="Tweak TEMPLATE SCALE and THRESHOLD until every node and modifier is correctly labeled."
                 "\nInitial values are likely close to ideal ones.",
            wraplength=self.right_panel_width - 40,
            justify="left",
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

        self._btn_prev = tb.Button(
            recal_row,
            text="<",
            width=3,
            command=self._prev_image
        )
        self._btn_prev.pack(side="left", padx=4)

        tb.Button(
            recal_row,
            text="Recalibrate",
            width=18,
            bootstyle="warning",
            command=self._apply,
            padding=4
        ).pack(side="left")

        self._btn_next = tb.Button(
            recal_row,
            text=">",
            width=3,
            command=self._next_image
        )
        self._btn_next.pack(side="left", padx=4)

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

    def _build_overlays_panel(self, parent):
        parent.pack_propagate(False)
        container = tb.Frame(parent)
        container.pack(fill="both", expand=True, pady=10)

        self._preview_vars = {
            "dim": tk.BooleanVar(value=Settings.preview_dim_background),
            "corridors": tk.BooleanVar(value=Settings.preview_draw_corridors),
            "nodes_text": tk.BooleanVar(value=Settings.preview_draw_nodes_text),
            "fringe": tk.BooleanVar(value=Settings.preview_draw_fringe_marks),
            "icons": tk.BooleanVar(value=Settings.preview_draw_node_icons),
            "trim": tk.BooleanVar(value=Settings.preview_draw_trim_overlay),
        }

        preview_box = tb.Labelframe(
            container,
            text="Preview overlays",
            padding=8
        )
        preview_box.pack(fill="x", padx=10, pady=(0, 10))

        def add_cb(text, var, setting_attr):
            def on_change():
                setattr(Settings, setting_attr, var.get())
                Settings.save()
                if self.preview is not None:
                    self.preview.apply_settings()
                    self.scr_display_pil = self._to_pil(self.preview.render())
                    self._reload_preview()

            tb.Checkbutton(
                preview_box,
                text=text,
                variable=var,
                command=on_change
            ).pack(anchor="w")

        add_cb("Dim background", self._preview_vars["dim"], "preview_dim_background")
        add_cb("Draw corridors", self._preview_vars["corridors"], "preview_draw_corridors")
        add_cb("Draw node text", self._preview_vars["nodes_text"], "preview_draw_nodes_text")
        add_cb("Draw node icons", self._preview_vars["icons"], "preview_draw_node_icons")
        add_cb("Draw fringe marks", self._preview_vars["fringe"], "preview_draw_fringe_marks")
        add_cb("Draw trim overlay", self._preview_vars["trim"], "preview_draw_trim_overlay")

    def _build_folders_panel(self, parent):
        parent.pack_propagate(False)
        container = tb.Frame(parent)
        container.pack(fill="both", expand=True, pady=10)

        self._folders = self.list_valid_image_folders()
        self._folder_var = tk.StringVar()
        folder_box = tb.Labelframe(
            container,
            text="Image folders",
            padding=8
        )
        folder_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._folder_list = tk.Listbox(
            folder_box,
            height=18,
            exportselection=False,
            relief="flat",
            highlightthickness=0
        )
        self._folder_list.pack(fill="both", expand=True)
        self._folder_list.config(
            bg=self.style.colors.bg,
            fg=self.style.colors.fg,
            selectbackground=self.style.colors.primary,
        )

        for path, selectable, indent in self._folders:
            label = f"{'    ' * indent}{path.name}"
            self._folder_list.insert("end", label)

        self._folder_list.bind("<<ListboxSelect>>", self._on_folder_selected)
        if not self._folders:
            self._folder_list.insert("end", "No valid image folders found")
            self._folder_list.config(state="disabled")

    def _build_help_panel(self, parent):
        parent.pack_propagate(False)

        container = tb.Frame(parent)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        tb.Label(
            container,
            text="Calibration Help",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 8))

        help_text = (
            "General workflow:\n"
            "1. Open calibration panel, optionally select saved folder and image.\n"
            "2. Lower THRESHOLD a few times until all nodes are labeled.\n"
            "3. If some node refuses to be labeled, try changing TEMPLATE SCALE.\n"
            "4. Confirm that every existing path between labeled nodes is highlighted.\n"
            "\n"
            "Goal:\n"
            "Every node and modifier inside central, non-crossed zone should be detected and correctly labeled.\n"
            "\n"
            "Tips:\n"
            "- Template scale is resolution-dependent; initial values are usually close.\n"
            "- If nodes are missing, lower the threshold. Lowering it too much may affect performance. \n"
            "- If extra modifiers appear, increase the threshold.\n"
            "- Yellow crossed area is excluded from detection due to game's ui elements potentially overlapping with nodes.\n"
            "- Blue crossed area is a safety margin, nodes located there are hard to read, so they are discarded, marked by X."
            " Modifiers are processed normally.\n"
            "\n"
            "Legend:\n"
            "NO - normal fight\n"
            "EL - elite fight\n"
            "EV - random event\n"
            "RE - rest\n"
            "\n"
            "**SH - shop\n"
            "**OR - chaos orb / aura monster / harder monster\n"
            "**TU - dimensional tunnel / s1+s2 unique event\n"
            "**ME - memory of embers / s2 unique event\n"
            "**PE - persona / s3 unique fight\n"
            "**DI - director's script / s3 unique event\n"
            "**DE - desire / s4 unique modifier\n"
        )

        tb.Label(
            container,
            text=help_text,
            justify="left",
            anchor="nw",
            wraplength=self.right_panel_width - 40
        ).pack(fill="both", expand=True)

    # ==================================================================
    # Preview image
    # ==================================================================
    def _reload_preview(self):

        self.scr_display_pil = self._fit_image(self.scr_display_pil, self.map_w, self.map_h)
        self._img_tk = ImageTk.PhotoImage(self.scr_display_pil)
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
    def scan_folder(folder: Path):
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
            if CalibrationPanel.scan_folder(p):
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
        base_np = cv2.cvtColor(np.array(self.scr_original_pil), cv2.COLOR_RGB2BGR)
        if self.preview is None:
            self.preview = UnifiedPreview(base_np)
        else:
            self.preview.base_img = base_np
        self.preview.scale = self.templates_scale.get() / self.screenshot_scale
        self.templates.scale_templates(self.templates_scale.get())
        nodes = detect_nodes(
            self.preview.base_img,
            self.templates,
            screenshot_scale=self.screenshot_scale,
            threshold=self.threshold.get(),
            filter_fringe=False
        )
        nodes_filtered = [n for n in nodes if not n.is_fringe]
        _, edges, corridor_debug = detect_connections(self.preview.base_img, templates=self.templates,
                                                      nodes=nodes_filtered)
        perform_or_validate_calibration(
            screenshot=self.scr_original_pil,
            nodes=nodes_filtered,
            log=self.log,
            template_scale=self.templates_scale.get(),
            threshold=self.threshold.get(),
        )
        self.preview.set_nodes(nodes)
        self.preview.set_connections(edges, corridor_debug)
        self.preview.apply_settings()

        self.scr_display_pil = self._to_pil(self.preview.render())
        self._reload_preview()

    def _show_original(self):
        self.scr_display_pil = self.scr_original_pil
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
            self.scr_original_pil = scr.copy()
            self.scr_display_pil = scr.copy()
            self._apply()
            self._update_map_label()

    def _next_image(self):
        if self._current_index >= len(self._image_files) - 1:
            return
        self._current_index += 1
        scr = self._load_image_at_index(self._current_index)
        if scr is not None:
            self.scr_original_pil = scr.copy()
            self.scr_display_pil = scr.copy()
            self._apply()
            self._update_map_label()

    def _on_folder_selected(self, event):
        sel = self._folder_list.curselection()
        if not sel:
            return

        idx = sel[0]
        path, selectable, _ = self._folders[idx]
        if not selectable:
            return  # parent folder → do nothing

        self.folder = path
        self._image_files = self.scan_folder(path)
        self._current_index = 0

        if not self._image_files:
            return
        scr = self._load_image_at_index(0)
        if scr is None:
            return

        self._suspend_autocal = True
        self.scr_original_pil = scr.copy()
        self.scr_display_pil = scr.copy()

        # Recalculate template scale and resolution as if reopening window with normal screenshot
        screenshot_scale, initial_scale, initial_threshold, w, h = get_initial_params(scr)
        self.res_w.set(w)
        self.res_h.set(h)
        self.templates_scale.set(initial_scale)
        self.threshold.set(initial_threshold)
        self.screenshot_scale = screenshot_scale
        Settings.template_scale = initial_scale
        Settings.screenshot_scale = screenshot_scale
        # do NOT save unconfirmed values, that's decided inside _apply
        self._suspend_autocal = False

        self._apply()
        self._from_folder = True
        self._update_map_label()
        self._update_nav_buttons()

    def _update_map_label(self):
        if self._from_folder:
            img = self._image_files[self._current_index].name
            folder = self.folder.name
            text = f"Loaded image: {img} from {folder} folder"
        else:
            text = "Loaded image: captured from game"

        self._map_label.config(text=text)

    def _update_nav_buttons(self):
        state = "normal" if self._from_folder else "disabled"
        self._btn_prev.config(state=state)
        self._btn_next.config(state=state)
