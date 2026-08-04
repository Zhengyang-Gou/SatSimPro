import os

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Visualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.plotter = QtInteractor(self)
        self.layout.addWidget(self.plotter)

        self.hud = QLabel(self.plotter)
        self.hud.setObjectName("sceneHud")
        self.hud.setStyleSheet(
            """
            QLabel#sceneHud {
                background-color: #20242b;
                border: 1px solid #3b4554;
                border-radius: 8px;
                color: #d7dce3;
                padding: 8px 10px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                font-size: 12px;
            }
            """
        )
        self.hud.setText("卫星 0\n链路 0\nRedis 空闲")
        self.hud.adjustSize()
        self.hud.move(14, 14)
        self.hud.raise_()

        self.cached_sat_pos = np.empty((0, 3), dtype=np.float64)
        self.cached_isl = np.empty((0,), dtype=np.int64)
        self.cached_path_lines = np.empty((0,), dtype=np.int64)
        self.rendered_isl = np.empty((0,), dtype=np.int64)
        self.rendered_path_lines = np.empty((0,), dtype=np.int64)

        self.sat_actor = None
        self.isl_actor = None
        self.path_actor = None

        self._init_scene()

    def _init_scene(self) -> None:
        self.plotter.set_background("#0f1218", top="#1a1f29")

        sphere = pv.Sphere(
            radius=6371,
            theta_resolution=120,
            phi_resolution=120,
        )

        try:
            sphere = sphere.texture_map_to_sphere()
        except Exception:
            pass

        if os.path.exists("assets/earth.jpg"):
            try:
                texture = pv.read_texture("assets/earth.jpg")
                self.plotter.add_mesh(
                    sphere,
                    texture=texture,
                    smooth_shading=True,
                )
            except Exception:
                self.plotter.add_mesh(
                    sphere,
                    color="#192433",
                    style="wireframe",
                    opacity=0.22,
                )
        else:
            self.plotter.add_mesh(
                sphere,
                color="#192433",
                style="wireframe",
                opacity=0.22,
            )

        self.plotter.add_axes()

        self.plotter.camera_position = [
            (35000, 25000, 15000),
            (0, 0, 0),
            (0, 0, 1),
        ]

        try:
            self.plotter.enable_anti_aliasing("msaa", multi_samples=4)
        except Exception:
            pass

        # Do not enable depth peeling here.  With the VTK/OpenGL stack used by
        # WSLg, combining it with MSAA makes translucent line actors disappear
        # completely even though their geometry is present.  The Earth is
        # opaque, so regular depth testing and alpha blending are sufficient
        # for the semi-transparent ISL actors.

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.hud.move(14, 14)
        self.hud.raise_()

    def closeEvent(self, event) -> None:
        self._remove_actor("path_actor")
        self._remove_actor("isl_actor")
        self._remove_actor("sat_actor")
        try:
            self.plotter.clear()
        except Exception:
            pass
        try:
            self.plotter.close()
        except Exception:
            pass
        super().closeEvent(event)

    def update_hud(
        self,
        *,
        satellite_count: int,
        active_link_count: int,
        current_time,
        redis_status: str,
    ) -> None:
        self.hud.setText(
            f"卫星 {satellite_count}\n"
            f"活动链路 {active_link_count}\n"
            f"时间 {current_time:%Y-%m-%d %H:%M:%S}\n"
            f"Redis {redis_status}"
        )
        self.hud.adjustSize()
        self.hud.raise_()

    def update_scene(self, sat_positions, isl_lines, highlight_lines=None) -> None:
        self.cached_sat_pos = self._normalize_points(sat_positions)
        self.cached_isl = self._normalize_lines(isl_lines)

        if highlight_lines is None:
            self.cached_path_lines = np.empty((0,), dtype=np.int64)
        else:
            self.cached_path_lines = self._normalize_lines(highlight_lines)

        self._render_frame()

    def _normalize_points(self, sat_positions) -> np.ndarray:
        if sat_positions is None:
            return np.empty((0, 3), dtype=np.float64)

        points = np.asarray(sat_positions, dtype=np.float64)

        if points.size == 0:
            return np.empty((0, 3), dtype=np.float64)

        points = points.reshape((-1, 3))
        return np.ascontiguousarray(points, dtype=np.float64)

    def _normalize_lines(self, lines) -> np.ndarray:
        if lines is None:
            return np.empty((0,), dtype=np.int64)

        arr = np.asarray(lines, dtype=np.int64).reshape(-1)

        if arr.size == 0:
            return np.empty((0,), dtype=np.int64)

        if arr.size % 3 != 0:
            return np.empty((0,), dtype=np.int64)

        if not np.all(arr[0::3] == 2):
            return np.empty((0,), dtype=np.int64)

        return np.ascontiguousarray(arr, dtype=np.int64)

    def _remove_actor(self, actor_name: str) -> None:
        actor = getattr(self, actor_name)

        if actor is None:
            return

        try:
            self.plotter.remove_actor(actor)
        except Exception:
            pass

        setattr(self, actor_name, None)

    def _build_line_mesh(self, points: np.ndarray, lines: np.ndarray) -> pv.PolyData:
        return pv.PolyData(points, lines=np.ascontiguousarray(lines, dtype=np.int64))

    def _same_line_topology(self, left: np.ndarray, right: np.ndarray) -> bool:
        if left.shape != right.shape:
            return False
        if np.array_equal(left, right):
            return True

        left_pairs = np.sort(left.reshape((-1, 3))[:, 1:3], axis=1)
        right_pairs = np.sort(right.reshape((-1, 3))[:, 1:3], axis=1)
        left_order = np.lexsort((left_pairs[:, 1], left_pairs[:, 0]))
        right_order = np.lexsort((right_pairs[:, 1], right_pairs[:, 0]))
        return np.array_equal(left_pairs[left_order], right_pairs[right_order])

    def _update_line_actor(
        self,
        actor_name: str,
        rendered_lines_name: str,
        points: np.ndarray,
        lines: np.ndarray,
        color: str,
        line_width: int,
        opacity: float = 1.0,
    ) -> None:
        if len(lines) == 0:
            self._remove_actor(actor_name)
            setattr(self, rendered_lines_name, np.empty((0,), dtype=np.int64))
            return

        actor = getattr(self, actor_name)
        rendered_lines = getattr(self, rendered_lines_name)

        if actor is not None and self._same_line_topology(rendered_lines, lines):
            try:
                dataset = actor.mapper.dataset
                if len(dataset.points) == len(points):
                    dataset.points = points
                    dataset.Modified()
                    actor.mapper.Modified()
                    return
            except Exception:
                pass

        self._remove_actor(actor_name)
        mesh = self._build_line_mesh(points, lines)
        actor = self.plotter.add_mesh(
            mesh,
            color=color,
            line_width=line_width,
            opacity=opacity,
            render_lines_as_tubes=True,
            lighting=False,
        )
        setattr(self, actor_name, actor)
        setattr(self, rendered_lines_name, lines.copy())
        self.plotter.reset_camera_clipping_range()

    def _render_frame(self) -> None:
        if len(self.cached_sat_pos) == 0:
            return

        sats = self.cached_sat_pos

        self._render_satellites(sats)
        self._render_isl_links(sats)
        self._render_highlight_links(sats)

        self.plotter.render()

    def _render_satellites(self, sats: np.ndarray) -> None:
        if self.sat_actor:
            try:
                dataset = self.sat_actor.mapper.dataset
                dataset.points = sats
                dataset.Modified()
                self.sat_actor.mapper.Modified()
                return
            except Exception:
                self._remove_actor("sat_actor")

        cloud = pv.PolyData(sats)

        self.sat_actor = self.plotter.add_mesh(
            cloud,
            color="#dbeafe",
            point_size=7,
            render_points_as_spheres=True,
        )

    def _render_isl_links(self, sats: np.ndarray) -> None:
        """
        Render normal ISL links.

        Important:
        Do not update dataset.lines in-place here. In some PyVista/VTK versions,
        changing the line cell array in-place does not reliably refresh the actor.
        Rebuild only when the topology changes; otherwise update points in-place
        to avoid visible flicker.
        """
        self._update_line_actor(
            "isl_actor",
            "rendered_isl",
            sats,
            self.cached_isl,
            color="#8ab4f8",
            line_width=2,
            opacity=0.58,
        )

    def _render_highlight_links(self, sats: np.ndarray) -> None:
        """
        Render selected/highlighted links.

        This follows the same topology-change rebuild rule as normal ISL links.
        """
        self._update_line_actor(
            "path_actor",
            "rendered_path_lines",
            sats,
            self.cached_path_lines,
            color="#fdd663",
            line_width=5,
        )
