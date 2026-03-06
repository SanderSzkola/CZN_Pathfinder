# gui_settings.py
import tkinter as tk
import ttkbootstrap as tb

from settings import Settings


class SettingsPanel(tb.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._vars = {}

        container = tb.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        self._build_tabs(container)
        self._build_buttons(container)
        self._center(parent)

    def _build_tabs(self, parent):
        notebook = tb.Notebook(parent, bootstyle="secondary")
        notebook.pack(fill="both", expand=True)

        tab_general = tb.Frame(notebook)
        notebook.add(tab_general, text="General")
        self._build_general_tab(tab_general)

        tab_temp = tb.Frame(notebook)
        notebook.add(tab_temp, text="Geometry")
        self._build_temp_tab(tab_temp)

    def _make_var(self, attr):
        val = getattr(Settings, attr)
        if isinstance(val, bool):
            return tk.BooleanVar(value=val)
        if isinstance(val, float):
            return tk.DoubleVar(value=val)
        if isinstance(val, int):
            return tk.IntVar(value=val)
        return tk.StringVar(value="" if val is None else val)

    def _add_field(self, parent, row, label, attr, disabled=False):
        var = self._make_var(attr)
        tb.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        entry = tb.Entry(parent, textvariable=var, width=25)
        if disabled:
            entry.configure(state="disabled")
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        self._vars[attr] = var
        return row + 1

    def _add_bool(self, parent, row, label, attr):
        var = self._make_var(attr)
        tb.Checkbutton(parent, text=label, variable=var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self._vars[attr] = var
        return row + 1

    def _add_explanation(self, parent, row, text):
        tb.Label(parent, text=text).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
        return row + 1

    def _add_separator(self, parent, row, pady=16):
        tb.Separator(parent, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=pady)
        return row + 1

    def _build_general_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        row = 0

        row = self._add_explanation(parent, row, "Any change requires script restart to take effect")
        row = self._add_field(parent, row, "Target app name", "target_app_name")
        row = self._add_bool(parent, row, "Request admin on startup", "request_admin")
        row = self._add_bool(parent, row, "Dark mode", "darkmode")
        row = self._add_bool(parent, row, "Auto import score table", "auto_import_score")
        row = self._add_bool(parent, row, "Testmode", "testmode")

        row = self._add_separator(parent, row)
        row = self._add_bool(parent, row, "Detect keyboard", "keyboard_input")
        row = self._add_explanation(parent, row, "Allows for calling scanners directly from the game")
        row = self._add_field(parent, row, "Run automatic scanner", "keyboard_input_autoscanner")
        row = self._add_field(parent, row, "Run halfauto scanner", "keyboard_input_halfautoscanner")
        row = self._add_explanation(parent, row, "Accepts letters and digits, alone or joined by + sign")

        row = self._add_separator(parent, row)
        row = self._add_bool(parent, row, "Check for update", "autoupdate")
        row = self._add_explanation(parent, row,
                                    "Checked once every day to not annoy GitHub\n"
                                    "The response is saved so you can be annoyed on every startup\n"
                                    "until you decide to update")
        row = self._add_field(parent, row, "Local version", "local_version", disabled=True)
        row = self._add_field(parent, row, "GitHub version", "remote_version", disabled=True)

    def _build_temp_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        row = 0
        row = self._add_explanation(parent, row, "Any change requires script restart to take effect")
        row = self._add_explanation(parent, row,
                                    "Those settings control how ui looks and behaves.\n"
                                    "Offset means how far the script window should be moved, relative to \n"
                                    "top left corner of display")

        row = self._add_field(parent, row, "Horizontal offset", "ui_window_offset_x")
        row = self._add_field(parent, row, "Horizontal offset in mini mode", "ui_window_offset_x_mini")
        row = self._add_field(parent, row, "Vertical offset", "ui_window_offset_y")
        row = self._add_field(parent, row, "Vertical offset in mini mode", "ui_window_offset_y_mini")
        row = self._add_field(parent, row, "Map image size % (20-100)", "ui_map_image_scale_normal")
        row = self._add_field(parent, row, "Minimap image size % (20-100)", "ui_map_image_scale_mini")
        row = self._add_bool(parent, row, "Keep script window always on top", "ui_window_always_on_top")

    def _build_buttons(self, parent):
        frame = tb.Frame(parent)
        frame.pack(anchor="e", pady=(10, 0))

        tb.Button(frame, text="Save", width=12, command=self._save).pack(side="right", padx=5)
        tb.Button(frame, text="Cancel", width=12, command=self.destroy).pack(side="right", padx=5)

    def _save(self):
        for attr, var in self._vars.items():
            val = var.get()
            if isinstance(val, str):
                val = val.strip()
                if val == "":
                    val = None

            if attr == "map_gui_image_scale":
                if int(val) > 100:
                    val = 100
                elif int(val) < 20:
                    val = 20

            setattr(Settings, attr, val)

        Settings.save()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() // 2 - self.winfo_width() // 2
        y = parent.winfo_y()
        self.geometry(f"+{x}+{y}")
