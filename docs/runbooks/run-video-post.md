# Runbook：视频发帖

## 目标

把 OpenNana 上的一个视频（含封面）通过指定账号发布到 XXAI 广场。

## 前置

- 已完成 [`docs/02-environment.md`](../02-environment.md) 的 4 步准备。
- `.env` 已填好。
- 已确认要用的账号在 `accounts_10.csv` 内。

## 步骤

```powershell
py -3 scripts/post_video.py `
    --account "your_account_email@example.com" `
    --video   "https://api.opennana.com/path/to/video.mp4" `
    --cover   "https://api.opennana.com/path/to/cover.png" `
    --caption "今日穿搭 国风变装 #今日穿搭 #国风"
```

脚本内部会按以下顺序执行：

1. 用 `--account` 在 `accounts_*.csv` 里找密码并登录拿 token。
2. `POST /file/upload/credentials` 拿 S3 临时凭证。
3. 下载视频 + 封面（带 `Referer: https://opennana.com/`）。
4. boto3 上传到 S3。
5. `POST /api/v1/moments/` 发布（media_info `type=video` + `video_url` + `thumbnail_url`）。

## 验收

```powershell
# 看脚本输出的 moment_id
# 用账号本人 App 端或下面接口确认：
$tok = '<bearer>'
Invoke-RestMethod -Headers @{ Authorization = "Bearer $tok" } `
                  -Uri "${env:MOMENTS_API_URL}<moment_id>"
```

## ⚠️ 失败回滚

如果探测格式失败留下了废帖：

```powershell
$tok = '<bearer>'
foreach($id in @('722391483944013824','722391487538532352')){
  Invoke-RestMethod -Method Delete -Headers @{ Authorization = "Bearer $tok" } `
                    -Uri "${env:MOMENTS_API_URL}$id"
}
```
