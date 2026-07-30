"""End-to-end metric query shell with time-series charts."""

from collections import deque
from typing import Deque, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MetricCurveChart(QWidget):
    """A polished rolling curve chart for one end-to-end metric."""

    def __init__(self, title: str, unit: str, color: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.color = QColor(color)
        self.values: Deque[Optional[float]] = deque(maxlen=60)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def append_value(self, value: Optional[float]) -> None:
        try:
            normalized = float(value) if value is not None else None
        except (TypeError, ValueError):
            normalized = None
        self.values.append(normalized)
        self.update()

    def clear(self) -> None:
        self.values.clear()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter.setPen(QPen(QColor("#26364b"), 1))
        painter.setBrush(QColor("#121925"))
        painter.drawRoundedRect(bounds, 12, 12)

        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.DemiBold))
        painter.setPen(QColor("#f2f4f8"))
        painter.drawText(QRectF(14, 10, bounds.width() - 28, 22), Qt.AlignLeft, self.title)

        valid = [value for value in self.values if value is not None]
        latest = valid[-1] if valid else None
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        painter.setPen(self.color if latest is not None else QColor("#667386"))
        latest_text = f"{latest:.2f} {self.unit}" if latest is not None else f"-- {self.unit}"
        painter.drawText(
            QRectF(14, 10, bounds.width() - 28, 22),
            Qt.AlignRight | Qt.AlignVCenter,
            latest_text,
        )

        chart = QRectF(48, 48, max(1, bounds.width() - 62), max(1, bounds.height() - 82))
        low, high = self._value_range(valid)
        self._draw_axes(painter, chart, low, high)

        if not valid:
            painter.setFont(QFont("Microsoft YaHei UI", 8))
            painter.setPen(QColor("#626b78"))
            painter.drawText(chart, Qt.AlignCenter, "等待端到端数据")
            return

        samples = list(self.values)
        span = max(high - low, 1e-9)
        slots = max(len(samples) - 1, 59)
        start_slot = 60 - len(samples)
        segments = []
        current = []

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
            if len(points) == 1:
                painter.setPen(Qt.NoPen)
                painter.setBrush(self.color)
                painter.drawEllipse(points[0], 2.8, 2.8)
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
            bottom_color.setAlpha(2)
            gradient.setColorAt(0, top_color)
            gradient.setColorAt(1, bottom_color)
            painter.fillPath(fill, gradient)

            glow = QColor(self.color)
            glow.setAlpha(42)
            painter.setPen(QPen(glow, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(line)
            painter.setPen(QPen(self.color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(line)

            painter.setPen(QPen(QColor("#d9f5ff"), 1))
            painter.setBrush(self.color)
            painter.drawEllipse(points[-1], 3.4, 3.4)

    def _draw_axes(self, painter: QPainter, chart: QRectF, low: float, high: float) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 7))
        for tick in range(4):
            ratio = tick / 3
            y = chart.bottom() - chart.height() * ratio
            value = low + (high - low) * ratio
            painter.setPen(QPen(QColor(91, 116, 148, 58), 1, Qt.DotLine))
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
            painter.setPen(QColor("#8290a3"))
            painter.drawText(
                QRectF(5, y - 8, 37, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                self._tick_text(value),
            )

        painter.setPen(QPen(QColor("#66809f"), 1))
        painter.drawLine(QPointF(chart.left(), chart.top()), QPointF(chart.left(), chart.bottom()))
        painter.drawLine(QPointF(chart.left(), chart.bottom()), QPointF(chart.right(), chart.bottom()))
        painter.setPen(QColor("#8290a3"))
        painter.drawText(
            QRectF(chart.left(), chart.bottom() + 5, 44, 14),
            Qt.AlignLeft,
            "较早",
        )
        painter.drawText(
            QRectF(chart.right() - 44, chart.bottom() + 5, 44, 14),
            Qt.AlignRight,
            "现在",
        )
        painter.drawText(
            QRectF(chart.center().x() - 30, chart.bottom() + 5, 60, 14),
            Qt.AlignCenter,
            "时间",
        )

    @staticmethod
    def _value_range(values) -> tuple[float, float]:
        if not values:
            return 0.0, 1.0
        low = min(values)
        high = max(values)
        padding = max((high - low) * 0.16, abs(high) * 0.06, 0.1)
        return max(0.0, low - padding), high + padding

    @staticmethod
    def _tick_text(value: float) -> str:
        if value >= 100:
            return f"{value:.0f}"
        if value >= 10:
            return f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")


class EndToEndDelayPanel(QWidget):
    """Search UI plus public hooks for future end-to-end metric data."""

    query_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("endToEndDelayPanel")
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.current_query = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("endpointSearchInput")
        self.search_input.setPlaceholderText("搜索链路，例如：0101-0201")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._request_query)

        self.search_button = QPushButton("查询")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._request_query)
        header.addWidget(self.search_input, 1)
        header.addWidget(self.search_button)

        self.query_status = QLabel("选择链路后查看端到端指标")
        self.query_status.setObjectName("hintLabel")

        self.latency_chart = MetricCurveChart("端到端时延", "ms", "#64d2ff", self)
        self.loss_chart = MetricCurveChart("端到端丢包率", "%", "#ff9f0a", self)

        layout.addLayout(header)
        layout.addWidget(self.query_status)
        layout.addWidget(self.latency_chart, 1)
        layout.addWidget(self.loss_chart, 1)

    def _request_query(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self.query_status.setText("请先输入需要查询的链路")
            return

        self.current_query = query
        self.clear_metrics()
        self.query_status.setText(f"当前链路：{query}")
        self.query_requested.emit(query)

    def append_metrics(
        self,
        *,
        latency_ms: Optional[float],
        loss_pct: Optional[float],
    ) -> None:
        """Append one future query sample to both rolling curves."""
        self.latency_chart.append_value(latency_ms)
        self.loss_chart.append_value(loss_pct)

    def clear_metrics(self) -> None:
        self.latency_chart.clear()
        self.loss_chart.clear()
