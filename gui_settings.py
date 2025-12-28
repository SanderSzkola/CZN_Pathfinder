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

        self._build_form(container)
        self._build_buttons(container)

        self._center(parent)

    def _build_form(self, parent):
        def _make_var(attr):
            val = getattr(Settings, attr)
            if isinstance(val, bool):
                return tk.BooleanVar(value=val)
            if isinstance(val, float):
                return tk.DoubleVar(value=val)
            if isinstance(val, int):
                return tk.IntVar(value=val)
            return tk.StringVar(value="" if val is None else val)

        def add_field(label, attr, disabled=False):
            nonlocal row
            var = _make_var(attr)
            tb.Label(parent, text=label).grid(
                row=row, column=0, sticky="w", padx=6, pady=4)
            entry = tb.Entry(parent, textvariable=var, width=25)
            if disabled:
                entry.configure(state="disabled")
            entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            self._vars[attr] = var
            row += 1

        def add_bool(label, attr):
            nonlocal row
            var = _make_var(attr)
            cb = tb.Checkbutton(parent, text=label, variable=var)
            cb.grid(row=row, column=0, columnspan=1, sticky="w", padx=6, pady=4)
            self._vars[attr] = var
            row += 1

        def add_explanation(label):
            nonlocal row
            tb.Label(parent, text=label).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
            row += 1

        def add_separator(pady=16):
            nonlocal row
            sep = tb.Separator(parent, orient="horizontal")
            sep.grid(row=row, column=0, columnspan=2, sticky="ew", pady=pady)
            row += 1

        row = 0
        add_explanation("Any change requires script restart to take effect")
        add_field("Target app name", "target_app_name")
        add_bool("Dark mode", "darkmode")
        add_bool("Auto import score table", "auto_import_score")

        add_separator()
        add_bool("Detect keyboard", "keyboard_input")
        add_explanation("Allows for calling scanners directly from the game")
        add_field("Run automatic scanner", "keyboard_input_autoscanner")
        add_field("Run halfauto scanner", "keyboard_input_halfautoscanner")
        add_explanation("Accepts letters and digits, alone or joined by + sign")

        add_separator()
        add_bool("Check for update", "autoupdate")
        add_explanation("Checked once every day to not annoy GitHub"
                        "\nThe response is saved so you can be annoyed on every startup"
                        "\nuntil you decide to update")
        add_field("Local version", "local_version", True)
        add_field("GitHub version", "remote_version", True)

    def _build_buttons(self, parent):
        frame = tb.Frame(parent)
        frame.grid(row=999, column=0, columnspan=2, sticky="e", pady=(10, 0))

        tb.Button(frame, text="Save", width=12, command=self._save).pack(
            side="right", padx=5)
        tb.Button(frame, text="Cancel", width=12, command=self.destroy).pack(
            side="right", padx=5)

    def _save(self):
        for attr, var in self._vars.items():
            val = var.get()
            if isinstance(val, str):
                val = val.strip()
                if val == "":
                    val = None
            setattr(Settings, attr, val)

        Settings.save()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() // 2 - self.winfo_width() // 2
        y = parent.winfo_y()
        self.geometry(f"+{x}+{y}")
