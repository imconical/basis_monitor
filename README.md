# 多品种基差实时监控系统

本系统通过 Wind 实时数据接口，结合 WebSocket + ECharts 实现多品种股指期货基差的实时监控和可视化展示。

## 项目结构

- **后端**：Python + WindPy + WebSocket
- **前端**：纯 HTML + JavaScript + ECharts v5

## 功能简介

- 实时订阅并获取沪深 300、上证 50、中证 500、中证 1000 等主要股指期货合约（当月、次月、当季、次季）和现货指数的最新行情数据；
- 动态计算基差（期货价格 - 现货价格）；
- 基差数据通过 WebSocket 实时推送至前端；
- 前端使用 ECharts 动态绘制折线图，并在每个图表右侧实时显示最新基差数值，方便快速观察最新行情；
- 数据自动缓存最新 300 个数据点，保证性能与流畅性。

## 环境配置

### 1. 后端环境

- Python >= 3.8
- WindPy SDK（需安装好 Wind 终端并有行情权限）
- 依赖库安装：

```bash
pip install WindPy websockets
```

### 2. 前端环境

- 无需额外依赖，现代浏览器（Chrome、Edge、Firefox）直接打开 index.html 文件即可。

## 启动方法
### 1. 启动 Wind 终端

- 请先确保本地已启动 Wind金融终端 并正常登录。
### 2. 启动后端服务
- 运行 backend.py：

```bash
python backend.py
```

- 默认启动在 ws://localhost:8765/
- 后端负责实时计算基差并通过 WebSocket 向前端推送数据

### 3. 启动前端页面
- 直接用浏览器打开 index.html，即可实时观看多品种基差曲线图和最新基差值。