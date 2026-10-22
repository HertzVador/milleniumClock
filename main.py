"""Disc clock: concentric rotating rings from years (outer) down to milliseconds (inner)."""

import argparse
import calendar
import json
import math
import signal
import sys
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QConicalGradient, QFont, QKeyEvent, QPainter, QPainterPath, QPen, QPolygonF,
                           QSurfaceFormat)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Northern-hemisphere seasons, Jan..Dec: icy winter, green spring, vivid summer, orange-to-red autumn.
SEASON_COLORS = [QColor(c) for c in (
    "#7fb4ff", "#a6dcff", "#9be86a", "#4fd65a", "#2fc96e", "#ffe63a",
    "#ffc21a", "#ff9f1a", "#ff7f1f", "#f25a26", "#d8352a", "#6f95ff")]
BACKGROUND = QColor("#0e1016")
HUB_FRACTION = 0.30  # share of the clock radius used by the central domino rings
INDICATOR = QColor("#ff3355")
NIGHT_SHADE = QColor(0, 0, 10, 170)
USER_AGENT = {"User-Agent": "disc-clock/1.0"}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def _hour_of_day(iso: str) -> float | None:
    dt = datetime.fromisoformat(iso)
    if dt.year == 1970:  # API returns the epoch during polar day/night
        return None
    local = dt.astimezone()
    return local.hour + local.minute / 60 + local.second / 3600


class SunTimes:
    """Fetches sunrise/sunset in a background thread and refreshes whenever the date changes."""

    CHECK_INTERVAL_S = 600

    def __init__(self, lat: float | None, lon: float | None) -> None:
        self._lat, self._lon = lat, lon
        self._fetched_for: date | None = None
        self.night: tuple[float, float] | None = None  # (sunset hour, sunrise hour), local time
        self.noon: float | None = None  # solar noon hour, local time
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            today = date.today()
            if self._fetched_for != today:
                try:
                    self._refresh(today)
                    self._fetched_for = today
                except (OSError, ValueError, KeyError) as exc:
                    print(f"Sunrise/sunset fetch failed, will retry: {exc}", file=sys.stderr)
            time.sleep(self.CHECK_INTERVAL_S)

    def _refresh(self, day: date) -> None:
        if self._lat is None or self._lon is None:
            loc = _get_json("https://ipapi.co/json/")
            self._lat, self._lon = float(loc["latitude"]), float(loc["longitude"])
        data = _get_json("https://api.sunrise-sunset.org/json"
                         f"?lat={self._lat:.5f}&lng={self._lon:.5f}&date={day.isoformat()}&formatted=0")
        if data.get("status") != "OK":
            raise ValueError(f"API status {data.get('status')}")
        sunrise = _hour_of_day(data["results"]["sunrise"])
        sunset = _hour_of_day(data["results"]["sunset"])
        self.night = (sunset, sunrise) if sunrise is not None and sunset is not None else None
        self.noon = _hour_of_day(data["results"]["solar_noon"])


@dataclass
class RingState:
    count: int                      # number of major divisions
    position: float                 # continuous current index in [0, count)
    label: Callable[[int], str]     # label for major division i
    label_every: int = 1            # draw a label every N major divisions
    subdiv: int = 1                 # minor ticks per major division
    fixed: bool = False             # ring stays still; a chasing light marks the position instead
    colors: list[QColor] | None = None  # per-division colors, blended into a gradient around the ring


@dataclass
class Ring:
    name: str
    color: QColor
    state: Callable[[datetime], RingState]


def _positions(now: datetime) -> dict[str, float]:
    ms = now.microsecond / 1000.0
    sec = now.second + ms / 1000.0
    minute = now.minute + sec / 60.0
    hour = now.hour + minute / 60.0
    dim = calendar.monthrange(now.year, now.month)[1]
    day = now.day - 1 + hour / 24.0
    month = now.month - 1 + day / dim
    return {"ms": ms, "sec": sec, "min": minute, "hour": hour, "day": day, "month": month}


