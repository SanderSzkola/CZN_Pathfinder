# grabber.py
import os.path
import time
from typing import Optional

import pyautogui
import cv2

if not hasattr(cv2, "__version__"):  # random GPT-approved dependency error fix
    cv2.__version__ = "4"
import win32gui
from PIL import Image
from queue import Queue
from pynput import mouse, keyboard

from settings import Settings

DEFAULT_DRAG_SQ_THRESHOLD = 100 ** 2

"""
Manages all screen actions - switch window, take screenshot, move map
Requires admin to run, as game is in admin itself,
and lower process cant send signals to elevated process or something.
"""

GAME_WINDOW = Settings.target_app_name
SCRIPT_WINDOW = "CZN Pathfinder"


def switch_window(step):
    time.sleep(0.2)
    switch_window_win32gui(step)


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
        game_text = ". Is CZN running?" if step == 0 else ''
        raise Exception(f"Window not found: {label}" + game_text)

    try:  # breaks if called from game
        win32gui.ShowWindow(hwnd, 5)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:  # fallback, works only if script is first in alt-tab queue
        pyautogui.hotkey("alt", "tab")
        time.sleep(0.2)
        target_window = GAME_WINDOW if step == 0 else SCRIPT_WINDOW
        title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
        if not target_window.lower() in title.lower():
            raise IOError("Window switched to unexcepted place, script stopped")
    time.sleep(0.2)


def screenshot(save_folder: Optional[str] = None, index: int = -1, whole_screen_mode=False):
    if whole_screen_mode:
        img = pyautogui.screenshot()
        game_window_corner_offset = (0, 0)
    else:
        hwnd = _find_hwnd(GAME_WINDOW)
        if not hwnd:
            raise Exception("Window not found")
        left_top = win32gui.ClientToScreen(hwnd, (0, 0))
        r = win32gui.GetClientRect(hwnd)
        left, top = left_top
        w, h = r[2], r[3]
        img = pyautogui.screenshot(region=(left, top, w, h))
        game_window_corner_offset = (left, top)

    if save_folder is not None:
        if index == -1:
            # for quick lookup only, can flip from 99 to 00 if timing is unfortunate, use index
            ts = int(time.time() * 10)
            ts = str(ts)[-5:]
            img.save(os.path.join(save_folder, f"map_frag_{ts}.png"))
        else:
            img.save(os.path.join(save_folder, f"map_frag_{index:02d}.png"))
    return img, game_window_corner_offset


def do_drag_move(node_from, node_to, game_window_corner_offset):
    current_x, current_y = pyautogui.position()
    ox, oy = game_window_corner_offset
    if abs(current_x - node_from.x) > 50:
        pyautogui.moveTo(node_from.x + ox, node_from.y + oy, duration=0.4)
    else:
        pyautogui.moveTo(node_from.x + ox, current_y, duration=0.1)
    time.sleep(0.03)
    pyautogui.mouseDown()
    pyautogui.moveTo(node_to.x + ox, node_to.y + oy, duration=0.5)
    time.sleep(0.05)
    pyautogui.mouseUp()


def move_mouse(node_to, game_window_corner_offset):
    ox, oy = game_window_corner_offset
    pyautogui.moveTo(node_to.x + ox, node_to.y + oy, duration=0.4)
    time.sleep(0.1)


def mock_switch_window():
    time.sleep(0.01)


def mock_screenshot(save_folder: Optional[str] = None) -> Image.Image:
    img = Image.open(save_folder)
    time.sleep(0.01)
    return img


def mock_move_screen(node_from, node_to):
    time.sleep(0.01)


def get_screen_res():
    w, h = pyautogui.size()
    return w, h


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

    def _on_click(self, x, y, button, pressed):
        if button == mouse.Button.right and not pressed:
            self.log("Drag scanner stopped (right click)")
            self.screenshot_q.put(None)
            self.stop()
            return

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

        img, _ = screenshot(self.save_folder, index=step)
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


# keyboard listener for hotkey action triggers
class KeyboardListener:
    def __init__(self, hotkeys: list[tuple[str, str]], on_trigger):
        self.hotkeys = [(action, parse_hotkey(combo)) for action, combo in hotkeys]

        self.on_trigger = on_trigger
        self.listener = None

        self._pressed = set()
        self._fired = set()

    def start(self):
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _on_press(self, key):
        if not isinstance(key, keyboard.KeyCode):
            return
        self._pressed.add(key)
        for action, combo in self.hotkeys:
            if action in self._fired:
                continue
            if combo.issubset(self._pressed):
                self._fired.add(action)
                try:
                    self.on_trigger(action)
                except Exception:
                    pass

    def _on_release(self, key):
        if not isinstance(key, keyboard.KeyCode):
            return
        self._pressed.discard(key)
        for action, combo in self.hotkeys:
            if key in combo:
                self._fired.discard(action)


def parse_hotkey(hotkey: str):
    result = set()
    for part in hotkey.lower().split("+"):
        part = part.strip()
        if len(part) == 1:
            result.add(keyboard.KeyCode.from_char(part))
        else:
            raise ValueError(f"Unsupported key: {part}")

    return result
