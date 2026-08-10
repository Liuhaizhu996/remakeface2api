# AppBMS / RemakeFace 协议还原记录

来源：`RemakeFace Ai V1.3.2 PRO.apk`（Pairip/R8 smali）clean-room 还原，仅依据可观测 HTTP 行为。

## 基址
- Base: `https://api.appbms.com`
- User-Agent: `okhttp/4.12.0`，Content-Type: `application/json`

## 1. 时间同步
```
GET /v1/time
-> { serverTimeMs: <ms> }
```
客户端缓存 `offset = serverTimeMs - now_ms`，用于签名时间戳。

## 2. Device Session 注册（ECDSA P-256）
```
POST /v1/device-sessions/challenges
  {platform:"android", appIdentifier, packageName, installationId, appVersion}
-> {challengeId, challenge, deviceSessionAttestationRequired, enabledAttestationProviders, ttlSeconds}

POST /v1/device-sessions     Header: X-Attestation-Recovery-Version: 1
  {platform, appIdentifier, packageName, challengeId, publicKeyPem, installationId, appVersion}
-> {deviceSessionId, expiresInSeconds|ttlSeconds, trustLevel, packageName, publicKeyFingerprint}
```
- 客户端生成 `secp256r1` 密钥对；公钥以 Android Keystore 风格 PEM（DER→base64 每 64 字符换行）提交。
- 会话默认 `trustLevel=low`，TTL 约 6 小时。

## 3. 请求签名
POST 需带 `X-Signed-Recovery-Version: 1`，请求头：
```
X-Device-Session-Id: <deviceSessionId>
X-Request-Timestamp: <unix_ms + server_offset>
X-Request-Nonce:     <16B random, base64url-nopad>
X-Body-SHA256:       <base64url-nopad(sha256(body))>
X-Device-Signature:  <base64url-nopad(ECDSA-SHA256(sign_string))>
```
`sign_string = METHOD \n PATH \n timestamp \n nonce \n deviceSessionId \n bodyHashB64`

401 错误码 `DEVICE_SESSION_REFRESH_REQUIRED / DEVICE_SESSION_INVALID / SESSION_INVALID / SIGNATURE_INVALID / UNAUTHORIZED` → 自动重注册重放一次。

## 4. 上传
```
POST /v1/storage/s3/presigned-url
  {purpose, contentType, fileName, contentLength}
-> {uploadUrl, method, headers, key}
```
直传 S3（默认 PUT），返回 `key` 用于后续 AI 调用（key 形如 `ai-generate/YYYY/MM/DD/ds_xxx/<purpose>-<uuid>.jpg`）。

## 5. AI 任务（异步，202 Accepted）
统一模式：`POST /v1/ai/<op>` 返回 202 + `{jobId, kind, statusUrl, statusExpiresInMs}`；
轮询 `GET <statusUrl>` 返回 `{state: pending|completed|failed, result, failedReason, pollAfterMs}`。

| 操作 | 路径 | 关键入参 |
|---|---|---|
| 提脸 | `/v1/ai/get-many-faces` | `imageKey`, `versi`(v3) |
| NSFW | `/v1/ai/check-nsfw` | `imageKey`, `source`(image) |
| 换脸 | `/v1/ai/face-swap` | `sourceImagePath`, `targetImagePath`, `queueType`(standard), `versi`, `isEnhance` |
| 多脸 | `/v1/ai/multi-face-swap` | `imageResourcePaths[]`, `targetImagePath`, `facesToSwap[]`, ... |
| 文生图 | `/v1/ai/ai-image-gen` | `imagePathList[]`, `prompt`, `imageRatio`, `model` |

- `get-many-faces` 结果：`result.faces[]` / `result.list_face[]`（RunPod 代理 URL）。
- `face-swap` 结果：`result` 为输出图片 URL（RunPod 代理静态资源）。

## 6. 已验证（2026-08-07/08 实测）
- 注册 / 会话复用：通过
- S3 上传：通过
- get-many-faces：completed，返回人脸 URL
- check-nsfw：completed
- face-swap：completed，输出有效 JPEG（1024x1536）

## 7. AI 生图（ai-image-gen）
```
POST /v1/ai/ai-image-gen
  {imagePathList: [key...], prompt, imageRatio, model}
```
- `imagePathList` 必填，可传 `image_uri_list` 别名；`prompt` ≤ 20000 字符。
- `imageRatio` 为**字符串**（非数组）：`Original`/`original`、`1:1`、`4:3`、`3:4`、`9:16`、`16:9`；空值默认 `original`。
- `model` 值（来自 APK y9.smali 硬编码）：
  | id | 显示名 |
  |---|---|
  | `general_v4.0_s` | General v4.0 |
  | `portrait_v3.2` | Portrait v3.2 |
  | `fantasy_v2.1` | Fantasy v2.1 |
- 结果（completed）：`result.imageUrls[]`（CDN，如 `https://cdn.appbms.com/temp/<uuid>.png`，实际为 WebP/VP8 编码）。
- 已实测：202 Accepted → 轮询 completed → 下载成功（1664x2496 WebP）。
