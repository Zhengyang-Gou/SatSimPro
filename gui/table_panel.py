"""Reusable widget that owns the link table, filter box, stats label, and pagination."""

from typing import List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QVBoxLayout,
    QWidget,
)

from .delegates import LatencyDelegate, RatioDelegate
from .link_state import LinkKey, LinkRecord, directed_link_key, is_down
from .theme import DOWN, TABLE_HEADERS


class LinkTablePanel(QWidget):
    """Link table with filtering, pagination, selection preservation, and stats text."""

    selection_changed = Signal(object)

    def __init__(self, page_size: int = 10, parent=None):
        super().__init__(parent)
        self.setObjectName("linkTablePanel")
        self.page_size = page_size
        self.current_page = 1
        self.records: List[LinkRecord] = []
        self.active_count: Optional[int] = None
        self.selected_link_pairs: Set[LinkKey] = set()
        self.redis_in_flight = False
        self.redis_enabled = False
        self.redis_last_error = ""
        self._filter_cache_query = ""
        self._filter_cache_records_id = 0
        self._filter_cache_result: List[LinkRecord] = []

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(9)
        layout.addLayout(self._build_toolbar())

        self.table = self._create_table()
        layout.addWidget(self.table)
        layout.addLayout(self._build_pagination_bar())

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        title = QLabel("链路详情")
        title.setObjectName("panelTitle")

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("搜索卫星或链路 ID")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setMinimumWidth(280)
        self.txt_search.setMaximumWidth(420)
        self.txt_search.textChanged.connect(self._on_search_changed)

        self.lbl_active_chip = QLabel("● 0 活动")
        self.lbl_active_chip.setObjectName("activeChip")

        self.lbl_total_chip = QLabel("0 条链路")
        self.lbl_total_chip.setObjectName("metricChip")

        self.lbl_redis_chip = QLabel("● Redis 空闲")
        self.lbl_redis_chip.setObjectName("redisChip")

        toolbar.addWidget(title)
        toolbar.addWidget(self.txt_search)
        toolbar.addStretch()
        toolbar.addWidget(self.lbl_active_chip)
        toolbar.addWidget(self.lbl_total_chip)
        toolbar.addWidget(self.lbl_redis_chip)
        return toolbar

    def _create_table(self) -> QTableWidget:
        table = QTableWidget(0, len(TABLE_HEADERS))

        available_fonts = set(QFontDatabase.families())
        table_family = next(
            (
                family
                for family in (
                    "SF Pro Text",
                    "PingFang SC",
                    "Microsoft YaHei UI",
                    "Noto Sans SC",
                    "Segoe UI",
                )
                if family in available_fonts
            ),
            "sans-serif",
        )
        table_font = QFont(table_family, 10)
        table.setFont(table_font)

        table.setAlternatingRowColors(True)
        table.setHorizontalHeaderLabels(TABLE_HEADERS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setDefaultSectionSize(36)
        table.verticalHeader().setVisible(False)

        table.setItemDelegateForColumn(3, LatencyDelegate(25.0, table))
        table.setItemDelegateForColumn(4, RatioDelegate(200.0, table))
        table.setItemDelegateForColumn(5, RatioDelegate(100.0, table))

        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.wheelEvent = lambda event: event.ignore()
        table.itemSelectionChanged.connect(self._on_table_selection)
        return table

    def _build_pagination_bar(self) -> QHBoxLayout:
        page_layout = QHBoxLayout()
        page_layout.setSpacing(8)

        self.btn_prev = QPushButton("上一页")
        self.btn_prev.setObjectName("pageButton")
        self.btn_prev.clicked.connect(lambda: self.change_page(-1))

        self.lbl_page = QLabel("第 1 / 1 页")
        self.lbl_page.setObjectName("metricChip")

        self.btn_next = QPushButton("下一页")
        self.btn_next.setObjectName("pageButton")
        self.btn_next.clicked.connect(lambda: self.change_page(1))

        page_layout.addStretch()
        page_layout.addWidget(self.btn_prev)
        page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.btn_next)
        page_layout.addStretch()
        return page_layout

    def reset(self) -> None:
        self.records = []
        self.active_count = None
        self.selected_link_pairs.clear()
        self.current_page = 1
        self.redis_in_flight = False
        self.redis_enabled = False
        self.redis_last_error = ""
        self._invalidate_filter_cache()
        self.refresh()

    def set_records(
        self,
        records: List[LinkRecord],
        *,
        redis_in_flight: bool = False,
        redis_enabled: bool = False,
        redis_last_error: str = "",
        active_count: Optional[int] = None,
    ) -> None:
        if self.records is not records:
            self._invalidate_filter_cache()
        self.records = records
        self.active_count = active_count
        self.redis_in_flight = redis_in_flight
        self.redis_enabled = redis_enabled
        self.redis_last_error = redis_last_error
        self.refresh()

    def change_page(self, delta: int) -> None:
        self.current_page += delta
        self.refresh()

    def _on_search_changed(self) -> None:
        self.current_page = 1
        self.refresh()

    def _invalidate_filter_cache(self) -> None:
        self._filter_cache_query = ""
        self._filter_cache_records_id = 0
        self._filter_cache_result = []

    def _filtered_records(self) -> List[LinkRecord]:
        query = self.txt_search.text().strip().lower()
        if not query:
            return self.records

        records_id = id(self.records)
        if (
            query == self._filter_cache_query
            and records_id == self._filter_cache_records_id
        ):
            return self._filter_cache_result

        result: List[LinkRecord] = []
        for record in self.records:
            src_name = str(record["src_name"]).lower()
            tgt_name = str(record["tgt_name"]).lower()
            link_id = str(record["id"]).lower()
            forward = f"{src_name}-{tgt_name}"

            if query in link_id or query in src_name or query in tgt_name or query in forward:
                result.append(record)

        self._filter_cache_query = query
        self._filter_cache_records_id = records_id
        self._filter_cache_result = result
        return result

    def refresh(self) -> None:
        filtered = self._filtered_records()
        total_pages = max(1, (len(filtered) + self.page_size - 1) // self.page_size)
        self.current_page = max(1, min(self.current_page, total_pages))

        self.lbl_page.setText(f"第 {self.current_page} / {total_pages} 页")
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < total_pages)
        self._update_summary_chips()

        start_idx = (self.current_page - 1) * self.page_size
        page_data = filtered[start_idx : start_idx + self.page_size]

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setSortingEnabled(False)
            self.table.clearSelection()

            if self.table.rowCount() != len(page_data):
                self.table.setRowCount(len(page_data))

            for row, record in enumerate(page_data):
                self._ensure_table_row(row)
                self._write_table_row(row, record)

            for row, record in enumerate(page_data):
                if directed_link_key(record["src"], record["tgt"]) in self.selected_link_pairs:
                    self.table.setRangeSelected(
                        QTableWidgetSelectionRange(row, 0, row, self.table.columnCount() - 1),
                        True,
                    )
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

    def _active_count(self) -> int:
        return (
            self.active_count
            if self.active_count is not None
            else sum(1 for record in self.records if not is_down(record.get("latency")))
        )

    def _update_summary_chips(self) -> None:
        active_count = self._active_count()
        total_count = len(self.records)
        self.lbl_active_chip.setText(f"● {active_count} 活动")
        self.lbl_total_chip.setText(f"{total_count} 条链路")

        if self.redis_last_error:
            self.lbl_redis_chip.setText("● Redis 异常")
            self.lbl_redis_chip.setStyleSheet("color: #ff453a;")
        elif self.redis_in_flight:
            self.lbl_redis_chip.setText("● Redis 更新中")
            self.lbl_redis_chip.setStyleSheet("color: #ff9f0a;")
        elif self.redis_enabled:
            self.lbl_redis_chip.setText("● Redis 已连接")
            self.lbl_redis_chip.setStyleSheet("color: #30d158;")
        else:
            self.lbl_redis_chip.setText("● Redis 未连接")
            self.lbl_redis_chip.setStyleSheet("color: #98989d;")

    def _ensure_table_row(self, row: int) -> None:
        for col in range(len(TABLE_HEADERS)):
            if self.table.item(row, col) is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def _write_table_row(self, row: int, record: LinkRecord) -> None:
        values = [
            record["id"],
            record["src_name"],
            record["tgt_name"],
            record.get("latency", DOWN),
            record.get("redis_delay_ratio_pct", DOWN),
            record.get("redis_loss_pct", DOWN),
        ]

        for col, value in enumerate(values):
            item = self.table.item(row, col)
            if col in (0, 3, 4, 5):
                if item.data(Qt.EditRole) != value:
                    item.setData(Qt.EditRole, value)
            else:
                text = str(value)
                if item.text() != text:
                    item.setText(text)

        self.table.item(row, 1).setData(Qt.UserRole, record["src"])
        self.table.item(row, 2).setData(Qt.UserRole, record["tgt"])

    def _on_table_selection(self) -> None:
        selected: Set[LinkKey] = set()

        selected_rows = set()
        for selected_range in self.table.selectedRanges():
            selected_rows.update(range(selected_range.topRow(), selected_range.bottomRow() + 1))

        for row in selected_rows:
            src_item = self.table.item(row, 1)
            tgt_item = self.table.item(row, 2)
            if src_item is None or tgt_item is None:
                continue

            src = src_item.data(Qt.UserRole)
            tgt = tgt_item.data(Qt.UserRole)
            if src is not None and tgt is not None:
                selected.add(directed_link_key(int(src), int(tgt)))

        self.selected_link_pairs = selected
        self.selection_changed.emit(set(self.selected_link_pairs))
