# fake_window_for_app_testing.py
import tkinter as tk
from PIL import Image, ImageTk

from data.settings import Settings
from utils.path_converter import get_path

RESOLUTION_CONFIGS = {
    "720p": {
        "size": (1280, 720),
        "image": get_path(["Images", "Fake_map", "720_full_map.png"]),
    },
    "1080p": {
        "size": (1920, 1080),
        "image": get_path(["Images", "Fake_map", "1080_full_map.png"]),
    },
    "1440p": {
        "size": (2560, 1440),
        "image": get_path(["Images", "Fake_map", "1440_full_map.png"]),
    },
}


class ImageViewer:
    def __init__(self, root, resolution="1080p"):
        self.root = root
        self.canvas = tk.Canvas(root, highlightthickness=0)
        self.canvas.pack()

        self.image_id = None
        self.tk_image = None

        self.offset_x = 0
        self.drag_start_x = None
        self.start_offset = 0

        self.set_resolution(resolution)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click)

        root.bind(Settings.keyboard_input_fake_map_720, lambda e: self.set_resolution("720p"))
        root.bind(Settings.keyboard_input_fake_map_1080, lambda e: self.set_resolution("1080p"))
        root.bind(Settings.keyboard_input_fake_map_1440, lambda e: self.set_resolution("1440p"))

    def set_resolution(self, key):
        cfg = RESOLUTION_CONFIGS[key]

        self.view_w, self.view_h = cfg["size"]

        self.image = Image.open(cfg["image"])
        self.img_w, self.img_h = self.image.size
        self.tk_image = ImageTk.PhotoImage(self.image)

        self.canvas.config(width=self.view_w, height=self.view_h)

        if self.image_id is None:
            self.image_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
        else:
            self.canvas.itemconfig(self.image_id, image=self.tk_image)

        self.offset_x = 0
        self.update_view()

    def clamp_offset(self, x):
        return max(0, min(x, max(0, self.img_w - self.view_w)))

    def on_press(self, event):
        self.drag_start_x = event.x
        self.start_offset = self.offset_x

    def on_drag(self, event):
        dx = event.x - self.drag_start_x
        self.offset_x = self.clamp_offset(self.start_offset - dx)
        self.update_view()

    def on_right_click(self, event):
        self.offset_x = 0
        self.update_view()

    def update_view(self):
        self.canvas.coords(self.image_id, -self.offset_x, 0)


def open_fake_map(resolution="1080p"):
    win = tk.Toplevel()
    win.title(Settings.target_app_name + " | fake map app")

    ImageViewer(win, resolution=resolution)
    win.focus_force()
    return win


if __name__ == "__main__":
    root = tk.Tk()
    root.title(Settings.target_app_name + " | fake map app")

    app = ImageViewer(root, resolution="1080p")

    root.mainloop()
