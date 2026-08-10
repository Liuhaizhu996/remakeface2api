# RemakeFace2API 部署说明

## 推荐：全新服务器一键部署

```bash
git clone https://github.com/Liuhaizhu996/remakeface2api.git
cd remakeface2api
bash deploy.sh
```

默认端口 `8610`；自定义端口：

```bash
PORT=9000 bash deploy.sh
```

`deploy.sh` 会自动检查 Python 3.10+、创建运行目录、创建 `.venv`、安装 `requirements.txt` 并启动 Uvicorn。

## `.venv` 为什么不上传

`.venv` 是本机生成物，与系统、Python 版本和路径绑定，不适合作为源码发布。仓库通过 `requirements.txt` + 部署脚本在目标机器重建虚拟环境，所以排除 `.venv` 不会影响部署。

## 系统要求

- Git
- Python 3.10+
- 能访问 PyPI 安装 Python 包
- 能访问项目所需远程 API

Debian / Ubuntu 如缺少 venv：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

## 更新

```bash
cd remakeface2api
git pull
bash deploy.sh
```

## 验证

```bash
curl http://127.0.0.1:8610/api/health
curl http://127.0.0.1:8610/v1/models
```

## 运行时数据

以下内容会自动生成并且不应上传公开仓库：

- `.venv/`
- `state/device_state.json`
- `server/data/jobs.json`
- `server/data/generated/`
- 日志文件
