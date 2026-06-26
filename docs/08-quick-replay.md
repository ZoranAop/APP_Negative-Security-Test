# 08. 复用步骤速查（下次发布）

## 通用前置

```powershell
# 1. py -3 环境
py -3 --version

# 2. 装依赖
py -3 -m pip install -r scripts/requirements.txt
#    最小集：requests boto3 python-dotenv

# 3. 配置 .env
Copy-Item .env.example .env
# 编辑 .env，填好凭证

# 4. 准备账号 CSV（含"邮箱""密码"列）
#    建议放到工作目录，命名如 accounts_10.csv
```

## 图文 / 文本

```powershell
# 1. 取素材：调 OpenNana / 热点接口
py -3 scripts/opennana_fetch.py --media-type image --page 1 --output moments.csv

# 2. 改写成用户口吻文案 → 写入素材 CSV
#    （可走 post_single_moment_vision.py 让 LLM 直接改写，也可手工）

# 3. 批量发帖
py -3 scripts/post_moments.py `
    --accounts-csv accounts_10.csv `
    --csv moments.csv `
    --num-accounts 0 `
    --num-posts 0 `
    --concurrency 1 `
    --delay 2.0
```

## 视频

```powershell
# 编辑 post_video.py 里的常量（或通过命令行参数传入）：
#   VIDEO_URL / COVER_URL / CAPTION / 账号
py -3 scripts/post_video.py `
    --account some@email.com `
    --video https://api.opennana.com/path/to.mp4 `
    --cover https://api.opennana.com/path/to.png `
    --caption "今日穿搭 #国风"
```

## 验证

```powershell
# 查 result/ 下结果与 moment_id
Get-ChildItem result\ | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

## 安全提示

- 流程涉及明文账号密码与 token。
- **任务结束后视情况轮换凭证**。
- 真实账号 CSV 永远不要 commit。
