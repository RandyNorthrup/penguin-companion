"""Speech bubbles: messages drawn by the stage, and the ask box you type in."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSizeF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QTextDocument,
)
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QTextBrowser, QToolButton, QVBoxLayout, QWidget

ACCENT = QColor("#26b8d9")  # the penguin's glowing cyan nodes
PAD = 14
TAIL = 12
RADIUS = 14
FADE = 0.14  # seconds


def open_link(url: QUrl) -> None:
    """Links in answers open in the browser; nothing else (no files, no apps)."""
    if url.scheme() in ("http", "https", "mailto"):
        QDesktopServices.openUrl(url)


def colours() -> tuple[QColor, QColor]:
    """Bubble fill and text, from the desktop's light or dark theme."""
    pal = QApplication.palette()
    fill = QColor(pal.color(QPalette.ColorRole.Base))
    fill.setAlpha(248)
    return fill, QColor(pal.color(QPalette.ColorRole.Text))


def bubble_path(box: QRectF, tail_x: float) -> QPainterPath:
    """A rounded box with a tail under it pointing down at `tail_x`."""
    path = QPainterPath()
    path.addRoundedRect(box, RADIUS, RADIUS)
    tail = QPainterPath()
    tail.moveTo(tail_x - 9, box.bottom() - 1)
    tail.lineTo(tail_x, box.bottom() + TAIL)
    tail.lineTo(tail_x + 9, box.bottom() - 1)
    tail.closeSubpath()
    return path.united(tail)


def _font(points: float, bold: bool = False) -> QFont:
    font = QFont(QApplication.font())
    font.setPointSizeF(points)
    font.setBold(bold)
    return font


@dataclass
class _Button:
    label: str
    action: Callable[[], None] | None
    rect: QRectF


