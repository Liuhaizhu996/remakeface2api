# RemakeFace2API

`RemakeFace Ai V1.3.2 PRO` 后端（`api.appbms.com`）的 clean-room 客户端、WebUI 与 OpenAI Images 兼容 API 网关。协议细节见 `docs/PROTOCOL.md`。

## 为什么仓库不包含 `.venv`？

这是**刻意排除**，不会影响拉取和部署，反而是标准做法。

`.venv` 是当前机器生成的 Python 虚拟环境，里面包含操作系统、CPU 架构、Python 小版本和绝对路径相关文件。把它上传到 GitHub 后，在另一台 Linux、Windows、macOS 或不同 Python 版本机器上通常不能直接复用，还会让仓库体积暴涨。

本项目真正需要提交的是：

- `requirements.txt`：声明 Python 依赖；
- `deploy.sh` / `server/start.sh`：自动创建新的 `.venv` 并安装依赖；
- `client/`、`server/`、`tests/`、`docs/`：项目源码；
- 运行时目录和状态文件由程序自动创建，不需要预先提交。

因此一台全新的服务器只要有 `git` 和 Python 3，就能从源码完整重建运行环境。

## 一键部署（推荐）

### 1. 拉取源码并启动

```bash
git clone https://github.com/Liuhaizhu996/remakeface2api.git
cd remakeface2api
bash deploy.sh
```

脚本会自动完成：

1. 创建 `state/`、`server/data/generated/` 等运行目录；
2. 创建本机专用 `.venv`；
3. 安装/更新 `requirements.txt` 中全部依赖；
4. 启动 FastAPI + WebUI，默认监听 `0.0.0.0:8610`。

启动后访问：

```text
WebUI:  http://服务器IP:8610/
Health: http://服务器IP:8610/api/health
Models: http://服务器IP:8610/v1/models
```

### 自定义端口

```bash
PORT=9000 bash deploy.sh
```

### Debian / Ubuntu 如果提示无法创建 venv

系统只需补一次 Python venv 组件：

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

然后重新执行：

```bash
bash deploy.sh
```

## 以后更新源码

```bash
cd remakeface2api
git pull
bash deploy.sh
```

已有 `.venv` 会自动复用并根据 `requirements.txt` 更新依赖，不需要手工删除。

## 手动部署

如果不想用一键脚本：

```bash
git clone https://github.com/Liuhaizhu996/remakeface2api.git
cd remakeface2api
mkdir -p state server/data/generated examples
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8610
```

> 不需要 `source .venv/bin/activate`。直接使用 `.venv/bin/python` 更适合服务器部署和脚本化。

## 项目结构

```text
remakeface2api/
├── client/remake_client.py   # AppBMS 客户端：签名、设备会话、S3 上传、AI 任务
├── server/app.py             # FastAPI / OpenAI 兼容 API
├── server/static/index.html  # WebUI
├── server/start.sh           # 服务启动脚本
├── deploy.sh                 # 全新机器一键部署
├── tests/test_flow.py        # 上传 / 提脸 / NSFW 冒烟测试
├── tests/test_flow2.py       # Face Swap E2E
├── tests/test_gen.py         # AI 生图 E2E
├── docs/PROTOCOL.md          # 协议说明
└── requirements.txt          # Python 依赖
```

运行时会自动生成：

```text
.venv/                        # 本机 Python 虚拟环境，不提交 Git
state/device_state.json       # installation_id / ECDSA 私钥 / deviceSession，不提交 Git
server/data/jobs.json         # 任务历史，不提交 Git
server/data/generated/        # 生成图片，不提交 Git
```

## API 快速验证

```bash
curl http://127.0.0.1:8610/api/health
curl http://127.0.0.1:8610/v1/models
```

OpenAI Images 兼容调用：

```bash
curl -X POST http://127.0.0.1:8610/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"general_v4.0_s",
    "prompt":"a cyberpunk city at night, neon lights",
    "size":"1024x1024",
    "n":1
  }'
```

更完整接口说明见 `README_API.md`，部署说明见 `DEPLOY.md`。

## 本地测试

```bash
.venv/bin/python tests/test_flow.py /path/to/source.jpg
.venv/bin/python tests/test_flow2.py /path/to/source.jpg /path/to/target.jpg
.venv/bin/python tests/test_gen.py /path/to/source.jpg "cyberpunk portrait" general_v4.0_s "1:1"
```

## 关于设备状态

`state/device_state.json` 是**运行时生成文件**。全新拉取源码后没有它是正常的：首次请求会自动注册设备并创建文件；会话过期后客户端会自动重建。因此它不应提交到公开仓库。
