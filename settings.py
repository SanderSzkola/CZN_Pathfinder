# settings.py
import json
from datetime import datetime
from pathlib import Path

from path_converter import get_path


class Settings:
    _path: Path | None = None
    _loaded: bool = False

    # template params
    template_scale: float = 1.0
    screenshot_scale: float = 0.0  # 0 as uncalibrated flag, normally 1 or 0.5
    threshold: float = 0.98

    # preview draw flags
    preview_dim_background: bool = True
    preview_draw_corridors: bool = True
    preview_draw_nodes_text: bool = True
    preview_draw_fringe_marks: bool = True
    preview_draw_node_icons: bool = True
    preview_draw_trim_overlay: bool = True

    # whatever else
    testmode: bool = False
    request_admin: bool = False
    darkmode: bool = True
    auto_import_score: bool = True
    autoupdate: bool = True
    last_update_check: datetime | None = None
    remote_version: str | None = None
    local_version: str | None = "v0.4.3-rc1"  # REMEMBER TO UPDATE BEFORE BUILD, or integrate into build somehow
    target_app_name: str = "Chaos Zero Nightmare"
    keyboard_input: bool = False
    keyboard_input_autoscanner: str = "s+1"
    keyboard_input_halfautoscanner: str = "s+2"

    @classmethod
    def _ensure_path(cls) -> None:
        if cls._path is None:
            cls._path = Path(get_path("settings.json"))

    @classmethod
    def load(cls) -> None:
        if cls._loaded:
            return

        cls._ensure_path()

        if not cls._path.exists():
            cls.save()
            cls._loaded = True
            return

        with cls._path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for key, value in data.items():
            if not hasattr(cls, key):
                continue
            if key == "local_version":
                continue

            if key == "last_update_check" and value is not None:
                value = datetime.fromisoformat(value)

            setattr(cls, key, value)

        cls._loaded = True

    @classmethod
    def save(cls) -> None:
        cls._ensure_path()

        data = {
            k: getattr(cls, k)
            for k in vars(cls)
            if not k.startswith("_") and not callable(getattr(cls, k))
        }

        if cls.last_update_check is not None:
            data["last_update_check"] = cls.last_update_check.isoformat()

        cls._path.parent.mkdir(parents=True, exist_ok=True)

        with cls._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def calibrated(cls):
        return cls.screenshot_scale > 0

    @classmethod
    def get_scale(cls):
        if cls.screenshot_scale != 0:
            return cls.template_scale / cls.screenshot_scale
        else:
            return cls.template_scale


# autoload on import
Settings.load()
