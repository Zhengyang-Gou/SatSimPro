"""Custom table delegates used by the link table."""

from typing import Optional

from PySide6.QtCore import QObject, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from core.metrics import STATUS_TEXT, valid_metric

DOWN_TEXT = "中断"


class BarDelegate(QStyledItemDelegate):
    """Shared bar renderer for latency and Redis percentage columns."""

    def __init__(self, max_value: float, suffix: str, decimals: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.max_value = max_value
        self.suffix = suffix
        self.decimals = decimals

    def paint(self, painter: QPainter, option, index) -> None:
        data = valid_metric(index.data(Qt.EditRole))
        value_is_down = isinstance(data, str)

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.fillRect(
            option.rect,
            QColor("#263243")
            if option.state & QStyle.State_Selected
            else QColor("#1a1d23") if index.row() % 2 == 1 else QColor("#15181d"),
        )

        if value_is_down:
            ratio = 1.0
            color = QColor("#5f2d32")
            text = STATUS_TEXT[data]
        else:
            try:
                value = float(data)
            except (TypeError, ValueError):
                painter.restore()
                super().paint(painter, option, index)
                return

            ratio = min(max(value / self.max_value, 0.0), 1.0)
            low = QColor("#2f4f46")
            high = QColor("#6b4a28")
            color = QColor(
                int(low.red() + (high.red() - low.red()) * ratio),
                int(low.green() + (high.green() - low.green()) * ratio),
                int(low.blue() + (high.blue() - low.blue()) * ratio),
            )
            text = f"{value:.{self.decimals}f} {self.suffix}".rstrip()

        bar_rect = QRect(
            option.rect.x() + 4,
            option.rect.y() + 4,
            int((option.rect.width() - 8) * ratio),
            option.rect.height() - 8,
        )
        painter.setBrush(color)
        painter.drawRoundedRect(bar_rect, 4, 4)

        painter.setPen(QColor("#e8f0fe"))
        painter.drawText(option.rect, Qt.AlignCenter, text)
        painter.restore()


class LatencyDelegate(BarDelegate):
    def __init__(self, max_latency: float = 25.0, parent: Optional[QObject] = None):
        super().__init__(max_latency, "ms", 4, parent)


class RatioDelegate(BarDelegate):
    """
    显示 Redis 延迟 / 计算延迟 的百分比。

    100% 表示 Redis 读取延迟和本地计算延迟相同。
    越高越红。
    """

    def __init__(self, max_percent: float = 200.0, parent: Optional[QObject] = None):
        super().__init__(max_percent, "%", 2, parent)
