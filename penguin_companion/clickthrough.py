"""Let clicks through the stage window everywhere except the penguin and its
bubbles, so the window can cover the screen without getting in the way.

- X11 and XWayland: an X input shape (the SHAPE extension, through libXext),
  which changes only where clicks land, never what's drawn.
- Windows and macOS: the whole window ignores the mouse except while the
  pointer is over something of ours, checked every frame.
- Anything else: Qt's window mask (on Wayland, the surface's input region).
"""

from __future__ import annotations

import ctypes
import ctypes.util

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QCursor, QGuiApplication, QRegion
from PyQt6.QtWidgets import QWidget


class _XRectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


class XShapeInput:
    SHAPE_INPUT = 2
    SHAPE_SET = 0

    def __init__(self, widget: QWidget):
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xext.XShapeQueryExtension.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        xext.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(_XRectangle), ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        self._x11, self._xext = x11, xext
        self._display = x11.XOpenDisplay(None)
        event, error = ctypes.c_int(), ctypes.c_int()
        if not self._display or not xext.XShapeQueryExtension(self._display, ctypes.byref(event), ctypes.byref(error)):
            raise OSError("no X SHAPE extension")
        self._window = int(widget.winId())
        self._last: tuple | None = None
        self.update([])

    def update(self, rects: list[QRect]) -> None:
        key = tuple((r.x(), r.y(), r.width(), r.height()) for r in rects)
        if key == self._last:
            return
        self._last = key
        array = (_XRectangle * max(1, len(key)))(*[_XRectangle(*r) for r in key])
        self._xext.XShapeCombineRectangles(self._display, self._window, self.SHAPE_INPUT, 0, 0, array, len(key), self.SHAPE_SET, 0)
        self._x11.XFlush(self._display)

    def follow_pointer(self, hit) -> None:
        pass

    def close(self) -> None:
        if self._display:
            self._x11.XCloseDisplay(self._display)
            self._display = None


class PointerToggle:
    """Windows and macOS: switch mouse input on only under the pointer."""

    def __init__(self, widget: QWidget):
        self._widget = widget
        self._accepting: bool | None = None

    def update(self, rects: list[QRect]) -> None:
        pass

    def follow_pointer(self, hit) -> None:
        handle = self._widget.windowHandle()
        if handle is None:
            return
        local = self._widget.mapFromGlobal(QCursor.pos())
        dragging = QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton and bool(self._accepting)
        accepting = bool(hit(local)) or dragging
        if accepting != self._accepting:
            self._accepting = accepting
            handle.setFlag(Qt.WindowType.WindowTransparentForInput, not accepting)

    def close(self) -> None:
        pass


class MaskInput:
    def __init__(self, widget: QWidget):
        self._widget = widget
        self._last: tuple | None = None
        self.update([])

    def update(self, rects: list[QRect]) -> None:
        key = tuple((r.x(), r.y(), r.width(), r.height()) for r in rects)
        if key == self._last:
            return
        self._last = key
        region = QRegion()
        for r in rects:
            region = region.united(QRegion(r))
        # An empty mask means "no mask" to Qt; keep one invisible pixel instead.
        self._widget.setMask(region if not region.isEmpty() else QRegion(0, 0, 1, 1))

    def follow_pointer(self, hit) -> None:
        pass

    def close(self) -> None:
        pass


def for_window(widget: QWidget):
    platform = QGuiApplication.platformName()
    if platform == "xcb":
        try:
            return XShapeInput(widget)
        except OSError:
            return MaskInput(widget)
    if platform in ("windows", "cocoa"):
        return PointerToggle(widget)
    return MaskInput(widget)
