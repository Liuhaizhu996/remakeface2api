# RemakeFace AppBMS Clean-Room Client

`RemakeFace Ai V1.3.2 PRO` 后端（`api.appbms.com`）的 clean-room 客户端实现与完整流程测试。
协议细节见 `docs/PROTOCOL.md`。

## 结构
```
remakeface-appbms/
├── client/remake_client.py   # 主客户端：签名请求、设备会话、S3 上传、AI 任务
├── tests/test_flow.py        # 冒烟：upload -> get-many-faces -> check-nsfw
├── tests/test_flow2.py       # E2E：upload x2 -> face_swap -> poll -> 下载产物
├── state/device_state.json   # 会话状态（安装 ID / 私钥 / deviceSession）
├── examples/                 # 本地测试输入/输出目录（图片不提交）
├── docs/PROTOCOL.md          # 协议还原记录
└── requirements.txt          # 仅 cryptography
```

## 安装
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 使用
```bash
# 1) 单文件跑通（自动注册/复用会话、上传、提脸、NSFW）
python3 tests/test_flow.py /path/to/source.jpg

# 2) 换脸 E2E（上传源图+目标图 -> 换脸 -> 轮询 -> 下载 result_swap.jpg）
python3 tests/test_flow2.py /path/to/source.jpg /path/to/target.jpg
```

## 状态文件
`state/device_state.json` 保存 installation_id、ECDSA 私钥、deviceSession。
会话过期（TTL≈6h）后 `ensure_session()` 自动走 challenge → register 重建。

## 已验证结果（2026-08-07/08）
- 设备会话注册/复用：通过
- 签名请求（ECDSA-SHA256 + nonce + timestamp + body-hash）：通过
- S3 直传：通过
- get-many-faces / check-nsfw / face-swap：全部 completed
- 换脸产物已验证可正常下载；本仓库不提交测试生成图片

## 生图
```bash
# AI 生图：参考图 -> 风格化输出（模型/比例见 docs/PROTOCOL.md）
python3 tests/test_gen.py /path/to/source.jpg "cyberpunk portrait, neon rim light" general_v4.0_s "1:1"
# 输出 examples/result_gen.webp（实际为 WebP/VP8）
```
