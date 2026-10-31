"""The stage: one see-through window over the screen the penguin is on.

The penguin and its speech bubbles are drawn inside it, so moving them is just
drawing them somewhere else: no window moves, so nothing lags or leaves a
trail. Only the patch that changed is redrawn, and clicks go through the
window everywhere except the penguin and its bubble (see clickthrough).
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QRegion, QScreen
from PyQt6.QtWidgets import QWidget

from . import clickthrough
from .behavior import Behavior, Frame
from .bubble import SpeechBubble
from .sprites import Sprites

EDGE = 50  # keep the penguin's centre this far from the screen's sides
FPS = 60  # while it walks, falls or a bubble fades
SLOW_FPS = 30  # otherwise


class Stage(QWidget):
    clicked = pyqtSignal()
    menu_requested = pyqtSignal(QPoint)
    head_moved = pyqtSignal()
    message_closed = pyqtSignal()

    def __init__(self, sprites: Sprites, behavior: Behavior):
        xcb = QGuiApplication.platformName() == "xcb"
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
        # On X11 and XWayland the stage skips the window manager, so it stays
        # above everything, panels included, and never shows in the taskbar.
        flags |= Qt.WindowType.X11BypassWindowManagerHint if xcb else Qt.WindowType.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # macOS hides tool windows otherwise
        self.setMouseTracking(True)
        self.setWindowTitle("Penguin companion")
        self.behavior = behavior
        self.sprites = sprites
        self.bubble = SpeechBubble()
        self.bubble.on_close = self.message_closed.emit
        self._clock = time.monotonic
        self._frame: Frame | None = None
        self._penguin = QRect()  # where the penguin was last drawn, local
        self._bubble_box = QRectF()
        self._head = QPoint()
        self._key = None
        self._press: QPoint | None = None
        self._press_on: str | int | None = None
        self._grab = QPointF()
        self._dragging = False
        self._screen: QScreen | None = None
        self._use_screen(QGuiApplication.screenAt(QPoint(int(behavior.x), 0)) or QGuiApplication.primaryScreen())
        self.winId()  # the native window, so clicks can pass through before it first shows
        self.input = clickthrough.for_window(self)
        self.show()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // FPS)

    # -- what the app uses

    def set_sprites(self, sprites: Sprites) -> None:
        self.sprites = sprites
        self._key = None
        self.update()

    def show_message(self, title: str, text: str = "", buttons=None, timeout_s: float | None = 12) -> None:
        self.bubble.show(title, text, buttons, timeout_s, self._clock())
        self._key = None

    def dismiss_message(self) -> None:
        self.bubble.dismiss(self._clock())

    def message_visible(self) -> bool:
        return self.bubble.visible()

    def head_point(self) -> QPoint:
        """Above the penguin's head, in screen coordinates: where bubbles point."""
        return self.mapToGlobal(self._head)

    def close_stage(self) -> None:
        self._timer.stop()
        self.input.close()
        self.close()

    # -- screens: the stage covers the one the penguin is on

    def _use_screen(self, screen: QScreen) -> None:
        if screen is self._screen:
            return
        self._screen = screen
        self.setGeometry(screen.geometry())
        self._floor()

    def _floor(self) -> int:
        """The floor's height on the stage, and keep the walking range current."""
        avail = self._screen.availableGeometry()
        self.behavior.set_floor(avail.x() + EDGE, avail.x() + avail.width() - EDGE)
        return avail.y() + avail.height() - self.geometry().y()

    # -- every frame

    def _tick(self) -> None:
        now = self._clock()
        if not self._dragging:
            here = QGuiApplication.screenAt(QPoint(int(self.behavior.x), self.geometry().center().y()))
            if here is not None:
                self._use_screen(here)
        floor = self._floor()
        f = self.behavior.tick(now)
        self.bubble.tick(now)
        self._frame = f
        origin = self.geometry().topLeft()

        penguin, outline = QRect(), []
        if f.anim is not None:
            sprite = self.sprites.frame(f.anim, f.index, f.mirror)
            left = round(f.x) - origin.x() - sprite.anchor
            top = floor - sprite.pixmap.height() - round(f.lift)
            penguin = QRect(left, top, sprite.pixmap.width(), sprite.pixmap.height())
            outline = [r.translated(left, top) for r in sprite.outline]
            head = QPoint(round(f.x) - origin.x(), top + 4)
        else:
            head = QPoint(round(f.x) - origin.x(), floor)
        zs = self._z_rect(penguin) if self._sleeping(f) else QRect()

        bubble_box = QRectF()
        if self.bubble.drawn():
            size = self.bubble.size
            x = min(max(head.x() - size.width() / 2, 4), self.width() - size.width() - 4)
            y = max(head.y() - size.height(), 4)
            bubble_box = QRectF(x, y, size.width(), size.height())
            if self.bubble.visible():
                outline.append(bubble_box.toAlignedRect())

        z_phase = int(now * 1.2) % 3 if zs.isValid() else -1
        fade = round(self.bubble.opacity(now) * 20) if self.bubble.drawn() else -1
        key = (f.anim, f.index, f.mirror, penguin.topLeft(), z_phase, bubble_box.topLeft(), self.bubble.hover, fade)
        if key != self._key:
            dirty = QRegion(self._penguin.adjusted(-2, -2, 2, 2)).united(QRegion(penguin.adjusted(-2, -2, 2, 2)))
            dirty = dirty.united(QRegion(self._z_rect(self._penguin))).united(QRegion(zs))
            dirty = dirty.united(QRegion(self._bubble_box.toAlignedRect().adjusted(-3, -3, 3, 3)))
            dirty = dirty.united(QRegion(bubble_box.toAlignedRect().adjusted(-3, -3, 3, 3)))
            self._key = key
            self._penguin, self._bubble_box = penguin, bubble_box
            self.update(dirty)
        if zs.isValid():
            outline.append(zs)
        self.input.update(outline)
        self.input.follow_pointer(self._target_at)
        if head != self._head:
            self._head = head
            self.head_moved.emit()
        # Full speed while anything moves; the sprites' own frame rates are 10 fps or less.
        moving = f.anim == "walk" or self.behavior.held or self.behavior.falling or 0 <= fade < 20
        interval = 1000 // FPS if moving else 1000 // SLOW_FPS
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _sleeping(self, f: Frame) -> bool:
        return f.anim == "sleep" and f.index >= 3

    def _z_rect(self, penguin: QRect) -> QRect:
        if penguin.isNull():
            return QRect()
        return QRect(penguin.center().x() + 6, penguin.top() - 30, 48, 44)

    # -- drawing

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(event.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        f, now = self._frame, self._clock()
        if f is not None and f.anim is not None and not self._penguin.isNull():
            p.drawPixmap(self._penguin.topLeft(), self.sprites.frame(f.anim, f.index, f.mirror).pixmap)
            if self._sleeping(f):
                self._paint_zs(p, self._z_rect(self._penguin), int(now * 1.2) % 3)
        if self.bubble.drawn() and not self._bubble_box.isNull():
            p.save()
            p.translate(self._bubble_box.topLeft())
            self.bubble.paint(p, self._head.x() - self._bubble_box.x(), now)
            p.restore()

    def _paint_zs(self, p: QPainter, rect: QRect, phase: int) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, (size, dx, dy) in enumerate(((12, 2, 30), (15, 15, 17), (19, 29, 3))):
            if i > phase:
                break
            font = QFont()
            font.setBold(True)
            font.setPixelSize(size)
            path = QPainterPath()
            path.addText(rect.x() + dx, rect.y() + dy + size, font, "z" if i < 2 else "Z")
            p.setPen(QPen(QColor(30, 30, 40, 200), 3))
            p.drawPath(path)
            p.fillPath(path, QColor("#e9fbff"))

    # -- the mouse

    def _target_at(self, pos: QPoint) -> str | int | None:
        """What's under a point on the stage: a bubble part, "penguin", or None."""
        if self.bubble.visible() and self._bubble_box.contains(QPointF(pos)):
            return self.bubble.hit(QPointF(pos) - self._bubble_box.topLeft())
        f = self._frame
        if f is not None and f.anim is not None and self._penguin.contains(pos):
            sprite = self.sprites.frame(f.anim, f.index, f.mirror)
            local = pos - self._penguin.topLeft()
            if any(sprite.hit(local.x() + dx, local.y() + dy) for dx, dy in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3))):
                return "penguin"
        return None

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        target = self._target_at(pos)
        if target is None:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.RightButton and target == "penguin":
            self.menu_requested.emit(event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            self._press, self._press_on, self._dragging = event.globalPosition().toPoint(), target, False
            self._grab = event.globalPosition() - QPointF(self.behavior.x, self._screen_floor() - self.behavior.lift)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._press is None:
            hover = self._target_at(pos)
            self.bubble.hover = hover if isinstance(hover, int) else None
            return
        if self._press_on != "penguin":
            return
        gpos = event.globalPosition()
        if not self._dragging and (gpos.toPoint() - self._press).manhattanLength() < 6:
            return
        self._dragging = True
        screen = QGuiApplication.screenAt(gpos.toPoint())
        if screen is not None:
            self._use_screen(screen)
        foot = gpos - self._grab
        self.behavior.hold(foot.x(), self._screen_floor() - foot.y(), self._clock())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        target, self._press = self._press_on, None
        if self._dragging:
            self._dragging = False
            self.behavior.release(self._clock())
        elif target == "penguin":
            self.clicked.emit()
        elif target == "close" or (target == "body" and not self.bubble.buttons):
            self.dismiss_message()
        elif isinstance(target, int) and self._target_at(event.position().toPoint()) == target:
            action = self.bubble.buttons[target].action
            self.dismiss_message()
            if action:
                action()

    def _screen_floor(self) -> float:
        avail = self._screen.availableGeometry()
        return avail.y() + avail.height()
