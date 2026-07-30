"""Shared GUI constants and macOS-inspired dark stylesheet."""

DARK_THEME = """
QMainWindow, QDialog {
    background-color: #1c1c1e;
    color: #f5f5f7;
}
QWidget {
    color: #f5f5f7;
    font-family: "SF Pro Text", "SF Pro Display", ".AppleSystemUIFont", "PingFang SC", "Microsoft YaHei UI", "Noto Sans SC", "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget#workspace {
    background-color: #171719;
}
QWidget#sceneRow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f29, stop:1 #0f1218);
}
QWidget#networkTrendPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f29, stop:1 #0f1218);
    border: none;
}
QWidget#endToEndDelayPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f29, stop:1 #0f1218);
    border: none;
}
QWidget#linkTablePanel {
    background-color: #242426;
    border-top: 1px solid #38383a;
}
QMenuBar {
    background-color: #242426;
    border: none;
    border-bottom: 1px solid #38383a;
    padding: 2px 8px;
}
QMenuBar::item {
    background: transparent;
    border-radius: 6px;
    padding: 5px 10px;
}
QMenuBar::item:selected { background-color: #3a3a3c; }
QMenu {
    background-color: #2c2c2e;
    border: 1px solid #48484a;
    border-radius: 9px;
    padding: 6px;
}
QMenu::item {
    border-radius: 6px;
    padding: 7px 30px 7px 12px;
}
QMenu::item:selected { background-color: #0a84ff; color: white; }
QMenu::separator { height: 1px; background: #48484a; margin: 5px 8px; }
QToolBar {
    background-color: #242426;
    border: none;
    border-bottom: 1px solid #38383a;
    spacing: 5px;
    padding: 6px 10px;
}
QToolBar::separator { width: 1px; background: #48484a; margin: 7px 6px; }
QToolBar QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #e5e5e7;
    min-height: 28px;
    padding: 3px 8px;
}
QToolBar QToolButton:hover { background-color: #3a3a3c; }
QToolBar QToolButton:pressed,
QToolBar QToolButton:checked { background-color: #48484a; color: white; }
QToolBar QToolButton#primaryToolButton {
    background-color: #0a84ff;
    color: white;
    font-weight: 600;
    padding: 3px 13px;
}
QToolBar QToolButton#primaryToolButton:hover { background-color: #2692ff; }
QToolBar QToolButton#connectionToolButton:checked { color: #30d158; }
QStatusBar {
    background-color: #242426;
    border-top: 1px solid #38383a;
    color: #98989d;
    min-height: 22px;
}
QStatusBar::item { border: none; }
QSplitter::handle { background-color: #38383a; }
QSplitter::handle:vertical { height: 1px; }
QGroupBox {
    background-color: #242426;
    border: 1px solid #38383a;
    border-radius: 11px;
    margin-top: 18px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #f5f5f7;
}
QLabel { color: #e5e5e7; background: transparent; }
QLabel#panelTitle { color: #f5f5f7; font-size: 15px; font-weight: 600; }
QLabel#sectionTitle { color: #f5f5f7; font-size: 18px; font-weight: 600; }
QLabel#hintLabel { color: #98989d; }
QLabel#metricChip,
QLabel#activeChip,
QLabel#redisChip {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 5px 8px;
    color: #98989d;
}
QLabel#activeChip { color: #30d158; }
QLabel#redisChip { color: #64d2ff; }
QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox {
    background-color: #2c2c2e;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #f5f5f7;
    min-height: 28px;
    padding: 4px 9px;
    selection-background-color: #0a84ff;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { background-color: #323234; }
QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus { border-color: #0a84ff; background-color: #2c2c2e; }
QLineEdit:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled { background-color: #232325; color: #636366; }
QCheckBox { spacing: 8px; color: #e5e5e7; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid #636366;
    background-color: #2c2c2e;
}
QCheckBox::indicator:hover { border-color: #8e8e93; }
QCheckBox::indicator:checked { background-color: #0a84ff; border-color: #0a84ff; }
QPushButton {
    background-color: #2c2c2e;
    border: 1px solid #48484a;
    border-radius: 8px;
    color: #f5f5f7;
    min-height: 28px;
    padding: 4px 14px;
}
QPushButton:hover { background-color: #3a3a3c; border-color: #636366; }
QPushButton:pressed { background-color: #48484a; }
QPushButton:disabled { background-color: #232325; border-color: #38383a; color: #636366; }
QPushButton#primaryButton { background-color: #0a84ff; border-color: #0a84ff; color: white; font-weight: 600; }
QPushButton#primaryButton:hover { background-color: #2692ff; }
QPushButton#pageButton { min-width: 72px; background-color: transparent; }
QTableWidget {
    background-color: #242426;
    alternate-background-color: #272729;
    border: 1px solid #38383a;
    border-radius: 10px;
    gridline-color: transparent;
    outline: none;
    color: #e5e5e7;
    selection-background-color: rgba(10, 132, 255, 90);
}
QHeaderView::section {
    background-color: #2c2c2e;
    border: none;
    border-bottom: 1px solid #48484a;
    color: #98989d;
    font-weight: 600;
    padding: 8px 7px;
}
QTableWidget::item { border: none; border-bottom: 1px solid #303033; padding: 4px 7px; }
QTableWidget::item:hover { background-color: #303033; }
QTableWidget::item:selected { background-color: rgba(10, 132, 255, 90); color: white; }
QScrollBar:vertical, QScrollBar:horizontal { background: transparent; border: none; width: 10px; height: 10px; }
QScrollBar::handle { background-color: #636366; border-radius: 5px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background-color: #8e8e93; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QProgressBar { background: #2c2c2e; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #0a84ff; border-radius: 4px; }
QToolTip { background-color: #3a3a3c; color: white; border: 1px solid #636366; padding: 5px; }
"""

DOWN = "down"
TABLE_HEADERS = [
    "链路 ID",
    "源卫星",
    "目标卫星",
    "计算时延 (ms)",
    "Redis / 计算时延 (%)",
    "Redis 丢包 (%)",
]
