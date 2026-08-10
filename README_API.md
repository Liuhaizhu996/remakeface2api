
## WebUI + OpenAI 兼容网关（已部署）

服务已跑在 `0.0.0.0:8610`（本机 + 局域网可访问），后端 `server/app.py` + 前端 `server/static/index.html`。

### WebUI
```
http://<服务器IP>:8610/
```
模型选择 / 比例 / 提示词 / 可选参考图 → 开始生成 → 画廊展示 + 下载原图 + 最近任务历史（持久化到 `server/data/jobs.json`）。

### OpenAI 兼容接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/v1/models` | 列出可用模型（OpenAI 格式） |
| POST | `/v1/images/generations` | 同步文生图（OpenAI Images API 兼容） |
| GET  | `/api/health` | 服务 + 设备会话状态 |
| GET  | `/api/models` | 内置模型列表 |
| GET  | `/api/ratios` | 支持比例 |
| POST | `/api/generate` | 异步生图（multipart，可选参考图） |
| GET  | `/api/jobs/{jobId}` | 查询任务状态 |
| GET  | `/api/image/{name}` | 取生成产物 |
| GET  | `/api/history` | 最近任务 |

### 可用模型
| id | 名称 | 说明 |
|---|---|---|
| `general_v4.0_s` | General v4.0 | 通用平衡模型 |
| `portrait_v3.2` | Portrait v3.2 | 人像/肤色/光影优化 |
| `fantasy_v2.1` | Fantasy v2.1 | 幻想场景风格化 |

### 比例
`Original`、`1:1`、`4:3`、`3:4`、`9:16`、`16:9`
（OpenAI size 参数映射：`1024x1024`→`1:1`、`1024x1792`→`9:16`、`1792x1024`→`16:9`、`768x1024`→`3:4`、`1024x768`→`4:3`）

### curl 示例
```bash
# 列出模型
curl http://127.0.0.1:8610/v1/models

# 文生图（OpenAI 兼容）
curl -X POST http://127.0.0.1:8610/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"model":"general_v4.0_s","prompt":"a cyberpunk city at night, neon lights","size":"1024x1024","n":1}'
# -> {"created":..., "data":[{"url":"/api/image/v1_xxx_0.png"}]}

# 带参考图（异步）
curl -X POST http://127.0.0.1:8610/api/generate \
  -F "prompt=a portrait in oil painting style" \
  -F "model=portrait_v3.2" -F "ratio=1:1" \
  -F "file=@/path/to/ref.jpg"
# -> {"jobId":"..."} 然后轮询 /api/jobs/{jobId}
```

### 服务管理
```bash
cd /home/liuhaizhu/remakeface-appbms
./server/start.sh                        # 前台启动
PORT=8610 .venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8610
```
生成产物缓存：`server/data/generated/`；历史：`server/data/jobs.json`；会话状态：`state/device_state.json`。
