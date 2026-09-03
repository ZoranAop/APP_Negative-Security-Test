# GLEEZY PRO ADB 提取指南

## 概述

通过 ADB 连接 MuMu 模拟器，导出 GLEEZY PRO 应用数据（数据库、缓存图片），用于更新素材库。

## 前置条件

1. **MuMu 模拟器已安装并运行**
   - 安装路径：`D:\程序\模拟器\MuMuPlayer`
   - ADB 路径：`D:\程序\模拟器\MuMuPlayer\nx_main\adb.exe`

2. **GLEEZY PRO 应用已安装到模拟器**
   - 包名：`com.I98Gj.BF1rt2`
   - 如未安装，需先通过 APK 安装：`adb install gleezy_pro.apk`

3. **Python 依赖**
   ```powershell
   pip install requests boto3
   ```

## 使用步骤

### Step 1: 连接模拟器

```powershell
# 设置 ADB 路径
$env:ADB_PATH = "D:\程序\模拟器\MuMuPlayer\nx_main\adb.exe"

# 检查设备连接
& $env:ADB_PATH devices
```

预期输出：
```
List of devices attached
emulator-5554    device
```

### Step 2: 获取 Root 权限

```powershell
& $env:ADB_PATH root
# 输出: restarting adbd as root
```

### Step 3: 导出应用数据

```powershell
# 运行导出脚本
py -3 scripts/fetch_gleezy_adb.py
```

脚本会自动：
- 检测 GLEEZY PRO 包名
- 导出数据库文件（wk_*.db, gleezy_downloads.db, libCachedImageData.db）
- 保存到 `gleezy_dump/` 目录

### Step 4: 分析数据

```powershell
# 查看各群消息分布
py -3 scripts/check_gleezy_status.py
```

输出示例：
```
[channels] 共 36 个频道
  群聊: 22, 私聊: 14

[messages] 共 32 条消息
  文本: 27, 视频: 1, 机器人: 4

[historical data] 2657 images from previous extraction
```

### Step 5: 提取图片并生成素材

```powershell
# 从数据库提取图片 URL
py -3 scripts/extract_gleezy_images.py

# 或从历史数据生成 CSV 素材
py -3 scripts/restore_gleezy_data.py
```

## 数据库结构

### 主数据库 (wk_*.db)

| 表名 | 说明 |
|------|------|
| `channel` | 频道/群组信息 |
| `message` | 消息记录 |
| `conversation` | 会话列表 |

### message 表字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | INTEGER | 消息类型：1=文本，3=图片，4=视频，5=视频，2000=机器人 |
| `content` | TEXT | JSON 格式内容 |
| `channel_id` | TEXT | 频道 ID |
| `timestamp` | INTEGER | 时间戳 |

### content 字段示例

**文本消息：**
```json
{"content": "分享文字内容", "type": 1}
```

**图片消息：**
```json
{"url": "file/preview/chat/large/2/channel_id/filename.jpg", "width": 720, "height": 1280}
```

**视频消息：**
```json
{"url": "file/preview/chat/large/2/channel_id/filename.mp4", "second": 15, "width": 720, "height": 1280}
```

## 常见问题

### Q: ADB 连接失败

```powershell
# 重启 ADB server
& $env:ADB_PATH kill-server
& $env:ADB_PATH start-server

# 重新连接
& $env:ADB_PATH connect 127.0.0.1:7555
```

### Q: 无法获取 Root 权限

MuMu 模拟器默认开启 root 权限。如提示失败：
1. 检查 MuMu 设置 → 开启"启用 root 权限"
2. 重启模拟器后重试

### Q: 数据库导出为空

模拟器中的 GLEEZY PRO 数据可能是当前会话的 subset。历史数据存储在 `sources/customs_images.json`，可通过 `restore_gleezy_data.py` 恢复。

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `fetch_gleezy_adb.py` | ADB 连接并导出应用数据 |
| `check_gleezy_status.py` | 检查各群消息和图片状态 |
| `extract_gleezy_images.py` | 从数据库提取图片 URL |
| `restore_gleezy_data.py` | 从 git 历史数据恢复并生成 CSV |

## 后续使用

生成的 CSV 素材可直接用于发布：

```powershell
# 发布到房间（不同步广场）
py -3 scripts/post_room_moments.py ^
    --csv moments_gleezy_final.csv ^
    --email u_xxx@xxai.com ^
    --password YOUR_PASSWORD ^
    --room-id "!RoomId:xxai.com"
```
