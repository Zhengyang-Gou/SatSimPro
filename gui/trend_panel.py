"""Compact, number-free trend charts shown beside the globe."""

from collections import deque
from typing import Deque, Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class TrendChart(QWidget):
    """A small auto-scaling sparkline card without numeric labels."""

    def __init__(self, title: str, subtitle: str, color: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.color = QColor(color)
        self.values: Deque[Optional[float]] = deque(maxlen=60)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def append_value(self, value: Optional[float]) -> None:
        try:
            normalized = float(value) if value is not None else None
        except (TypeError, ValueError):
            normalized = None
        self.values.append(normalized)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter.setPen(QPen(QColor("#353b47"), 1))
        painter.setBrush(QColor("#20242c"))
        painter.drawRoundedRect(bounds, 12, 12)

        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.DemiBold))
        painter.setPen(QColor("#f2f4f8"))
        painter.drawText(QRectF(14, 10, bounds.width() - 28, 22), Qt.AlignLeft, self.title)

        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.setPen(QColor("#7f8998"))
        painter.drawText(QRectF(14, 31, bounds.width() - 28, 18), Qt.AlignLeft, self.subtitle)

        chart = QRectF(14, 54, max(1, bounds.width() - 28), max(1, bounds.height() - 66))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1, Qt.DotLine))
        for ratio in (0.25, 0.5, 0.75):
            y = chart.top() + chart.height() * ratio
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

        samples = list(self.values)
        valid = [value for value in samples if value is not None]
        if not valid:
            painter.setPen(QColor("#626b78"))
            painter.drawText(chart, Qt.AlignCenter, "等待仿真数据")
            return

        low, high = min(valid), max(valid)
        padding = max((high - low) * 0.18, abs(high) * 0.04, 0.5)
        low -= padding
        high += padding
        span = max(high - low, 1e-9)
        slots = max(len(samples) - 1, 59)

        segments = []
        current = []
        start_slot = 60 - len(samples)
        for index, value in enumerate(samples):
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            x = chart.left() + chart.width() * (start_slot + index) / slots
            y = chart.bottom() - chart.height() * (value - low) / span
            current.append(QPointF(x, y))
        if current:
            segments.append(current)

        for points in segments:
            if len(points) < 2:
                continue
            line = QPainterPath(points[0])
            for point in points[1:]:
                line.lineTo(point)

            fill = QPainterPath(line)
            fill.lineTo(points[-1].x(), chart.bottom())
            fill.lineTo(points[0].x(), chart.bottom())
            fill.closeSubpath()
            gradient = QLinearGradient(0, chart.top(), 0, chart.bottom())
            top_color = QColor(self.color)
            top_color.setAlpha(72)
            bottom_color = QColor(self.color)
            bottom_color.setAlpha(0)
            gradient.setColorAt(0, top_color)
            gradient.setColorAt(1, bottom_color)
            painter.fillPath(fill, gradient)
            painter.setPen(QPen(self.color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(line)


class NetworkTrendPanel(QWidget):
    """Four coordinated network trend cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("networkTrendPanel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(9)

        specs = (
            ("latency", "平均时延", "链路传播时延趋势", "#64d2ff"),
            ("availability", "链路可用率", "当前拓扑连通趋势", "#30d158"),
            ("loss", "网络丢包", "Redis 丢包趋势", "#ff9f0a"),
            ("active", "活动链路", "在线链路规模趋势", "#bf5af2"),
        )
        self.charts: Dict[str, TrendChart] = {}
        for key, title, subtitle, color in specs:
            chart = TrendChart(title, subtitle, color, self)
            self.charts[key] = chart
            layout.addWidget(chart, 1)

    def update_metrics(
        self,
        *,
        average_latency: Optional[float],
        availability: Optional[float],
        average_loss: Optional[float],
        active_links: int,
    ) -> None:
        self.charts["latency"].append_value(average_latency)
        self.charts["availability"].append_value(availability)
        self.charts["loss"].append_value(average_loss)
        self.charts["active"].append_value(active_links)
