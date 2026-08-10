# 部署说明（换机/上服务器）

## 需要拷贝的内容

整个项目目录（推荐排除：`.venv/`、`server/data/generated/`、`__pycache__/`）。
`state/device_state.json` 可拷可不拷：
- **不拷**：新机器首次运行自动注册新设备（推荐，最干净）
- **拷**：复用当前 deviceSession（TTL≈6h，过期后自动重建）

## 新机器启动（三条命令）

```bash
cd remakeface-appbms
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./server/start.sh                 # 默认 0.0.0.0:8610
# 或自定义端口
PORT=9000 ./server/start.sh
```

## 依赖

仅 5 个纯 Python 包（`requirements.txt`）：
`cryptography` `fastapi` `uvicorn` `python-multipart` `pillow`

## 无本地依赖

- 后端只连远程 `https://api.appbms.com`，本地不装任何数据库/中间件
- 所有路径基于 `Path(__file__)` 相对定位，无环境变量/绝对路径依赖
- 生图模型 24 款全部内置在 `server/app.py` MODELS，无需模型文件下载

## 验证

```bash
curl http://127.0.0.1:8610/api/health      # 服务 + 设备会话状态
curl http://127.0.0.1:8610/api/models      # 24 个模型
curl -X POST http://127.0.0.1:8610/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"model":"anime_v1.0","prompt":"test","size":"1024x1024"}'   # 实测出图
```

## 注意事项

- 首次请求会注册新设备（installation_id + ECDSA 私钥），AppBMS 侧 trustLevel 通常为 `low`，不影响生图
- PRO 订阅按安装包标识（APP_ID / APP_VERSION=1.3.2 PRO）判定，新设备注册仍走同一 PRO 包
- 会话 TTL≈6h，客户端自动续签，无需手工干预
