"""Redis-backed link metric rankings shown beside the globe."""

from math import floor, log10, isfinite
from typing import Any, Dict, List, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .link_state import is_down

MetricEntry = Tuple[str, float]


def ranked_metric_data(
    records: Sequence[Dict[str, Any]],
    field: str,
    *,
    limit: int = 5,
) -> List[MetricEntry]:
    """Return the highest links followed by the average of every valid Redis value."""
    values: List[MetricEntry] = []
    for record in records:
        raw_value = record.get(field)
        if is_down(raw_value):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not isfinite(value) or value < 0:
            continue
        values.append((str(record.get("id", "未知链路")), value))

    if not values:
        return []

    ranked = sorted(values, key=lambda item: (-item[1], item[0]))[:limit]
    average = sum(value for _label, value in values) / len(values)
    return [*ranked, ("平均", average)]


class RankingBarChart(QWidget):
    """A compact ranking chart with labeled horizontal and vertical axes."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        unit: str,
        y_axis_label: str,
        color: str,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.unit = unit
        self.y_axis_label = y_axis_label
        self.color = QColor(color)
        self.entries: List[MetricEntry] = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_entries(self, entries: Sequence[MetricEntry]) -> None:
        self.entries = list(entries)
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

        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.setPen(QColor("#7f8998"))
        painter.drawText(QRectF(14, 31, bounds.width() - 28, 18), Qt.AlignLeft, self.subtitle)

        chart = QRectF(58, 58, max(1, bounds.width() - 72), max(1, bounds.height() - 108))
        if not self.entries:
            self._draw_axes(painter, chart, 1.0)
            painter.setPen(QColor("#626b78"))
            painter.drawText(chart, Qt.AlignCenter, "等待 Redis 数据")
            self._draw_axis_titles(painter, chart)
            return

        maximum = max((value for _label, value in self.entries), default=0.0)
        scale_max = self._nice_axis_max(maximum)
        count = len(self.entries)
        slot_width = chart.width() / max(count, 1)
        bar_width = min(38.0, max(12.0, slot_width * 0.58))
        baseline = chart.bottom()
        usable_height = max(10.0, chart.height())

        self._draw_axes(painter, chart, scale_max)

        painter.setFont(QFont("Microsoft YaHei UI", 7))
        painter.setPen(QPen(QColor("#66809f"), 1.2))
        for tick in range(count):
            center_x = chart.left() + slot_width * (tick + 0.5)
            painter.drawLine(QPointF(center_x, baseline), QPointF(center_x, baseline + 4))

        for index, (label, value) in enumerate(self.entries):
            center_x = chart.left() + slot_width * (index + 0.5)
            height = usable_height * max(value, 0.0) / scale_max
            bar = QRectF(
                center_x - bar_width / 2,
                baseline - max(height, 1.5),
                bar_width,
                max(height, 1.5),
            )

            bar_color = QColor("#8e8e93") if label == "平均" else QColor(self.color)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(bar, 4, 4)

            painter.setPen(QColor("#e5e5e7"))
            value_rect = QRectF(
                center_x - slot_width / 2,
                max(chart.top() - 2, bar.top() - 18),
                slot_width,
                16,
            )
            painter.drawText(
                value_rect,
                Qt.AlignHCenter | Qt.AlignBottom,
                f"{value:.2f}{self.unit}",
            )

            painter.setPen(QColor("#aeb6c2"))
            label_rect = QRectF(center_x - slot_width / 2, baseline + 6, slot_width, 18)
            painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, label)

        self._draw_axis_titles(painter, chart)

    def _draw_axis_titles(self, painter: QPainter, chart: QRectF) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 7))
        painter.setPen(QColor("#8290a3"))
        painter.drawText(
            QRectF(chart.left(), chart.bottom() + 27, chart.width(), 15),
            Qt.AlignCenter,
            "链路",
        )

        painter.save()
        painter.translate(8, chart.center().y())
        painter.rotate(-90)
        painter.drawText(
            QRectF(-chart.height() / 2, 0, chart.height(), 14),
            Qt.AlignCenter,
            self.y_axis_label,
        )
        painter.restore()

    def _draw_axes(self, painter: QPainter, chart: QRectF, scale_max: float) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 7))
        for tick in range(5):
            ratio = tick / 4
            y = chart.bottom() - chart.height() * ratio
            tick_value = scale_max * ratio
            painter.setPen(QPen(QColor(91, 116, 148, 65), 1, Qt.DotLine))
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
            painter.setPen(QColor("#8290a3"))
            painter.drawText(
                QRectF(18, y - 8, 35, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                self._tick_text(tick_value),
            )

        painter.setPen(QPen(QColor("#66809f"), 1.2))
        painter.drawLine(QPointF(chart.left(), chart.top()), QPointF(chart.left(), chart.bottom()))
        painter.drawLine(QPointF(chart.left(), chart.bottom()), QPointF(chart.right(), chart.bottom()))

    @staticmethod
    def _nice_axis_max(maximum: float) -> float:
        if not isfinite(maximum) or maximum <= 0:
            return 1.0
        raw = maximum * 1.15
        magnitude = 10 ** floor(log10(raw))
        normalized = raw / magnitude
        step = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
        return float(step * magnitude)

    @staticmethod
    def _tick_text(value: float) -> str:
        if value >= 10:
            return f"{value:.0f}"
        if value >= 1:
            return f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")


class NetworkTrendPanel(QWidget):
    """Two Redis ranking charts: packet loss and measured latency."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("networkTrendPanel")
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(9)

        self.loss_chart = RankingBarChart(
            "Redis 丢包排行",
            "丢包率最高的 5 条链路及全部链路平均值",
            "%",
            "丢包率 (%)",
            "#ff9f0a",
            self,
        )
        self.latency_chart = RankingBarChart(
            "Redis 时延排行",
            "实测时延最高的 5 条链路及全部链路平均值",
            "ms",
            "时延 (ms)",
            "#64d2ff",
            self,
        )
        layout.addWidget(self.loss_chart, 1)
        layout.addWidget(self.latency_chart, 1)

    def update_metrics(
        self,
        *,
        loss_entries: Sequence[MetricEntry],
        latency_entries: Sequence[MetricEntry],
    ) -> None:
        self.loss_chart.set_entries(loss_entries)
        self.latency_chart.set_entries(latency_entries)