class SpeechBubble:
    """A message above the penguin's head. It has no window of its own: the
    stage draws it, so it follows the penguin smoothly."""

    MAX_WIDTH = 340

    def __init__(self):
        self.title = ""
        self.doc = QTextDocument()
        self.doc.setDocumentMargin(0)
        self.buttons: list[_Button] = []
        self.size = QSizeF()
        self.hover: int | None = None
        self.on_close: Callable[[], None] | None = None
        self._shown_at = 0.0
        self._expires: float | None = None
        self._closing_at: float | None = None
        self._visible = False
        self._close_rect = QRectF()
        self._body_top = 0.0

    def visible(self) -> bool:
        """Showing and not on its way out."""
        return self._visible and self._closing_at is None

    def drawn(self) -> bool:
        """Still on screen, perhaps fading out."""
        return self._visible

    def show(self, title: str, text: str, buttons, timeout_s: float | None, now: float) -> None:
        self.title = title
        self.hover = None
        title_font, body_font = _font(10.5, bold=True), _font(10.5)
        self.doc.setDefaultFont(body_font)
        self.doc.setMarkdown(text or "")
        has_text = bool(text)
        metrics = QFontMetricsF(body_font)
        self.buttons = [_Button(label, action, QRectF(0, 0, metrics.horizontalAdvance(label) + 26, metrics.height() + 10)) for label, action in buttons or []]
        title_w = QFontMetricsF(title_font).horizontalAdvance(title) + 28
        buttons_w = sum(b.rect.width() for b in self.buttons) + 8 * max(0, len(self.buttons) - 1)
        inner_max = self.MAX_WIDTH - 2 * PAD
        self.doc.setTextWidth(inner_max)
        inner = min(inner_max, max(140, title_w, buttons_w, self.doc.idealWidth() + 1 if has_text else 0))
        self.doc.setTextWidth(inner)
        title_h = QFontMetricsF(title_font).height()
        height = PAD + title_h
        self._body_top = height + 6
        if has_text:
            height += 6 + self.doc.size().height()
        if self.buttons:
            height += 10
            x = PAD + inner
            for b in reversed(self.buttons):
                x -= b.rect.width()
                b.rect.moveTo(x, height)
                x -= 8
            height += self.buttons[0].rect.height()
        height += PAD
        self.size = QSizeF(inner + 2 * PAD, height + TAIL)
        self._close_rect = QRectF(PAD + inner - 16, PAD - 2, 20, title_h + 4)
        self._shown_at, self._closing_at = now, None
        self._expires = now + timeout_s if timeout_s else None
        self._visible = True
        self._title_font, self._has_text = title_font, has_text

    def dismiss(self, now: float) -> None:
        """Closed as far as anyone is concerned; it fades out on its own."""
        if self.visible():
            self._closing_at = now
            self._expires = None
            if self.on_close:
                self.on_close()

    def tick(self, now: float) -> None:
        if self._expires is not None and now >= self._expires:
            self.dismiss(now)
        if self._closing_at is not None and now - self._closing_at >= FADE:
            self._visible, self._closing_at = False, None

    def opacity(self, now: float) -> float:
        if self._closing_at is not None:
            return max(0.0, 1 - (now - self._closing_at) / FADE)
        return min(1.0, (now - self._shown_at) / FADE)

    def hit(self, pos: QPointF) -> str | int | None:
        """What's at `pos` (bubble coordinates): a button's index, "close", "body"."""
        if self._close_rect.contains(pos):
            return "close"
        for i, b in enumerate(self.buttons):
            if b.rect.contains(pos):
                return i
        if QRectF(0, 0, self.size.width(), self.size.height() - TAIL).contains(pos):
            return "body"
        return None

    def paint(self, p: QPainter, tail_x: float, now: float) -> None:
        fill, text = colours()
        p.save()
        p.setOpacity(self.opacity(now))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(1, 1, self.size.width() - 2, self.size.height() - TAIL - 2)
        path = bubble_path(box, tail_x)
        p.fillPath(path, fill)
        p.setPen(QPen(ACCENT, 2))
        p.drawPath(path)
        p.setPen(text)
        p.setFont(self._title_font)
        p.drawText(QRectF(PAD, PAD, self.size.width() - 2 * PAD - 20, 40), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.title)
        p.setFont(_font(9.5))
        p.drawText(self._close_rect, Qt.AlignmentFlag.AlignCenter, "✕")
        if self._has_text:
            p.save()
            p.translate(PAD, self._body_top)
            ctx = QAbstractTextDocumentLayout.PaintContext()
            ctx.palette.setColor(QPalette.ColorRole.Text, text)
            self.doc.documentLayout().draw(p, ctx)
            p.restore()
        p.setFont(_font(10))
        for i, b in enumerate(self.buttons):
            if i == self.hover:
                p.setBrush(ACCENT)
                p.setPen(QPen(ACCENT, 1.2))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(ACCENT, 1.2))
            p.drawRoundedRect(b.rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.setPen(QColor("white") if i == self.hover else text)
            p.drawText(b.rect, Qt.AlignmentFlag.AlignCenter, b.label)
        p.restore()


class AskBox(QWidget):
    """The bubble you type questions into. A real window, since it needs the
    keyboard; the penguin holds still while it's open."""

    closed = pyqtSignal()
    submitted = pyqtSignal(str)
    reset_requested = pyqtSignal()

    WIDTH = 380
    MAX_ANSWER = 320

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFixedWidth(self.WIDTH)
        self._anchor = QPoint(0, 0)
        self._tail_x = self.WIDTH / 2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14 + TAIL)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("title")
        top.addWidget(self.title, 1)
        self.reset_button = QToolButton(text="New chat", autoRaise=True)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        top.addWidget(self.reset_button)
        close = QToolButton(text="✕", autoRaise=True)
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self.dismiss)
        top.addWidget(close)
        layout.addLayout(top)
        self.answer = QTextBrowser(openLinks=False)
        self.answer.anchorClicked.connect(open_link)
        self.answer.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.answer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.answer.document().setDocumentMargin(2)
        layout.addWidget(self.answer)
        self.entry = QLineEdit()
        self.entry.returnPressed.connect(self._submit)
        layout.addWidget(self.entry)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)
        self._style()

    def open(self, anchor: QPoint, title: str, hint: str, placeholder: str, text: str = "", prefill: str = "") -> None:
        self.title.setText(title)
        self.hint.setText(QFontMetricsF(self.hint.font()).elidedText(hint, Qt.TextElideMode.ElideRight, self.WIDTH - 34))
        self.entry.setPlaceholderText(placeholder)
        self.entry.setText(prefill)
        self.reset_button.hide()
        self._anchor = QPoint(anchor)
        self.set_answer(text)
        self.show()
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()
        self.entry.end(False)

    def set_answer(self, markdown: str) -> None:
        if markdown:
            self.answer.setMarkdown(markdown)
            doc = self.answer.document()
            doc.setTextWidth(self.WIDTH - 32 - 10)
            self.answer.setFixedHeight(min(int(doc.size().height()) + 4, self.MAX_ANSWER))
            self.answer.show()
        else:
            self.answer.clear()
            self.answer.hide()
        self._fit()
        self.answer.verticalScrollBar().setValue(0)

    def set_resettable(self, on: bool) -> None:
        self.reset_button.setVisible(on)

    def place(self, anchor: QPoint) -> None:
        self._anchor = QPoint(anchor)
        self._fit()

    def dismiss(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def _fit(self) -> None:
        layout = self.layout()
        layout.activate()
        height = layout.totalSizeHint().height()
        screen = QGuiApplication.screenAt(self._anchor) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(self._anchor.x() - self.WIDTH // 2, geo.left() + 4), geo.right() - self.WIDTH - 4)
        y = max(self._anchor.y() - height, geo.top() + 4)
        self._tail_x = min(max(self._anchor.x() - x, RADIUS + TAIL), self.WIDTH - RADIUS - TAIL)
        self.setGeometry(x, y, self.WIDTH, height)
        self.update()

    def _submit(self) -> None:
        text = self.entry.text().strip()
        if text:
            self.entry.clear()
            self.submitted.emit(text)

    def _style(self) -> None:
        fill, text = colours()
        dim = QColor(text)
        dim.setAlpha(150)
        base = QApplication.palette().color(QPalette.ColorRole.Base)
        self.setStyleSheet(
            f"""
            QLabel, QTextBrowser {{ color: {text.name()}; background: transparent; font-size: 10.5pt; }}
            QLabel#title {{ font-weight: 600; }}
            QLabel#hint {{ color: {dim.name(QColor.NameFormat.HexArgb)}; font-size: 9pt; }}
            QLineEdit {{ border: 1px solid {ACCENT.name()}; border-radius: 8px; padding: 6px 8px;
                         background: {base.name()}; color: {text.name()}; font-size: 10.5pt; }}
            QToolButton {{ color: {text.name()}; border: none; padding: 2px 6px; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {ACCENT.name()}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            """
        )
        for child in self.findChildren(QWidget):
            child.ensurePolished()

    def paintEvent(self, _event) -> None:
        fill, _ = colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = bubble_path(QRectF(self.rect()).adjusted(1, 1, -1, -1 - TAIL), self._tail_x)
        p.fillPath(path, fill)
        p.setPen(QPen(ACCENT, 2))
        p.drawPath(path)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)
