from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import redis

try:
    from sshtunnel import SSHTunnelForwarder
except Exception:  # sshtunnel is optional until SSH mode is enabled.
    SSHTunnelForwarder = None


class RedisLatencyProvider:
    """Read link metrics directly from Redis."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        key_prefix: str = "link",
        loss_scale: float = 1.0,
        loss_enabled: bool = False,
        socket_timeout: float = 0.05,
        enabled: bool = True,
        use_ssh: bool = False,
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_username: Optional[str] = None,
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
        ssh_private_key_passphrase: Optional[str] = None,
        raise_on_error: bool = False,
    ):
        self.enabled = enabled
        self.host = host
        self.port = int(port)
        self.password = password or None
        self.db = int(db)
        self.key_prefix = key_prefix or "link"
        self.loss_scale = float(loss_scale)
        self.loss_enabled = bool(loss_enabled)
        self.socket_timeout = float(socket_timeout)

        self.use_ssh = bool(use_ssh)
        self.ssh_host = ssh_host or ""
        self.ssh_port = int(ssh_port)
        self.ssh_username = ssh_username or ""
        self.ssh_password = ssh_password or None
        self.ssh_private_key = ssh_private_key or None
        self.ssh_private_key_passphrase = ssh_private_key_passphrase or None
        self.raise_on_error = bool(raise_on_error)

        self.tunnel = None
        self.client: Optional[redis.Redis] = None

        self._connect()

    def _connect(self) -> None:
        connect_host = self.host
        connect_port = self.port

        if self.use_ssh:
            connect_host, connect_port = self._open_ssh_tunnel()

        self.client = redis.Redis(
            host=connect_host,
            port=connect_port,
            db=self.db,
            password=self.password,
            decode_responses=True,
            protocol=2,
            socket_timeout=self.socket_timeout,
            socket_connect_timeout=self.socket_timeout,
        )
        self.client.ping()

    def _open_ssh_tunnel(self) -> Tuple[str, int]:
        if SSHTunnelForwarder is None:
            raise RuntimeError("SSH 模式需要安装 'sshtunnel' 包，可执行：pip install sshtunnel")

        if not self.ssh_host:
            raise RuntimeError("启用 SSH 隧道时必须填写 SSH 主机")

        if not self.ssh_username:
            raise RuntimeError("启用 SSH 隧道时必须填写 SSH 用户名")

        ssh_kwargs: Dict[str, Any] = {
            "ssh_username": self.ssh_username,
            "remote_bind_address": (self.host, self.port),
            "local_bind_address": ("127.0.0.1", 0),
            "set_keepalive": 5.0,
        }

        if self.ssh_password:
            ssh_kwargs["ssh_password"] = self.ssh_password

        if self.ssh_private_key:
            ssh_kwargs["ssh_pkey"] = self.ssh_private_key

        if self.ssh_private_key_passphrase:
            ssh_kwargs["ssh_private_key_password"] = self.ssh_private_key_passphrase

        self.tunnel = SSHTunnelForwarder((self.ssh_host, self.ssh_port), **ssh_kwargs)
        self.tunnel.start()

        return "127.0.0.1", int(self.tunnel.local_bind_port)

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

        if self.tunnel is not None:
            try:
                self.tunnel.stop()
            except Exception:
                pass
            self.tunnel = None

    def _reconnect(self) -> None:
        self.close()
        self._connect()

    def _ssh_session_active(self) -> bool:
        if not self.use_ssh:
            return True
        if self.tunnel is None or not self.tunnel.is_active:
            return False
        transport = getattr(self.tunnel, "_transport", None)
        return transport is not None and transport.is_active()

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if self.client is None:
                self._connect()
            self.client.ping()
            if self.use_ssh:
                return True, f"SSH 隧道正常，Redis 正常：{self.ssh_host}:{self.ssh_port} -> {self.host}:{self.port}"
            return True, f"Redis 正常：{self.host}:{self.port}"
        except Exception as exc:
            return False, str(exc)

    def get_redis_sat_id(self, sat):
        return 10000 + (sat.plane_idx + 1) * 100 + (sat.node_idx + 1)

    def _metric_keys(self, src_id, tgt_id, metric, time_slice: Optional[int] = None):
        if time_slice is not None and time_slice >= 0:
            return [f"{self.key_prefix}:ts{time_slice}:{src_id}:{tgt_id}:{metric}"]
        return [f"{self.key_prefix}:{src_id}:{tgt_id}:{metric}"]

    def _parse_metric_value(self, raw):
        if not raw:
            return "down"

        try:
            value = float(str(raw).rsplit(",", 1)[-1])
            return round(value, 4)
        except Exception:
            return "down"

    def _parse_loss_pct(self, raw):
        if not raw:
            return "down"

        try:
            value = float(str(raw).split(",")[-1])
            return round((value / self.loss_scale) * 100.0, 4)
        except Exception:
            return "down"

    def _get_latest_many(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        metric: str,
        parser: Callable[[Any], Any],
        time_slice: Optional[int] = None,
    ):
        result = {}

        if not links or not satellites:
            return result

        if self.client is None:
            self._connect()

        sat_ids = [self.get_redis_sat_id(sat) for sat in satellites]
        query_plan = []
        commands = []

        for link in links:
            src_idx = link["src"]
            tgt_idx = link["tgt"]
            src_id = sat_ids[src_idx]
            tgt_id = sat_ids[tgt_idx]
            keys = self._metric_keys(src_id, tgt_id, metric, time_slice)

            commands.extend(keys)
            query_plan.append((src_idx, tgt_idx))

        redis_results = None
        for attempt in range(2):
            try:
                if attempt or not self._ssh_session_active():
                    self._reconnect()
                pipe = self.client.pipeline(transaction=False)
                for key in commands:
                    pipe.lrange(key, -1, -1)
                redis_results = pipe.execute()
                break
            except Exception:
                redis_results = None

        if redis_results is None:
            for link in links:
                result[(link["src"], link["tgt"])] = "down"
            return result

        pos = 0
        for src_idx, tgt_idx in query_plan:
            latest_result = redis_results[pos]
            pos += 1

            latest = "down"
            if latest_result:
                latest = parser(latest_result[-1])

            result[(src_idx, tgt_idx)] = latest

        return result

    def get_latest_delay_many(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        time_slice: Optional[int] = None,
    ):
        return self._get_latest_many(links, satellites, "delay", self._parse_metric_value, time_slice)

    def get_latest_loss_many(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        time_slice: Optional[int] = None,
    ):
        return self._get_latest_many(links, satellites, "loss", self._parse_loss_pct, time_slice)

    def get_latest_link_metrics_many(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        time_slice: Optional[int] = None,
    ):
        metric_specs = [("delay", self._parse_metric_value)]
        if self.loss_enabled:
            metric_specs.append(("loss", self._parse_loss_pct))
        return self._get_latest_metrics_pipeline(links, satellites, metric_specs, time_slice)

    def _get_latest_metrics_pipeline(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        metric_specs: Sequence[Tuple[str, Callable[[Any], Any]]],
        time_slice: Optional[int],
    ) -> Dict[str, Dict[Tuple[int, int], Any]]:
        metrics = {metric: {} for metric, _parser in metric_specs}
        if not links or not satellites:
            return metrics
        if self.client is None:
            self._connect()

        sat_ids = [self.get_redis_sat_id(sat) for sat in satellites]
        commands = []
        query_plan = []
        for metric, parser in metric_specs:
            for link in links:
                src_idx = int(link["src"])
                tgt_idx = int(link["tgt"])
                key = self._metric_keys(
                    sat_ids[src_idx],
                    sat_ids[tgt_idx],
                    metric,
                    time_slice,
                )[0]
                commands.append(key)
                query_plan.append((metric, parser, src_idx, tgt_idx))

        redis_results = None
        last_error = None
        for attempt in range(2):
            try:
                if attempt or not self._ssh_session_active():
                    self._reconnect()
                pipe = self.client.pipeline(transaction=False)
                for key in commands:
                    pipe.lrange(key, -1, -1)
                redis_results = pipe.execute()
                break
            except Exception as exc:
                last_error = exc
                redis_results = None

        if redis_results is None:
            if self.raise_on_error and last_error is not None:
                raise RuntimeError(f"Redis批量查询失败：{last_error}") from last_error
            for metric, _parser in metric_specs:
                for link in links:
                    metrics[metric][(int(link["src"]), int(link["tgt"]))] = "down"
            return metrics

        for result, (metric, parser, src_idx, tgt_idx) in zip(redis_results, query_plan):
            value = parser(result[-1]) if result else "down"
            metrics[metric][(src_idx, tgt_idx)] = value
        return metrics


class MultiRedisLatencyProvider:
    """Route directed-link metric queries to the backend owning the source orbit."""

    def __init__(
        self,
        *,
        backends: Sequence[Dict[str, Any]],
        enabled: bool = True,
        loss_enabled: bool = True,
        strict: bool = True,
    ):
        self.enabled = bool(enabled)
        self.loss_enabled = bool(loss_enabled)
        self.strict = bool(strict)
        self.backend_configs = {
            str(config["name"]): dict(config)
            for config in backends
        }
        self.providers: Dict[str, RedisLatencyProvider] = {}
        self.last_errors: Dict[str, str] = {}

    def _backend_for_orbit(self, orbit_number: int) -> Optional[str]:
        for name, config in self.backend_configs.items():
            if int(config["orbit_start"]) <= orbit_number <= int(config["orbit_end"]):
                return name
        return None

    def _provider(self, name: str) -> RedisLatencyProvider:
        provider = self.providers.get(name)
        if provider is None:
            config = dict(self.backend_configs[name])
            for key in ("name", "orbit_start", "orbit_end"):
                config.pop(key, None)
            config["loss_enabled"] = self.loss_enabled
            provider = RedisLatencyProvider(**config)
            self.providers[name] = provider
        return provider

    def get_latest_link_metrics_many(
        self,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        time_slice: Optional[int] = None,
    ) -> Dict[str, Dict[Tuple[int, int], Any]]:
        merged: Dict[str, Dict[Tuple[int, int], Any]] = {"delay": {}}
        if self.loss_enabled:
            merged["loss"] = {}
        if not links or not satellites:
            return merged

        partitions: Dict[str, List[Dict[str, Any]]] = {}
        unassigned: List[Dict[str, Any]] = []
        for link in links:
            src_idx = int(link["src"])
            orbit_number = int(satellites[src_idx].plane_idx) + 1
            backend_name = self._backend_for_orbit(orbit_number)
            if backend_name is None:
                unassigned.append(link)
            else:
                partitions.setdefault(backend_name, []).append(link)

        self.last_errors.clear()
        with ThreadPoolExecutor(
            max_workers=max(1, len(partitions)),
            thread_name_prefix="redis",
        ) as executor:
            futures = {}
            for name, backend_links in partitions.items():
                futures[
                    executor.submit(
                        self._query_backend,
                        name,
                        backend_links,
                        satellites,
                        time_slice,
                    )
                ] = (name, backend_links)

            for future in as_completed(futures):
                name, backend_links = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    self.last_errors[name] = str(exc)
                    self._mark_down(merged, backend_links)
                    continue
                for metric, values in result.items():
                    merged.setdefault(metric, {}).update(values)

        # A cross-host monitor may capture both directions on the destination
        # backend. Keep source-orbit routing as the primary lookup, then query
        # the target backend only for cross-host links whose primary value is
        # missing. This avoids reporting a working physical link as down merely
        # because its telemetry was recorded by the peer receiver.
        fallback_partitions: Dict[str, List[Dict[str, Any]]] = {}
        for link in links:
            src_idx = int(link["src"])
            tgt_idx = int(link["tgt"])
            src_backend = self._backend_for_orbit(
                int(satellites[src_idx].plane_idx) + 1
            )
            tgt_backend = self._backend_for_orbit(
                int(satellites[tgt_idx].plane_idx) + 1
            )
            if (
                src_backend is not None
                and tgt_backend is not None
                and src_backend != tgt_backend
            ):
                fallback_partitions.setdefault(tgt_backend, []).append(link)

        with ThreadPoolExecutor(
            max_workers=max(1, len(fallback_partitions)),
            thread_name_prefix="redis-fallback",
        ) as executor:
            futures = {
                executor.submit(
                    self._query_backend,
                    name,
                    backend_links,
                    satellites,
                    time_slice,
                ): name
                for name, backend_links in fallback_partitions.items()
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception:
                    # The source backend remains authoritative. A peer lookup
                    # is best-effort and must not turn a valid primary result
                    # into a strict multi-Redis failure.
                    continue
                for metric, values in result.items():
                    destination = merged.setdefault(metric, {})
                    for key, value in values.items():
                        if destination.get(key, "down") == "down" and value != "down":
                            destination[key] = value

        self._mark_down(merged, unassigned)
        if unassigned:
            self.last_errors["placement"] = f"{len(unassigned)} 条链路没有后端归属"
        if self.strict and self.last_errors:
            details = "; ".join(
                f"{name}: {message}"
                for name, message in sorted(self.last_errors.items())
            )
            raise RuntimeError(f"双Redis查询未完整闭环（{details}）")
        return merged

    def _query_backend(
        self,
        name: str,
        links: List[Dict[str, Any]],
        satellites: List[Any],
        time_slice: Optional[int],
    ):
        return self._provider(name).get_latest_link_metrics_many(
            links,
            satellites,
            time_slice,
        )

    def _mark_down(
        self,
        result: Dict[str, Dict[Tuple[int, int], Any]],
        links: Sequence[Dict[str, Any]],
    ) -> None:
        for link in links:
            key = (int(link["src"]), int(link["tgt"]))
            for values in result.values():
                values[key] = "down"

    def test_connection(self) -> Tuple[bool, str]:
        results = []
        all_ok = True
        for name in self.backend_configs:
            try:
                ok, message = self._provider(name).test_connection()
            except Exception as exc:
                ok, message = False, str(exc)
            all_ok = all_ok and ok
            results.append(f"[{name}] {message}")
        return all_ok, "\n".join(results)

    def close(self) -> None:
        for provider in self.providers.values():
            provider.close()
        self.providers.clear()