RINGS: list[Ring] = [
    # Window of 10 years starting at last year; the current year sits at index 1.
    Ring("Year", QColor("#9b8cff"), lambda n: RingState(
        10, 1 + _positions(n)["month"] / 12.0, lambda i, first=n.year - 1: str(first + i), subdiv=12)),
    Ring("Month", QColor("#4aa8ff"), lambda n: RingState(
        12, _positions(n)["month"], lambda i: MONTHS[i], subdiv=4, colors=SEASON_COLORS)),
    Ring("Day", QColor("#2fd6c6"), lambda n: RingState(
        calendar.monthrange(n.year, n.month)[1], _positions(n)["day"], lambda i: str(i + 1), subdiv=4)),
    Ring("Hour", QColor("#82e04f"), lambda n: RingState(
        24, _positions(n)["hour"], lambda i: f"{i:02d}", subdiv=4)),
    Ring("Minute", QColor("#ffd23f"), lambda n: RingState(
        60, _positions(n)["min"], lambda i: f"{i:02d}", label_every=5)),
    Ring("Second", QColor("#ff9142"), lambda n: RingState(
        60, _positions(n)["sec"], lambda i: f"{i:02d}", label_every=5)),
    Ring("Ten seconds", QColor("#ff5277"), lambda n: RingState(
        10, _positions(n)["sec"] % 10, str, subdiv=10, fixed=True)),
]


def _glow(age: float, period: float, trail: float, fade_in: float) -> float:
    """Brightness in [0, 1] for an item `age` units behind the moving light (wraps every `period`)."""
    age %= period
    if age > period - fade_in:
        return 1.0 - (period - age) / fade_in
    return max(0.0, 1.0 - age / trail) ** 2


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                           a.greenF() + (b.greenF() - a.greenF()) * t,
                           a.blueF() + (b.blueF() - a.blueF()) * t)


