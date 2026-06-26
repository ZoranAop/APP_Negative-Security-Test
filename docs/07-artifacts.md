# 07. 产物文件清单

> 真实运行时的工作目录通常长这样（这些产物**不入库**，由 `.gitignore` 排除）。

| 文件                                              | 说明                              |
| ------------------------------------------------- | --------------------------------- |
| `post_moments.py` 等                              | 仓库下载的发帖工具                |
| `accounts_10.csv`                                 | 10 个用户子集                     |
| `moments.csv`                                     | 批次 1：纯文字素材                |
| `moments_gallery.csv`                             | 批次 2：图文素材（直贴版）        |
| `moments_gallery_v2.csv`                          | 批次 3：图文素材（改写版）        |
| `moments_beauty.csv`                              | 批次 4：美女图文素材（20 条）     |
| `build_gallery_csv.py` / `build_beauty_csv.py`    | 素材生成脚本                      |
| `beauty_images.json`                              | 美女案例真实图片 URL              |
| `post_video.py`                                   | 视频发布脚本                      |
| `images/` `media/`                                | 下载的图片 / 视频                 |
| `result/`                                         | 各批次发布结果 CSV + summary      |
