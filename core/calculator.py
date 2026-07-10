from datetime import datetime

import numpy as np

from .models import Satellite


class OrbitCalculator:
    def __init__(self):
        self.satellites = []
        self.epoch_time = None
        self._altitudes = np.empty((0,), dtype=np.float64)
        self._inclinations_rad = np.empty((0,), dtype=np.float64)
        self._raan_rad = np.empty((0,), dtype=np.float64)
        self._mean_anomalies_rad = np.empty((0,), dtype=np.float64)

    def generate_walker(self, T, P, F, alt_km, inc_deg, current_time: datetime):
        if T <= 0 or P <= 0:
            raise ValueError("T and P must be positive")
        if T % P != 0:
            raise ValueError("T must be divisible by P")

        self.satellites = []
        self.epoch_time = current_time
        S = T // P
        delta_raan = 360.0 / P
        delta_ma = 360.0 / S
        phase_shift = (F * 360.0) / T

        sat_id_counter = 0
        for p in range(P):
            for s in range(S):
                raan = p * delta_raan
                ma = (s * delta_ma + p * phase_shift) % 360.0
                name = f"{p+1:02d}{s+1:02d}"

                sat = Satellite(sat_id=sat_id_counter, name=name)
                sat.plane_idx = p
                sat.node_idx = s
                sat.altitude = alt_km
                sat.inclination = inc_deg
                sat.raan = raan
                sat.mean_anomaly = ma
                self.satellites.append(sat)
                sat_id_counter += 1

        self._cache_orbital_elements()
        return len(self.satellites)

    def _cache_orbital_elements(self) -> None:
        """Cache immutable Walker elements as arrays for vectorized propagation."""
        self._altitudes = np.asarray([sat.altitude for sat in self.satellites], dtype=np.float64)
        self._inclinations_rad = np.radians(
            np.asarray([sat.inclination for sat in self.satellites], dtype=np.float64)
        )
        self._raan_rad = np.radians(
            np.asarray([sat.raan for sat in self.satellites], dtype=np.float64)
        )
        self._mean_anomalies_rad = np.radians(
            np.asarray([sat.mean_anomaly for sat in self.satellites], dtype=np.float64)
        )

    def propagate(self, current_time: datetime):
        if not self.satellites:
            return
        if len(self._altitudes) != len(self.satellites):
            self._cache_orbital_elements()

        jd = 2451545.0 + (current_time - datetime(2000, 1, 1, 12)).total_seconds() / 86400.0
        gst = self._gstime(jd)
        c, s = np.cos(gst), np.sin(gst)
        delta_t_sec = (current_time - self.epoch_time).total_seconds() if self.epoch_time is not None else 0.0
        earth_radius_km = 6371.0
        mu = 3.986004418e5

        semi_major_axes = earth_radius_km + self._altitudes
        mean_motion = np.sqrt(mu / np.power(semi_major_axes, 3))
        anomaly = self._mean_anomalies_rad + mean_motion * delta_t_sec

        x_plane = semi_major_axes * np.cos(anomaly)
        y_plane = semi_major_axes * np.sin(anomaly)
        cos_raan = np.cos(self._raan_rad)
        sin_raan = np.sin(self._raan_rad)
        cos_inc = np.cos(self._inclinations_rad)
        sin_inc = np.sin(self._inclinations_rad)

        x_eci = x_plane * cos_raan - y_plane * cos_inc * sin_raan
        y_eci = x_plane * sin_raan + y_plane * cos_inc * cos_raan
        z_eci = y_plane * sin_inc
        positions_eci = np.column_stack((x_eci, y_eci, z_eci))
        positions_ecef = np.column_stack((x_eci * c + y_eci * s, -x_eci * s + y_eci * c, z_eci))

        for sat, position_eci, position_ecef in zip(
            self.satellites, positions_eci, positions_ecef
        ):
            sat.position_eci = position_eci
            sat.position = position_ecef

    def _gstime(self, jdut1):
        tut1 = (jdut1 - 2451545.0) / 36525.0
        temp = -6.2e-6 * tut1**3 + 0.093104 * tut1**2 + (876600.0*3600 + 8640184.812866) * tut1 + 67310.54841
        temp = (temp * (np.pi/180.0) / 240.0) % (2*np.pi)
        if temp < 0:
            temp += 2*np.pi
        return temp
