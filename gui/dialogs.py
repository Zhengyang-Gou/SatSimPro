"""Dialog classes used by MainWindow."""
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _configure_form_layout(layout: QFormLayout) -> None:
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setHorizontalSpacing(16)
    layout.setVerticalSpacing(11)
    layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)


def _configure_box_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(20, 18, 20, 20)
    layout.setSpacing(14)


def _dialog_buttons(dialog: QDialog) -> QDialogButtonBox:
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok_button = btns.button(QDialogButtonBox.Ok)
    if ok_button is not None:
        ok_button.setText("确定")
        ok_button.setObjectName("primaryButton")
        ok_button.setDefault(True)
    cancel_button = btns.button(QDialogButtonBox.Cancel)
    if cancel_button is not None:
        cancel_button.setText("取消")
    btns.accepted.connect(dialog.accept)
    btns.rejected.connect(dialog.reject)
    return btns


class WalkerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("生成 Walker 星座")
        self.setMinimumWidth(480)
        layout = QFormLayout(self)
        _configure_form_layout(layout)

        self.spin_t = QSpinBox()
        self.spin_t.setRange(1, 10000)
        self.spin_t.setValue(1200)

        self.spin_p = QSpinBox()
        self.spin_p.setRange(1, 1000)
        self.spin_p.setValue(60)

        self.spin_f = QSpinBox()
        self.spin_f.setRange(0, 1000)
        self.spin_f.setValue(0)

        self.spin_alt = QDoubleSpinBox()
        self.spin_alt.setRange(100, 20000)
        self.spin_alt.setValue(508.0)
        self.spin_alt.setSuffix(" km")

        self.spin_inc = QDoubleSpinBox()
        self.spin_inc.setRange(0, 180)
        self.spin_inc.setValue(55.0)
        self.spin_inc.setSuffix(" °")

        layout.addRow("卫星总数 (T)：", self.spin_t)
        layout.addRow("轨道面数 (P)：", self.spin_p)
        layout.addRow("相位因子 (F)：", self.spin_f)
        layout.addRow("轨道高度：", self.spin_alt)
        layout.addRow("轨道倾角：", self.spin_inc)

        layout.addRow(_dialog_buttons(self))


class TopologyDialog(QDialog):
    def __init__(
        self,
        latitude_fuse_enabled: bool = False,
        latitude_threshold: float = 70.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("网络拓扑设置")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        _configure_box_layout(layout)

        strategy_label = QLabel("连接策略：Grid Delta")
        strategy_label.setObjectName("hintLabel")
        layout.addWidget(strategy_label)

        delta_group = QGroupBox("Delta 拓扑")
        delta_layout = QFormLayout(delta_group)
        _configure_form_layout(delta_layout)

        self.chk_latitude_fuse = QCheckBox("启用纬度熔断")
        self.chk_latitude_fuse.setChecked(latitude_fuse_enabled)

        self.spin_latitude_threshold = QDoubleSpinBox()
        self.spin_latitude_threshold.setRange(0.0, 90.0)
        self.spin_latitude_threshold.setDecimals(1)
        self.spin_latitude_threshold.setValue(latitude_threshold)
        self.spin_latitude_threshold.setSuffix(" °")

        delta_layout.addRow(self.chk_latitude_fuse)
        delta_layout.addRow("纬度阈值：", self.spin_latitude_threshold)
        layout.addWidget(delta_group)

        layout.addWidget(_dialog_buttons(self))


class LinkDatasetExportDialog(QDialog):
    def __init__(self, constellation_config: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("导出链路状态数据集")
        self.setMinimumWidth(520)
        self.path = ""
        self.constellation_config = dict(constellation_config)

        layout = QVBoxLayout(self)
        _configure_box_layout(layout)

        constellation_group = QGroupBox("星座参数")
        constellation_layout = QFormLayout(constellation_group)
        _configure_form_layout(constellation_layout)

        constellation_layout.addRow(
            "卫星总数 (T)：",
            QLabel(str(self.constellation_config["total"])),
        )
        constellation_layout.addRow(
            "轨道面数：",
            QLabel(str(self.constellation_config["orbit_num"])),
        )
        constellation_layout.addRow(
            "每轨卫星数：",
            QLabel(str(self.constellation_config["sat_per_orbit"])),
        )
        constellation_layout.addRow(
            "相位因子 (F)：",
            QLabel(str(self.constellation_config["phase_factor"])),
        )
        constellation_layout.addRow(
            "轨道高度：",
            QLabel(f"{self.constellation_config['altitude_km']:.1f} km"),
        )
        constellation_layout.addRow(
            "轨道倾角：",
            QLabel(f"{self.constellation_config['inclination_deg']:.1f} °"),
        )
        layout.addWidget(constellation_group)

        simulation_group = QGroupBox("仿真参数")
        simulation_layout = QFormLayout(simulation_group)
        _configure_form_layout(simulation_layout)

        self.spin_time_slices = QSpinBox()
        self.spin_time_slices.setRange(1, 1_000_000)
        self.spin_time_slices.setValue(6000)

        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.1, 31_536_000.0)
        self.spin_duration.setDecimals(1)
        self.spin_duration.setValue(6000.0)
        self.spin_duration.setSuffix(" s")

        simulation_layout.addRow("时间片数量：", self.spin_time_slices)
        simulation_layout.addRow("仿真总时长：", self.spin_duration)
        layout.addWidget(simulation_group)

        failure_group = QGroupBox("随机链路失效")
        failure_layout = QFormLayout(failure_group)
        _configure_form_layout(failure_layout)

        self.chk_random_failure = QCheckBox("启用随机链路失效")

        self.spin_failure_probability = QDoubleSpinBox()
        self.spin_failure_probability.setRange(0.0, 1.0)
        self.spin_failure_probability.setDecimals(6)
        self.spin_failure_probability.setSingleStep(0.01)
        self.spin_failure_probability.setValue(0.01)

        self.spin_random_seed = QSpinBox()
        self.spin_random_seed.setRange(0, 2_147_483_647)
        self.spin_random_seed.setValue(42)

        failure_layout.addRow(self.chk_random_failure)
        failure_layout.addRow("单片失效概率：", self.spin_failure_probability)
        failure_layout.addRow("随机种子：", self.spin_random_seed)
        layout.addWidget(failure_group)

        output_group = QGroupBox("输出")
        output_layout = QFormLayout(output_group)
        _configure_form_layout(output_layout)

        self.btn_path = QPushButton("选择目录...")
        self.btn_path.clicked.connect(self._select_directory)

        self.lbl_path = QLabel("未选择")
        self.lbl_path.setWordWrap(True)

        output_layout.addRow("保存到：", self.btn_path)
        output_layout.addRow("", self.lbl_path)
        layout.addWidget(output_group)

        layout.addWidget(_dialog_buttons(self))

    def _select_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self)
        if directory:
            self.path = directory
            self.lbl_path.setText(directory)

    def config(self) -> Dict[str, Any]:
        return {
            "time_slices": self.spin_time_slices.value(),
            "duration_sec": self.spin_duration.value(),
            "random_failure_enabled": self.chk_random_failure.isChecked(),
            "failure_probability": self.spin_failure_probability.value(),
            "random_seed": self.spin_random_seed.value(),
            "output_dir": self.path,
        }
