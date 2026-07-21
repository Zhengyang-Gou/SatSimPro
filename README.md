# Satellite Simulation

Satellite Simulation 是一个基于 PySide6 和 PyVista 的卫星网络仿真工具。它提供三维地球与卫星链路可视化、Walker 星座生成、链路表格查看、Redis 实时链路指标查询，以及离线链路状态数据集导出。

## 功能概览

- 三维可视化卫星位置、星间链路和选中链路。
- 支持生成 Walker 星座，参数包括卫星总数、轨道面数、相位因子、高度和倾角。
- 使用 Grid Delta 拓扑策略生成星间链路。
- 可启用纬度熔断，在高纬区域断开异轨链路。
- 链路表格展示链路端点、延迟、Redis 查询状态等信息。
- 支持 Redis 或 SSH 隧道 Redis 查询链路指标。
- 支持导出 Walker 星座的离线链路状态数据集。

## 环境安装

项目提供 Conda 环境文件：

```bash
conda env create -f environment.yml
conda activate satsim
```

如果环境已存在，可以更新依赖：

```bash
conda env update -f environment.yml --prune
```

主要依赖包括：

- Python 3.11
- NumPy
- PySide6
- VTK
- PyVista
- PyVistaQt
- redis
- sshtunnel

## 启动

```bash
python main.py
```

启动后生成 Walker 星座，可在前端选择两种运行方式：

- `本地运行`：仅在本机推进星座，不执行 SSH、远程测量或 Redis 查询。
- `远程运行`：保留 Deploy、远程时间片测量和 Redis 查询流程。

本地推演可通过“仿真 -> 步长设置”配置每次推进的仿真秒数。

Linux Wayland 环境下，程序会自动尝试切换到 X11 后端以提升 Qt/VTK 兼容性。

## 基本使用

### 生成 Walker 星座

菜单路径：

```text
数据 -> 生成 Walker 星座
```

可设置：

- `Total Satellites (T)`：卫星总数
- `Orbital Planes (P)`：轨道面数量
- `Phase Factor (F)`：相位因子
- `Altitude`：轨道高度，单位 km
- `Inclination`：轨道倾角，单位度

注意：卫星总数必须能被轨道面数整除。

### 设置拓扑

菜单路径：

```text
拓扑 -> 拓扑设置
```

当前拓扑策略为 `Grid Delta`。可选开启 `Latitude Fuse`，当链路端点处于指定纬度阈值以上时，异轨链路会被熔断。

### 运行仿真

菜单路径：

```text
仿真 -> Deploy
仿真 -> 开始
仿真 -> 步长设置
```

`Deploy` 会通过已配置的 SSH 主机执行远端脚本
`/home/s223/yzy/scripts/deploy.sh`，用于清理旧环境、创建容器和 OVS、
启动 rawsock 与收包器。部署过程在后台线程执行，成功后按钮会变为
`Deployed` 并灰掉。

`开始` 会进入远程实验播放模式：GUI 每 100 ms 平滑推进 Walker 画面，
同时每 10 秒启动一个远程时间片测量：

```text
sudo bash /home/s223/yzy/scripts/measure_slice.sh <ts> 5 10
```

时间片从 `ts=0` 开始。远端脚本顺序执行：写入当前时间片、调用
`apply_slice.py` 下发流表和 tc、发送 delay 探测包、发送 loss 探测包。
如果某个时间片测量超过 10 秒，GUI 会停止播放并报错，不会启动下一片。

`步长设置` 仅用于非远程播放时的本地推进步长。

## 导出链路状态数据集

菜单路径：

```text
仿真 -> 导出数据集
```

该功能只支持 Walker 星座。导出前需要先通过 `生成 Walker 星座` 生成星座。

导出参数：

- `时间片数量`：导出的时间片数量
- `仿真总时长`：总仿真时长，单位秒
- `Enable Random Link Failure`：是否启用随机链路失效
- `Down Probability / Slice`：每个时间片的链路失效概率
- `Random Seed`：随机种子
- `Save To`：输出目录

输出目录格式：

```text
LinkDataset_YYYYMMDD_HHMMSS/
  link_info_15_35.txt
  manifest.json
  satellite_10101.txt
  satellite_10102.txt
  ...
```

`manifest.json` 记录本次仿真的运行编号、单个时间片时长和时间片数量：

```json
{
  "run_id": "20260614_055437",
  "step_duration_sec": 10.0,
  "time_slices": 6
}
```

每个卫星一个文件，记录该卫星固定 4 个邻居在各时间片的链路状态。链路可用时写入延迟，链路不可用时写入：

```text
down
```

示例文件结构：

```text
Time
Satellite_10102 Satellite_10201 Satellite_10199 Satellite_10103
------------------------------------------------------------
0 12.34567890 down 10.12345678 11.23456789
1 12.45678901 down 10.23456789 11.34567890
```

导出限制：

- 轨道面数量至少为 3。
- 每轨卫星数量至少为 3。
- 轨道面数量和每轨卫星数量最多为 99，用于生成两位编号格式。

## Redis 链路指标

菜单路径：

```text
Redis -> 启用 Redis 查询
```

Redis 查询默认关闭。勾选后，程序会自动通过 SSH 连接固定服务器
`121.48.163.223`，并访问该服务器本机的 Redis `127.0.0.1:6379`。

也可以在启动前用环境变量默认启用：

```bash
SATNET_REDIS_ENABLED=1
```

SSH 主机、用户名、私钥、Redis 地址和 Redis key 前缀均已固定在项目配置中。
密码不会写入项目；默认使用 SSH 私钥免密连接。Redis 密码写入仅当前用户可读的
`~/.config/satellite-simulation/redis_password`。

Redis key 默认格式：

```text
data:ts<slice_id>:<src_id>:<tgt_id>:delay
data:ts<slice_id>:<src_id>:<tgt_id>:loss
```

Value 为 Redis List，每项格式为 `timestamp,value`。程序使用
`LRANGE key -1 -1` 读取最新值，并同时尝试正向和反向链路 key。

写入 Redis 前应将 `delay` 统一换算为毫秒。读取端直接按毫秒解析，
再在表格中显示为 `Redis 时延 / 计算时延 (%)`。
默认认为 `loss` 是 0 到 1 的比例，并转换为百分比。

```text
data:ts0:10101:10102:delay -> "1718400010.345678,4.095800"
data:ts0:10101:10102:loss  -> "1718400010.345678,0.012500"
```

## 项目结构

```text
satellite-simulation/
  main.py                       # 程序入口
  environment.yml               # Conda 环境
  assets/                       # 贴图和图标资源
  core/
    calculator.py               # Walker 生成和轨道推进
    strategies.py               # 链路拓扑策略
    link_dataset_exporter.py    # 链路状态数据集导出
    redis_latency.py            # Redis 链路指标读取
    models.py                   # 数据模型
  gui/
    main_window.py              # 主窗口和菜单逻辑
    dialogs.py                  # 参数对话框
    visualizer.py               # 三维可视化
    table_panel.py              # 链路表格
    topology_registry.py        # 链路状态注册表
    redis_worker.py             # Redis 后台查询线程
```

## 开发检查

可用以下命令做基础检查：

```bash
python3 -m pyflakes .
python3 -m compileall -q .
```