class DiscClock(QOpenGLWidget):
    def __init__(self, sun: SunTimes) -> None:
        super().__init__()
        self._sun = sun
        self.setWindowTitle("Disc Clock")
        self.resize(900, 900)
        self._frame_times: deque[float] = deque(maxlen=120)
        self._label_font = QFont("Segoe UI")
        self._center_font = QFont("Consolas")
        self._small_font = QFont("Consolas")

        self._limit_fps = 60
        self._render_timer = QTimer(self)
        self._render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._render_timer.timeout.connect(self.update)
        self._render_timer.start(max(1, 1000 // self._limit_fps))

    def resizeGL(self, w: int, h: int) -> None:
        radius = min(w, h) / 2 * 0.96
        ring_width = radius * (1 - HUB_FRACTION) / len(RINGS)
        self._label_font.setPixelSize(max(8, int(ring_width * 0.30)))
        self._center_font.setPixelSize(max(8, int(radius * 0.055)))
        self._small_font.setPixelSize(max(8, int(radius * 0.03)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _fps(self) -> float:
        now = time.perf_counter()
        self._frame_times.append(now)
        if len(self._frame_times) < 2:
            return 0.0
        return (len(self._frame_times) - 1) / (self._frame_times[-1] - self._frame_times[0])

    def paintGL(self) -> None:
        now = datetime.now()
        fps = self._fps()

        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), BACKGROUND)
        self._draw_readout(p, now, fps)
        p.translate(self.width() / 2, self.height() / 2)

        radius = min(self.width(), self.height()) / 2 * 0.96
        hub = radius * HUB_FRACTION
        ring_width = (radius - hub) / len(RINGS)

        for idx, ring in enumerate(RINGS):
            r_out = radius - idx * ring_width
            st = ring.state(now)
            if st.fixed:
                self._draw_lit_ring(p, r_out - ring_width, r_out, ring.color, st)
            else:
                shade = self._sun.night if ring.name == "Hour" else None
                noon = self._sun.noon if ring.name == "Hour" else None
                self._draw_ring(p, r_out - ring_width, r_out, ring.color, st, shade, noon)

        self._draw_indicator(p, hub + ring_width, radius)
        self._draw_domino_rings(p, hub * 0.96, now.second + now.microsecond / 1e6)
        p.end()

    @staticmethod
    def _draw_band(p: QPainter, r_in: float, r_out: float, fill: QColor | QConicalGradient, gap: float) -> None:
        band = QPainterPath()
        band.addEllipse(QPointF(0, 0), r_out - gap, r_out - gap)
        band.addEllipse(QPointF(0, 0), r_in + gap, r_in + gap)
        if isinstance(fill, QColor):
            fill = QColor(fill)
            fill.setAlpha(38)
        p.fillPath(band, fill)

    @staticmethod
    def _season_gradient(colors: list[QColor]) -> QConicalGradient:
        # Qt conical gradients run counter-clockwise from 3 o'clock; division i is centered (i + 0.5) / n CCW from 12.
        grad = QConicalGradient(QPointF(0, 0), 90.0)
        n = len(colors)
        for i, c in enumerate(colors):
            stop = QColor(c)
            stop.setAlpha(110)
            grad.setColorAt((i + 0.5) / n, stop)
        wrap = _mix(colors[-1], colors[0], 0.5)
        wrap.setAlpha(110)
        grad.setColorAt(0.0, wrap)
        grad.setColorAt(1.0, wrap)
        return grad

    def _draw_ring(self, p: QPainter, r_in: float, r_out: float, color: QColor, st: RingState,
                   shade: tuple[float, float] | None = None, sun_at: float | None = None) -> None:
        gap = (r_out - r_in) * 0.04
        if st.colors is None:
            self._draw_band(p, r_in, r_out, color, gap)

        width = r_out - r_in
        major_len = width * 0.28
        minor_len = width * 0.14
        text_r = r_in + width * 0.40
        text_h = width * 0.45
        solid, round_cap = Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap
        major_pen = QPen(color, max(1.0, width * 0.035), solid, round_cap)
        minor_pen = QPen(color.darker(160), max(1.0, width * 0.02), solid, round_cap)
        top = r_out - gap * 2

        p.save()
        # Values are laid out counter-clockwise so the disc turns clockwise to bring them to the top.
        p.rotate(st.position / st.count * 360.0)
        if st.colors is not None:
            self._draw_band(p, r_in, r_out, self._season_gradient(st.colors), gap)
        if shade is not None:
            self._draw_shade(p, r_in + gap, r_out - gap, st.count, shade)
        p.setFont(self._label_font)
        total = st.count * st.subdiv
        step = 360.0 / total
        current = int(st.position) % st.count
        for k in range(total):
            i, minor = divmod(k, st.subdiv)
            p.save()
            p.rotate(-k * step)
            if st.colors is not None:
                major_pen.setColor(st.colors[i])
                minor_pen.setColor(st.colors[i].darker(130))
            if minor:
                p.setPen(minor_pen)
                p.drawLine(QPointF(0, -top), QPointF(0, -top + minor_len))
            else:
                p.setPen(major_pen)
                p.drawLine(QPointF(0, -top), QPointF(0, -top + major_len))
                if i % st.label_every == 0:
                    label_color = st.colors[i].lighter(130) if st.colors is not None else color
                    p.setPen(label_color.lighter(150) if i == current else label_color)
                    p.drawText(QRectF(-width * 1.5, -text_r - text_h / 2, width * 3, text_h),
                               Qt.AlignmentFlag.AlignCenter, st.label(i))
            p.restore()
        if sun_at is not None:
            p.rotate(-sun_at / st.count * 360.0)
            self._draw_sun(p, QPointF(0, -(r_out - width * 0.2)), width * 0.1)
        p.restore()

    @staticmethod
    def _draw_sun(p: QPainter, c: QPointF, r: float) -> None:
        sun = QColor("#ffd23f")
        p.setPen(QPen(sun, max(1.0, r * 0.3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for k in range(8):
            a = k * math.pi / 4
            dx, dy = math.cos(a), math.sin(a)
            p.drawLine(QPointF(c.x() + dx * r * 1.4, c.y() + dy * r * 1.4),
                       QPointF(c.x() + dx * r * 1.9, c.y() + dy * r * 1.9))
        p.setPen(QPen(BACKGROUND, max(1.0, r * 0.25)))
        p.setBrush(sun)
        p.drawEllipse(c, r, r)

    def _draw_lit_ring(self, p: QPainter, r_in: float, r_out: float, color: QColor, st: RingState) -> None:
        width = r_out - r_in
        gap = width * 0.04
        self._draw_band(p, r_in, r_out, color, gap)

        dim, bright = color.darker(220), color.lighter(170)
        top = r_out - gap * 2
        text_r = r_in + width * 0.40
        text_h = width * 0.45
        total = st.count * st.subdiv
        step = 360.0 / total
        tick_pos = st.position * st.subdiv
        solid, round_cap = Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap

        p.setFont(self._label_font)
        for k in range(total):
            i, minor = divmod(k, st.subdiv)
            glow = _glow(tick_pos - k, total, trail=8, fade_in=1)
            p.save()
            p.rotate(k * step)
            p.setPen(QPen(_mix(dim, bright, glow), max(1.0, width * (0.02 if minor else 0.035)), solid, round_cap))
            p.drawLine(QPointF(0, -top), QPointF(0, -top + width * (0.14 if minor else 0.28)))
            if not minor and i % st.label_every == 0:
                p.setPen(_mix(dim, bright, _glow(st.position - i, st.count, trail=1.5, fade_in=0.25)))
                p.drawText(QRectF(-width * 1.5, -text_r - text_h / 2, width * 3, text_h),
                           Qt.AlignmentFlag.AlignCenter, st.label(i))
            p.restore()

    @staticmethod
    def _draw_shade(p: QPainter, r_in: float, r_out: float, count: int, span: tuple[float, float]) -> None:
        start, end = span
        # Qt arc angles: degrees counter-clockwise from 3 o'clock; index 0 sits at 12 o'clock.
        start_deg = 90.0 + start / count * 360.0
        sweep = (end - start) % count / count * 360.0
        outer = QRectF(-r_out, -r_out, 2 * r_out, 2 * r_out)
        inner = QRectF(-r_in, -r_in, 2 * r_in, 2 * r_in)
        path = QPainterPath()
        path.arcMoveTo(outer, start_deg)
        path.arcTo(outer, start_deg, sweep)
        path.arcTo(inner, start_deg + sweep, -sweep)
        path.closeSubpath()
        p.fillPath(path, NIGHT_SHADE)

    def _draw_indicator(self, p: QPainter, start: float, radius: float) -> None:
        p.setPen(QPen(INDICATOR, max(1.5, radius * 0.004)))
        p.drawLine(QPointF(0, -start), QPointF(0, -radius))
        s = radius * 0.025
        p.setBrush(INDICATOR)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(-s, -radius - s * 1.2), QPointF(s, -radius - s * 1.2), QPointF(0, -radius + s * 0.4)]))

    @staticmethod
    def _draw_domino_rings(p: QPainter, r: float, seconds: float) -> None:
        count = 60
        hole = r * 0.12
        pitch = (r - hole) / count
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#12151d"))
        p.drawEllipse(QPointF(0, 0), r, r)
        p.setBrush(QColor("#000000"))
        p.drawEllipse(QPointF(0, 0), hole, hole)
        p.setBrush(Qt.BrushStyle.NoBrush)

        base = QColor("#13161c")
        idle, lit = QColor("#1f5a32"), QColor("#7dff9e")
        seg_deg = 10.0
        duration = 1.0
        fade = 0.08  # seconds to light up / dim at the start / end of a turn
        # Ring n turns once during second n, accelerating then decelerating, and hands over to ring n + 1 at rest.
        for n in range(count):
            local = (seconds - n) % count
            ring_r = hole + (n + 0.5) * pitch
            accent, body, turn = idle, base, 0.0
            if local < duration:
                turn = 360.0 * (0.5 - 0.5 * math.cos(math.pi * local / duration))
                accent = _mix(idle, lit, min(1.0, local / fade, (duration - local) / fade))
                body = _mix(base, idle, 0.5 * math.sin(math.pi * local / duration))

            rect = QRectF(-ring_r, -ring_r, 2 * ring_r, 2 * ring_r)
            # Qt arcs: 1/16 degree units, counter-clockwise from 3 o'clock; segment centered at 12 o'clock at rest.
            start = 90.0 - seg_deg / 2 - turn
            p.setPen(QPen(body, pitch * 0.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(rect, int((start - (360.0 - seg_deg)) * 16), int((360.0 - seg_deg) * 16))
            p.setPen(QPen(accent, pitch * 0.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(rect, int(start * 16), int(seg_deg * 16))

    def _draw_readout(self, p: QPainter, now: datetime, fps: float) -> None:
        margin = 14
        p.setFont(self._center_font)
        p.setPen(QColor("#e8ecf4"))
        line_h = self._center_font.pixelSize() * 1.3
        p.drawText(QRectF(margin, margin, self.width(), line_h), Qt.AlignmentFlag.AlignLeft,
                   now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}")
        p.setFont(self._small_font)
        p.setPen(QColor("#9aa3b5"))
        p.drawText(QRectF(margin, margin + line_h, self.width(), line_h), Qt.AlignmentFlag.AlignLeft,
                   now.strftime("%a %d %b %Y"))
        p.drawText(QRectF(margin, self.height() - margin - line_h, self.width(), line_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, f"{fps:5.1f} FPS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, help="latitude for sunrise/sunset (default: IP geolocation)")
    parser.add_argument("--lon", type=float, help="longitude for sunrise/sunset (default: IP geolocation)")
    args, qt_args = parser.parse_known_args()
    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon must be given together")
    if args.lat is not None and not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180):
        parser.error("--lat must be in [-90, 90] and --lon in [-180, 180]")

    fmt = QSurfaceFormat()
    fmt.setSamples(4)        # MSAA for smooth edges; 8x halves the frame rate on integrated GPUs
    fmt.setSwapInterval(0)   # use a timer-driven 60 FPS cap instead of display-refresh-driven redraws
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv[:1] + qt_args)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Python only runs signal handlers while executing bytecode; wake it periodically (e.g. when minimized).
    wakeup = QTimer()
    wakeup.timeout.connect(lambda: None)
    wakeup.start(200)

    clock = DiscClock(SunTimes(args.lat, args.lon))
    clock.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
