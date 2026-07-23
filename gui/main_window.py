"""Main application window after modularizing UI, table, topology, and Redis concerns."""

from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional, Set

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from core.calculator import OrbitCalculator
from core.strategies import GridDeltaStrategy

from .config import (
    DEFAULT_REMOTE_SLICE_DURATION_SEC,
    DEFAULT_REMOTE_TIME_SLICES,
    env_int,
    redis_config_from_env,
    sudo_password_from_env_or_file,
)
from .deploy_worker import RemoteDeployWorker
from .export_worker import LinkDatasetExportWorker
from .dialogs import (
    LinkDatasetExportDialog,
    TopologyDialog,
    WalkerDialog,
)
from .link_state import LinkKey, link_pairs_to_lines, satellite_positions_array
from .redis_worker import RedisQueryWorker
from .remote_play_worker import RemoteMeasureSliceWorker
from .table_panel import LinkTablePanel
from .theme import DARK_THEME
from .topology_registry import TopologyRegistry
from .trend_panel import NetworkTrendPanel
from .visualizer import Visualizer


class MainWindow(QMainWindow):
    redis_query_requested = Signal(int, int, object, object)
    redis_close_requested = Signal()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Satellite Simulation")
        self.resize(1280, 860)
        self.setMinimumSize(980, 700)
        self.setStyleSheet(DARK_THEME)

        self.calculator = OrbitCalculator()
        self.strategy = GridDeltaStrategy()
        self.registry = TopologyRegistry()

        self.redis_config = redis_config_from_env()
        self.redis_enabled = bool(self.redis_config.get("enabled", False))
        self.redis_query_interval = env_int("SATNET_REDIS_QUERY_INTERVAL", 2, minimum=1)
        self.redis_query_counter = 0
        self.redis_query_seq = 0
        self.redis_query_in_flight = False
        self.redis_last_error = ""
        self.redis_worker_thread: Optional[QThread] = None
        self.redis_worker: Optional[RedisQueryWorker] = None
        self._retiring_redis_threads: Set[QThread] = set()
        self.deploy_worker_thread: Optional[QThread] = None
        self.deploy_worker: Optional[RemoteDeployWorker] = None
        self.export_worker_thread: Optional[QThread] = None
        self.export_worker: Optional[LinkDatasetExportWorker] = None
        self.export_progress: Optional[QProgressDialog] = None
        self.deploy_completed = False
        self.remote_measure_thread: Optional[QThread] = None
        self.remote_measure_worker: Optional[RemoteMeasureSliceWorker] = None
        self.remote_measure_in_flight = False
        self.remote_current_slice = 0
        self.remote_total_slices = DEFAULT_REMOTE_TIME_SLICES
        self.remote_slice_duration_sec = DEFAULT_REMOTE_SLICE_DURATION_SEC
        self.remote_play_epoch_time: Optional[datetime] = None
        self.remote_play_started_at = 0.0
        self.remote_slice_active_links: Dict[int, Any] = {}
        self.remote_sudo_password: Optional[str] = None

        if self.redis_enabled:
            self.start_redis_worker(self.redis_config)

        self.step_size = 1.0
        self.is_playing = False
        self.current_time = datetime.utcnow()
        self.selected_link_pairs: Set[LinkKey] = set()
        self.current_walker_config: Optional[Dict[str, Any]] = None
        self._animation_frame = 0

        self._init_ui()
        self._init_menu()
        self._init_toolbar()
        self.statusBar().showMessage("就绪")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.loop)

        self.remote_slice_timer = QTimer(self)
        self.remote_slice_timer.setInterval(int(self.remote_slice_duration_sec * 1000))
        self.remote_slice_timer.timeout.connect(self._on_remote_slice_tick)

    def start_redis_worker(self, redis_config: Dict[str, Any]) -> None:
        self.stop_redis_worker()

        self.redis_worker_thread = QThread(self)
        self.redis_worker = RedisQueryWorker(redis_config)
        self.redis_worker.moveToThread(self.redis_worker_thread)
        self.redis_query_requested.connect(self.redis_worker.query)
        self.redis_close_requested.connect(self.redis_worker.close)
        self.redis_worker.result_ready.connect(self._apply_redis_result)
        self.redis_worker.error.connect(self._handle_redis_error)
        self.redis_worker_thread.finished.connect(self.redis_worker.deleteLater)
        self.redis_worker_thread.finished.connect(self.redis_worker_thread.deleteLater)
        self.redis_worker_thread.finished.connect(
            lambda thread=self.redis_worker_thread: self._retiring_redis_threads.discard(thread)
        )
        self.redis_worker_thread.start()

    def stop_redis_worker(self, *, wait: bool = False) -> None:
        self.redis_query_seq += 1
        self.redis_query_in_flight = False

        worker = self.redis_worker
        thread = self.redis_worker_thread
        self.redis_worker = None
        self.redis_worker_thread = None

        if worker is not None:
            try:
                self.redis_query_requested.disconnect(worker.query)
            except (TypeError, RuntimeError):
                pass
            try:
                self.redis_close_requested.emit()
            except RuntimeError:
                pass
            try:
                self.redis_close_requested.disconnect(worker.close)
            except (TypeError, RuntimeError):
                pass

        if thread is not None:
            self._retiring_redis_threads.add(thread)

        # Normal enable/disable operations return immediately. During final
        # application shutdown, wait briefly so a running QThread is not destroyed.
        if wait and thread is not None and not thread.wait(2000):
            thread.quit()
            thread.wait(500)

    def _init_ui(self) -> None:
        central = QWidget()
        central.setObjectName("workspace")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.workspace_splitter = QSplitter(Qt.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(1)

        scene_row = QWidget()
        scene_row.setObjectName("sceneRow")
        scene_layout = QHBoxLayout(scene_row)
        scene_layout.setContentsMargins(0, 0, 0, 0)
        scene_layout.setSpacing(0)

        self.visualizer = Visualizer()
        scene_layout.addWidget(self.visualizer, 1)

        self.trend_panel = NetworkTrendPanel()
        scene_layout.addWidget(self.trend_panel)
        self.workspace_splitter.addWidget(scene_row)

        self.table_panel = LinkTablePanel(page_size=10)
        self.table_panel.selection_changed.connect(self._on_selected_links_changed)
        self.workspace_splitter.addWidget(self.table_panel)

        self.workspace_splitter.setStretchFactor(0, 7)
        self.workspace_splitter.setStretchFactor(1, 3)
        self.workspace_splitter.setSizes([600, 240])
        layout.addWidget(self.workspace_splitter)

    def _init_menu(self) -> None:
        mb = self.menuBar()

        m_data = mb.addMenu("数据")
        self.act_generate_walker = QAction("生成 Walker 星座", self)
        self.act_generate_walker.triggered.connect(self.open_walker_gen)

        m_data.addAction(self.act_generate_walker)

        m_topo = mb.addMenu("拓扑")
        self.act_topology = QAction("拓扑设置", self)
        self.act_topology.triggered.connect(self.open_topology_settings)
        m_topo.addAction(self.act_topology)

        m_sim = mb.addMenu("仿真")

        self.act_local_play = QAction("本地运行", self)
        self.act_local_play.triggered.connect(self.toggle_local_sim)
        self.act_local_play.setEnabled(False)

        self.act_play = QAction("远程运行", self)
        self.act_play.triggered.connect(self.toggle_sim)
        self.act_play.setEnabled(False)

        self.act_deploy = QAction("Deploy", self)
        self.act_deploy.triggered.connect(self.deploy_remote)

        self.act_step = QAction("步长设置", self)
        self.act_step.triggered.connect(self.open_step_settings)

        self.act_export_dataset = QAction("导出数据集", self)
        self.act_export_dataset.triggered.connect(self.open_link_dataset_export)

        m_sim.addAction(self.act_deploy)
        m_sim.addAction(self.act_local_play)
        m_sim.addAction(self.act_play)
        m_sim.addAction(self.act_step)
        m_sim.addSeparator()
        m_sim.addAction(self.act_export_dataset)

        self.act_redis_enable = QAction("启用 Redis 查询", self)
        self.act_redis_enable.setCheckable(True)
        self.act_redis_enable.setChecked(self.redis_enabled)
        self.act_redis_enable.toggled.connect(self.toggle_redis_query)

        m_redis = mb.addMenu("Redis")
        m_redis.addAction(self.act_redis_enable)

    def _init_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(17, 17))
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)

        icon_dir = Path(__file__).resolve().parents[1] / "assets" / "icons"
        self.icon_play = QIcon(str(icon_dir / "play.svg"))
        self.icon_stop = QIcon(str(icon_dir / "stop.svg"))
        self.act_generate_walker.setIcon(QIcon(str(icon_dir / "constellation.svg")))
        self.act_deploy.setIcon(QIcon(str(icon_dir / "deploy.svg")))
        self.act_local_play.setIcon(self.icon_play)
        self.act_play.setIcon(self.icon_play)
        self.act_step.setIcon(QIcon(str(icon_dir / "step.svg")))
        self.act_export_dataset.setIcon(QIcon(str(icon_dir / "export.svg")))
        self.act_redis_enable.setIcon(QIcon(str(icon_dir / "database.svg")))

        self.act_generate_walker.setToolTip("生成 Walker 星座")
        self.act_deploy.setToolTip("部署远程仿真环境")
        self.act_local_play.setToolTip("开始或停止本地星座推演")
        self.act_play.setToolTip("开始或停止远程仿真")
        self.act_step.setToolTip("设置仿真步长")
        self.act_export_dataset.setToolTip("导出链路状态数据集")
        self.act_redis_enable.setToolTip("连接或断开 Redis")

        toolbar.addAction(self.act_generate_walker)
        toolbar.addSeparator()
        toolbar.addAction(self.act_deploy)
        toolbar.addAction(self.act_local_play)
        toolbar.addAction(self.act_play)
        toolbar.addAction(self.act_step)
        toolbar.addAction(self.act_export_dataset)
        toolbar.addSeparator()
        toolbar.addAction(self.act_redis_enable)

        self.act_toggle_details = QAction(
            QIcon(str(icon_dir / "panel.svg")),
            "链路详情",
            self,
        )
        self.act_toggle_details.setCheckable(True)
        self.act_toggle_details.setChecked(True)
        self.act_toggle_details.setToolTip("显示或隐藏链路详情")
        self.act_toggle_details.toggled.connect(self._toggle_link_details)
        toolbar.addAction(self.act_toggle_details)

        self.addToolBar(Qt.TopToolBarArea, toolbar)

        for play_action in (self.act_local_play, self.act_play):
            play_button = toolbar.widgetForAction(play_action)
            if play_button is not None:
                play_button.setObjectName("primaryToolButton")
                play_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        redis_button = toolbar.widgetForAction(self.act_redis_enable)
        if redis_button is not None:
            redis_button.setObjectName("connectionToolButton")

    def _toggle_link_details(self, visible: bool) -> None:
        self.table_panel.setVisible(visible)
        if visible:
            self.workspace_splitter.setSizes([600, 240])

    def _set_redis_action_checked(self, checked: bool) -> None:
        if not hasattr(self, "act_redis_enable"):
            return
        self.act_redis_enable.blockSignals(True)
        self.act_redis_enable.setChecked(checked)
        self.act_redis_enable.blockSignals(False)

    def toggle_redis_query(self, enabled: bool) -> None:
        if enabled:
            self.redis_config["enabled"] = True
            self.redis_enabled = True
            self.redis_last_error = ""
            self.start_redis_worker(self.redis_config)
        else:
            self.redis_enabled = False
            self.redis_config["enabled"] = False
            self.stop_redis_worker()
            self.redis_last_error = ""
            self.registry.mark_redis_down()

        self.redis_query_counter = 0
        self._set_redis_action_checked(self.redis_enabled)
        self._refresh_table()

    def deploy_remote(self) -> None:
        if self.deploy_worker_thread is not None:
            return

        sudo_password = self._get_remote_sudo_password()
        if sudo_password is None:
            return

        self.deploy_completed = False
        self.act_deploy.setEnabled(False)
        self.act_deploy.setText("Deploying...")
        self.statusBar().showMessage("正在远程部署，请稍候...")

        self.deploy_worker_thread = QThread(self)
        self.deploy_worker = RemoteDeployWorker(sudo_password=sudo_password)
        self.deploy_worker.moveToThread(self.deploy_worker_thread)
        self.deploy_worker_thread.started.connect(self.deploy_worker.run)
        self.deploy_worker.finished.connect(self._handle_deploy_finished)
        self.deploy_worker.finished.connect(self.deploy_worker_thread.quit)
        self.deploy_worker_thread.finished.connect(self.deploy_worker.deleteLater)
        self.deploy_worker_thread.finished.connect(self._cleanup_deploy_worker)
        self.deploy_worker_thread.start()

    @Slot(bool, str)
    def _handle_deploy_finished(self, ok: bool, message: str) -> None:
        summary = self._deploy_message_summary(message)
        if ok:
            self.deploy_completed = True
            self.act_deploy.setText("Deployed")
            self.statusBar().showMessage(summary or "远程部署完成")
            QMessageBox.information(self, "Deploy", summary or "远程部署完成。")
        else:
            self.deploy_completed = False
            self.act_deploy.setText("Deploy")
            self.act_deploy.setEnabled(True)
            self.statusBar().showMessage("远程部署失败")
            QMessageBox.warning(self, "Deploy 失败", summary or "远程部署失败。")

    @Slot()
    def _cleanup_deploy_worker(self) -> None:
        if self.deploy_worker_thread is not None:
            self.deploy_worker_thread.deleteLater()
        self.deploy_worker_thread = None
        self.deploy_worker = None
        if not self.deploy_completed and hasattr(self, "act_deploy"):
            self.act_deploy.setEnabled(True)

    def _deploy_message_summary(self, message: str) -> str:
        lines = [line.strip() for line in str(message).splitlines() if line.strip()]
        if not lines:
            return ""
        return "\n".join(lines[-8:])

    def _get_remote_sudo_password(self) -> Optional[str]:
        configured_password = sudo_password_from_env_or_file()
        if configured_password:
            return configured_password
        if self.remote_sudo_password:
            return self.remote_sudo_password

        password, ok = QInputDialog.getText(
            self,
            "远程 sudo 密码",
            "请输入远程主机 s223 用户的 sudo 密码：",
            QLineEdit.Password,
        )
        if not ok:
            return None

        self.remote_sudo_password = password
        return password

    def _on_selected_links_changed(self, selected: Set[LinkKey]) -> None:
        self.selected_link_pairs = selected

        if not self.is_playing:
            self.visualizer.update_scene(
                satellite_positions_array(self.calculator.satellites),
                self.visualizer.cached_isl,
                highlight_lines=link_pairs_to_lines(self.selected_link_pairs),
            )

    def reset_simulation_state(self) -> None:
        self.registry.reset(self.strategy)
        self.table_panel.reset()
        self.selected_link_pairs.clear()
        self.redis_query_counter = 0
        self.redis_query_seq += 1
        self.redis_query_in_flight = False
        self.redis_last_error = ""

    def _refresh_table(self) -> None:
        self.table_panel.selected_link_pairs = set(self.selected_link_pairs)
        self.table_panel.set_records(
            self.registry.all_links_data,
            redis_in_flight=self.redis_query_in_flight,
            redis_enabled=self.redis_enabled,
            redis_last_error=self.redis_last_error,
            active_count=self.registry.active_count,
        )

    def open_walker_gen(self) -> None:
        dlg = WalkerDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        total = dlg.spin_t.value()
        planes = dlg.spin_p.value()
        phase_factor = dlg.spin_f.value()
        altitude_km = dlg.spin_alt.value()
        inclination_deg = dlg.spin_inc.value()

        if total % planes != 0:
            QMessageBox.warning(
                self,
                "Walker 参数错误",
                "卫星总数 (T) 必须能被轨道面数 (P) 整除。",
            )
            return

        count = self.calculator.generate_walker(
            total,
            planes,
            phase_factor,
            altitude_km,
            inclination_deg,
            self.current_time,
        )

        if count:
            self.current_walker_config = {
                "total": total,
                "orbit_num": planes,
                "sat_per_orbit": total // planes,
                "phase_factor": phase_factor,
                "altitude_km": altitude_km,
                "inclination_deg": inclination_deg,
                "epoch_time": self.current_time,
            }
            self.reset_simulation_state()
            self.act_local_play.setEnabled(True)
            self.act_play.setEnabled(True)
            self.loop(advance=False)

    def open_topology_settings(self) -> None:
        dlg = TopologyDialog(
            latitude_fuse_enabled=getattr(self.strategy, "latitude_fuse_enabled", False),
            latitude_threshold=getattr(self.strategy, "latitude_threshold", 70.0),
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self.strategy = GridDeltaStrategy(
            latitude_fuse_enabled=dlg.chk_latitude_fuse.isChecked(),
            latitude_threshold=dlg.spin_latitude_threshold.value(),
        )

        self.reset_simulation_state()
        if self.calculator.satellites:
            self.loop(advance=False)

    def open_step_settings(self) -> None:
        value, ok = QInputDialog.getDouble(
            self,
            "设置步长",
            "请输入每次推进的仿真步长，单位秒：",
            self.step_size,
            0.1,
            3600.0,
            1,
        )
        if ok:
            self.step_size = value

    def open_link_dataset_export(self) -> None:
        export_error = self._walker_dataset_export_error()
        if export_error:
            QMessageBox.warning(
                self,
                "导出数据集",
                export_error,
            )
            return

        dlg = LinkDatasetExportDialog(self.current_walker_config, self)
        if dlg.exec() != QDialog.Accepted:
            return

        config = dlg.config()
        if not config["output_dir"]:
            QMessageBox.warning(self, "导出数据集", "请选择输出目录。")
            return

        self._start_link_dataset_export(config)

    def _start_link_dataset_export(self, config: Dict[str, Any]) -> None:
        if self.export_worker_thread is not None:
            return

        export_config = {
            "orbit_num": self.current_walker_config["orbit_num"],
            "sat_per_orbit": self.current_walker_config["sat_per_orbit"],
            "time_slices": config["time_slices"],
            "duration_sec": config["duration_sec"],
            "output_dir": config["output_dir"],
            "phase_factor": self.current_walker_config["phase_factor"],
            "altitude_km": self.current_walker_config["altitude_km"],
            "inclination_deg": self.current_walker_config["inclination_deg"],
            "random_failure_enabled": config["random_failure_enabled"],
            "failure_probability": config["failure_probability"],
            "random_seed": config["random_seed"],
            "strategy": self._clone_strategy(),
            "start_time": self.current_time,
            "epoch_time": self.current_walker_config["epoch_time"],
        }

        self.export_progress = QProgressDialog(
            "正在生成链路状态数据集...",
            "取消",
            0,
            config["time_slices"],
            self,
        )
        self.export_progress.setWindowTitle("导出链路状态数据集")
        self.export_progress.setWindowModality(Qt.WindowModal)
        self.export_progress.setMinimumDuration(0)

        self.export_worker_thread = QThread(self)
        self.export_worker = LinkDatasetExportWorker(export_config)
        self.export_worker.moveToThread(self.export_worker_thread)
        self.export_worker_thread.started.connect(self.export_worker.run)
        self.export_worker.progress.connect(self._update_export_progress)
        self.export_worker.finished.connect(self._handle_export_finished)
        self.export_worker.finished.connect(self.export_worker_thread.quit)
        self.export_worker_thread.finished.connect(self.export_worker.deleteLater)
        self.export_worker_thread.finished.connect(self._cleanup_export_worker)
        self.export_progress.canceled.connect(self._cancel_link_dataset_export)
        self.export_worker_thread.start()

    @Slot()
    def _cancel_link_dataset_export(self) -> None:
        if self.export_worker is not None:
            self.export_worker.cancel()

    @Slot(int, int)
    def _update_export_progress(self, done: int, total: int) -> None:
        if self.export_progress is not None:
            self.export_progress.setMaximum(total)
            self.export_progress.setValue(done)

    @Slot(bool, object, str)
    def _handle_export_finished(self, ok: bool, result: Any, message: str) -> None:
        if self.export_progress is not None:
            was_cancelled = self.export_progress.wasCanceled()
            self.export_progress.close()
        else:
            was_cancelled = not ok and not message

        if ok:
            QMessageBox.information(
                self,
                "导出数据集",
                (
                    f"已生成 {result.file_count} 个卫星文件，"
                    f"每个文件包含 {result.time_slices} 个时间片。\n\n{result.output_dir}"
                ),
            )
        elif not was_cancelled:
            QMessageBox.warning(self, "导出数据集", f"导出失败：\n{message}")

    @Slot()
    def _cleanup_export_worker(self) -> None:
        if self.export_worker_thread is not None:
            self.export_worker_thread.deleteLater()
        self.export_worker_thread = None
        self.export_worker = None
        if self.export_progress is not None:
            self.export_progress.deleteLater()
        self.export_progress = None

    def _has_walker_constellation(self) -> bool:
        return bool(self.calculator.satellites)

    def _walker_dataset_export_error(self) -> str:
        if not self.current_walker_config or not self._has_walker_constellation():
            return "请先生成 Walker 星座，再导出链路状态数据集。"

        orbit_num = self.current_walker_config["orbit_num"]
        sat_per_orbit = self.current_walker_config["sat_per_orbit"]
        if orbit_num < 3 or sat_per_orbit < 3:
            return (
                "当前数据集格式要求 Walker 星座至少包含 3 个轨道面，"
                "且每个轨道面至少包含 3 颗卫星。"
            )
        if orbit_num > 99 or sat_per_orbit > 99:
            return (
                "当前数据集格式要求轨道面数量和每轨卫星数量均不超过 99，"
                "以便生成两位编号。"
            )
        return ""

    def _clone_strategy(self):
        return GridDeltaStrategy(
            latitude_fuse_enabled=getattr(self.strategy, "latitude_fuse_enabled", False),
            latitude_threshold=getattr(self.strategy, "latitude_threshold", 70.0),
        )

    def toggle_sim(self) -> None:
        if self.is_playing:
            self.stop_remote_play("已停止远程实验播放")
        else:
            self.start_remote_play()

    def toggle_local_sim(self) -> None:
        if self.is_playing:
            self.stop_local_play()
            return

        if not self.calculator.satellites:
            QMessageBox.warning(self, "Play", "请先生成 Walker 星座。")
            return

        self.is_playing = True
        self.remote_play_epoch_time = None
        self.act_local_play.setText("停止本地")
        self.act_local_play.setIcon(self.icon_stop)
        self.act_play.setEnabled(False)
        self.act_step.setEnabled(False)
        self.timer.start(100)
        self.statusBar().showMessage(f"本地星座推演中，步长 {self.step_size:g} 秒")

    def stop_local_play(self) -> None:
        self.is_playing = False
        self.timer.stop()
        self.act_local_play.setText("本地运行")
        self.act_local_play.setIcon(self.icon_play)
        self.act_play.setEnabled(bool(self.calculator.satellites))
        self.act_step.setEnabled(True)
        self.statusBar().showMessage("本地星座推演已停止")

    def start_remote_play(self) -> None:
        if not self.calculator.satellites:
            QMessageBox.warning(self, "Play", "请先生成 Walker 星座。")
            return
        if self.remote_measure_thread is not None:
            return

        sudo_password = self._get_remote_sudo_password()
        if sudo_password is None:
            return

        if not self.redis_enabled:
            self.redis_config["enabled"] = True
            self.redis_enabled = True
            self._set_redis_action_checked(True)
            self.start_redis_worker(self.redis_config)

        self.is_playing = True
        self.remote_current_slice = 0
        self.remote_measure_in_flight = False
        self.remote_slice_active_links.clear()
        self.remote_play_epoch_time = self.current_walker_config.get("epoch_time") if self.current_walker_config else self.current_time
        self.remote_play_started_at = monotonic()
        self.redis_last_error = ""
        self.redis_query_in_flight = False
        self.remote_sudo_password = sudo_password

        self.act_play.setText("停止")
        self.act_play.setIcon(self.icon_stop)
        self.act_local_play.setEnabled(False)
        self.act_deploy.setEnabled(False)
        self.act_step.setEnabled(False)

        self._prepare_remote_slice(self.remote_current_slice)
        self._start_remote_measure(self.remote_current_slice)
        self.timer.start(100)
        self.remote_slice_timer.start()

    def stop_remote_play(self, message: str = "", *, finished: bool = False) -> None:
        self.is_playing = False
        self.timer.stop()
        self.remote_slice_timer.stop()
        self.remote_measure_in_flight = False

        if self.remote_measure_thread is not None:
            if self.remote_measure_worker is not None:
                self.remote_measure_worker.cancel()
            self.remote_measure_thread.quit()
            self.remote_measure_thread.wait(5000)
            self.remote_measure_thread = None
            self.remote_measure_worker = None

        self.act_play.setText("远程运行")
        self.act_play.setIcon(self.icon_play)
        self.act_local_play.setEnabled(bool(self.calculator.satellites))
        self.act_step.setEnabled(True)
        if not self.deploy_completed:
            self.act_deploy.setEnabled(True)

        if message:
            self.statusBar().showMessage(message)
            if not finished:
                QMessageBox.warning(self, "Play", message)

    def _on_remote_slice_tick(self) -> None:
        if not self.is_playing:
            return
        if self.remote_measure_in_flight:
            self.stop_remote_play(
                f"时间片 {self.remote_current_slice} 未在 {self.remote_slice_duration_sec:g}s 内完成，已停止。"
            )
            return

        self.remote_current_slice += 1
        if self.remote_current_slice >= self.remote_total_slices:
            self.stop_remote_play("远程实验播放完成", finished=True)
            return

        self._prepare_remote_slice(self.remote_current_slice)
        self._start_remote_measure(self.remote_current_slice)

    def _prepare_remote_slice(self, time_slice: int) -> None:
        if self.remote_play_epoch_time is None:
            self.remote_play_epoch_time = self.current_time
        self.current_time = self.remote_play_epoch_time + timedelta(
            seconds=time_slice * self.remote_slice_duration_sec
        )
        self.calculator.propagate(self.current_time)
        self.registry.build_if_needed(self.strategy, self.calculator.satellites)
        isl, active_links = self.strategy.compute_links(self.calculator.satellites)
        self.registry.apply_active_links(active_links)
        self.remote_slice_active_links[time_slice] = self.registry.active_for_redis()
        self._refresh_table()
        self.visualizer.update_scene(
            satellite_positions_array(self.calculator.satellites),
            isl,
            highlight_lines=link_pairs_to_lines(self.selected_link_pairs),
        )

    def _start_remote_measure(self, time_slice: int) -> None:
        if self.remote_measure_thread is not None:
            self.remote_measure_thread.quit()
            self.remote_measure_thread.wait(1000)
            self.remote_measure_thread = None
            self.remote_measure_worker = None

        self.remote_measure_in_flight = True
        self.statusBar().showMessage(f"远程测量时间片 {time_slice}/{self.remote_total_slices - 1}")

        self.remote_measure_thread = QThread(self)
        self.remote_measure_worker = RemoteMeasureSliceWorker(
            time_slice=time_slice,
            sudo_password=self.remote_sudo_password,
        )
        self.remote_measure_worker.moveToThread(self.remote_measure_thread)
        self.remote_measure_thread.started.connect(self.remote_measure_worker.run)
        self.remote_measure_worker.finished.connect(self._handle_remote_measure_finished)
        self.remote_measure_worker.finished.connect(self.remote_measure_thread.quit)
        self.remote_measure_thread.finished.connect(self.remote_measure_worker.deleteLater)
        self.remote_measure_thread.finished.connect(self._cleanup_remote_measure_worker)
        self.remote_measure_thread.start()

    @Slot(int, bool, str, float)
    def _handle_remote_measure_finished(self, time_slice: int, ok: bool, message: str, elapsed: float) -> None:
        self.remote_measure_in_flight = False
        if not self.is_playing:
            return

        if not ok:
            summary = self._deploy_message_summary(message)
            self.stop_remote_play(f"时间片 {time_slice} 测量失败：\n{summary}")
            return

        self.statusBar().showMessage(
            f"时间片 {time_slice} 测量完成，用时 {elapsed:.2f}s，正在读取 Redis..."
        )
        self._query_redis_for_slice(time_slice)

    @Slot()
    def _cleanup_remote_measure_worker(self) -> None:
        if self.remote_measure_thread is not None:
            self.remote_measure_thread.deleteLater()
        self.remote_measure_thread = None
        self.remote_measure_worker = None

    def _query_redis_for_slice(self, time_slice: int) -> None:
        if not self.redis_enabled or self.redis_worker is None:
            return

        active_for_redis = self.remote_slice_active_links.get(time_slice, [])
        if not active_for_redis or not self.calculator.satellites:
            return

        self.redis_query_seq += 1
        self.redis_query_in_flight = True
        self.redis_last_error = ""
        self.redis_query_requested.emit(
            self.redis_query_seq,
            time_slice,
            active_for_redis,
            list(self.calculator.satellites),
        )

    def _schedule_redis_update_if_needed(self) -> None:
        if self.is_playing:
            return
        if not self.redis_enabled or self.redis_worker is None:
            return

        self.redis_query_counter += 1
        if self.redis_query_counter % self.redis_query_interval != 0:
            return
        if self.redis_query_in_flight:
            return

        active_for_redis = self.registry.active_for_redis()
        if not active_for_redis or not self.calculator.satellites:
            return

        self.redis_query_seq += 1
        self.redis_query_in_flight = True
        self.redis_last_error = ""
        self.redis_query_requested.emit(
            self.redis_query_seq,
            -1,
            active_for_redis,
            list(self.calculator.satellites),
        )

    @Slot(int, int, object)
    def _apply_redis_result(
        self,
        query_id: int,
        time_slice: int,
        redis_result: Dict[str, Dict[LinkKey, Any]],
    ) -> None:
        if query_id != self.redis_query_seq:
            return

        self.redis_query_in_flight = False
        self.redis_last_error = ""
        if isinstance(redis_result, dict) and "delay" in redis_result:
            self.registry.apply_redis_delay(redis_result.get("delay", {}))
            if self.redis_config.get("loss_enabled", False):
                self.registry.apply_redis_loss(redis_result.get("loss", {}))
        else:
            self.registry.apply_redis_delay(redis_result)
        self._refresh_table()
        if self.is_playing and time_slice >= 0:
            self.statusBar().showMessage(
                f"时间片 {time_slice}/{self.remote_total_slices - 1} 数据已更新"
            )

    @Slot(int, int, str)
    def _handle_redis_error(self, query_id: int, time_slice: int, message: str) -> None:
        if query_id != self.redis_query_seq:
            return

        self.redis_query_in_flight = False
        self.redis_last_error = message or "Redis 查询失败"
        self.registry.mark_redis_down()
        self._refresh_table()

    def loop(self, advance: bool = True) -> None:
        if not self.calculator.satellites:
            return

        if advance:
            if self.is_playing and self.remote_play_epoch_time is not None:
                elapsed = monotonic() - self.remote_play_started_at
                self.current_time = self.remote_play_epoch_time + timedelta(seconds=elapsed)
            else:
                self.current_time += timedelta(seconds=self.step_size)

        self.calculator.propagate(self.current_time)
        sats = satellite_positions_array(self.calculator.satellites)

        self.registry.build_if_needed(self.strategy, self.calculator.satellites)

        isl, active_links = self.strategy.compute_links(self.calculator.satellites)
        self.registry.apply_active_links(active_links)
        self._schedule_redis_update_if_needed()
        self._animation_frame += 1
        if self._animation_frame % 3 == 0:
            self._refresh_table()

        self.visualizer.update_scene(
            sats,
            isl,
            highlight_lines=link_pairs_to_lines(self.selected_link_pairs),
        )
        self.visualizer.update_hud(
            satellite_count=len(self.calculator.satellites),
            active_link_count=len(active_links),
            current_time=self.current_time,
            redis_status=self._redis_status_text(),
        )
        self._update_trend_panel(len(active_links))
        self.statusBar().showMessage(
            f"卫星：{len(self.calculator.satellites)} | 活动链路：{len(active_links)}"
        )

    def _update_trend_panel(self, active_link_count: int) -> None:
        active_records = [
            self.registry.link_registry[key]
            for key in self.registry.active_link_keys
            if key in self.registry.link_registry
        ]

        def numeric_values(field: str):
            values = []
            for record in active_records:
                try:
                    values.append(float(record.get(field)))
                except (TypeError, ValueError):
                    continue
            return values

        latencies = numeric_values("latency")
        losses = numeric_values("redis_loss_pct")
        total_links = len(self.registry.link_registry)
        directed_active_count = self.registry.active_count

        self.trend_panel.update_metrics(
            average_latency=sum(latencies) / len(latencies) if latencies else None,
            availability=(directed_active_count / total_links) if total_links else None,
            average_loss=sum(losses) / len(losses) if losses else None,
            active_links=active_link_count,
        )

    def _redis_status_text(self) -> str:
        if self.redis_last_error:
            return "异常"
        if self.redis_query_in_flight:
            return "更新中"
        if self.redis_enabled:
            return "已启用"
        return "空闲"

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.remote_slice_timer.stop()
        if self.remote_measure_thread is not None:
            if self.remote_measure_worker is not None:
                self.remote_measure_worker.cancel()
            self.remote_measure_thread.quit()
            self.remote_measure_thread.wait(2500)
        self.stop_redis_worker(wait=True)
        for thread in tuple(self._retiring_redis_threads):
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
        if self.deploy_worker_thread is not None:
            if self.deploy_worker is not None:
                self.deploy_worker.cancel()
            self.deploy_worker_thread.quit()
            self.deploy_worker_thread.wait(2500)
        if self.export_worker_thread is not None:
            if self.export_worker is not None:
                self.export_worker.cancel()
            self.export_worker_thread.quit()
            self.export_worker_thread.wait(2500)
        self.visualizer.close()
        super().closeEvent(event)
