# grabber.py
import os.path
import time
from typing import Optional

import pyautogui
import win32gui
# import pygetwindow as gw
from PIL import Image
from queue import Queue
from pynput import mouse

DEFAULT_DRAG_SQ_THRESHOLD = 100 ** 2

"""
Manages all screen actions - switch window, take screenshot, move map
Requires admin to run, as game is in admin itself,
and lower process cant send signals to elevated process or something.
"""

GAME_WINDOW = "Chaos Zero Nightmare"
# GAME_WINDOW = "Spotify"
SCRIPT_WINDOW = "CZN Pathfinder"


def switch_window(step):  # TODO: think about some other way, alt-tab is unreliable // pygetwindow? win32gui?
    time.sleep(0.2)
    # pyautogui.hotkey("alt", "tab")
    # time.sleep(0.2)
    switch_window_win32gui(step)
    # switch_window_pygetwindow(step)


def _find_hwnd(title_substring: str):
    result = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in title.lower():
                result.append(hwnd)

    win32gui.EnumWindows(enum_handler, None)
    return result[0] if result else None


def switch_window_win32gui(step):
    if step == 0:
        hwnd = _find_hwnd(GAME_WINDOW)
        label = GAME_WINDOW
    else:
        hwnd = _find_hwnd(SCRIPT_WINDOW)
        label = SCRIPT_WINDOW

    if hwnd is None:
        game_text = ". Is CZN running?" if step == 0 else None
        raise Exception(f"grabber / win32gui: Window not found: {label}" + game_text)

    win32gui.ShowWindow(hwnd, 5)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.2)


# def switch_window_pygetwindow(step):
#     name = GAME_WINDOW if step == 0 else SCRIPT_WINDOW
#
#     windows = [w for w in gw.getAllWindows() if name.lower() in w.title.lower()]
#     if not windows:
#         print("pygetwindow: Window not found:", name)
#         return
#
#     w = windows[0]
#     w.activate()
#     time.sleep(0.2)


def screenshot(save_folder: Optional[str] = None, index: int = -1) -> Image.Image:
    img = pyautogui.screenshot()
    if save_folder is not None:
        if index == -1:
            # for quick lookup only, can flip from 99 to 00 if timing is unfortunate, use index
            ts = int(time.time() * 10)
            ts = str(ts)[-5:]
            img.save(os.path.join(save_folder, f"map_frag_{ts}.png"))
        else:
            img.save(os.path.join(save_folder, f"map_frag_{index:02d}.png"))
    return img


def do_drag_move(node_from, node_to):
    current_x, current_y = pyautogui.position()
    if abs(current_x - node_from.x) > 50:
        pyautogui.moveTo(node_from.x, node_from.y, duration=0.4)
    else:
        pyautogui.moveTo(node_from.x, current_y, duration=0.1)
    time.sleep(0.03)
    pyautogui.mouseDown()
    pyautogui.moveTo(node_to.x, node_to.y, duration=0.5)
    time.sleep(0.05)
    pyautogui.mouseUp()


def move_mouse(node_to):
    pyautogui.moveTo(node_to.x, node_to.y, duration=0.4)
    time.sleep(0.1)


def mock_switch_window():
    time.sleep(0.01)


def mock_screenshot(save_folder: Optional[str] = None) -> Image.Image:
    img = Image.open(save_folder)
    time.sleep(0.01)
    return img


def mock_move_screen(node_from, node_to):
    time.sleep(0.01)


# half-auto nonsense, but maybe more-legal
class DragListener:
    def __init__(self,
                 screenshot_q: Queue,
                 save_folder: Optional[str],
                 log=lambda msg: None):
        self.screenshot_q = screenshot_q
        self.save_folder = save_folder
        self.drag_sq_threshold = DEFAULT_DRAG_SQ_THRESHOLD
        self.log = log
        self.down_pos = None
        self.step = 0
        self.listener = None

    def start(self):
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()

    def _on_click(self, x, y, button, pressed): #  maybe add right click cancel later
        if pressed:
            self.down_pos = (x, y)
            return

        if self.down_pos is None:
            return

        dx = x - self.down_pos[0]
        dy = y - self.down_pos[1]
        dist_sq = dx * dx + dy * dy
        self.down_pos = None

        if dist_sq < self.drag_sq_threshold:
            self.log(f"Drag detected ({dist_sq:.1E} < {self.drag_sq_threshold:.1E}) and ignored")
            return

        step = self.step
        self.step += 1

        self.log(f"Drag detected ({dist_sq:.1E} > {self.drag_sq_threshold:.1E}), screenshot captured as step_{step}")
        time.sleep(0.1)

        img = screenshot(self.save_folder, index=step)
        self.screenshot_q.put((step, img))


class MockDragListener:
    def __init__(self,
                 screenshot_q: Queue,
                 save_folder: Optional[str],
                 log=lambda msg: None):
        self.screenshot_q = screenshot_q
        self.save_folder = "Example_scan_result"
        self.drag_sq_threshold = DEFAULT_DRAG_SQ_THRESHOLD
        self.log = log
        self.down_pos = None
        self.step = 0
        self.listener = None

    def start(self):
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()
        for f in os.listdir(self.save_folder):
            if f.startswith("merged") or not f.endswith("png"):
                continue
            img = mock_screenshot(os.path.join(self.save_folder, f))
            self.screenshot_q.put((self.step, img))
            self.step += 1

    def stop(self):
        if self.listener:
            self.listener.stop()

    def _on_click(self, x, y, button, pressed):
        return
