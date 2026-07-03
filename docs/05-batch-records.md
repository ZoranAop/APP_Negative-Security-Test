# 05. 已执行批次记录

| 批次 | 素材来源                                   | 内容形式                                   | 用户           | 帖数              | 结果         |
| ---- | ------------------------------------------ | ------------------------------------------ | -------------- | ----------------- | ------------ |
| 2    | OpenNana 图库                              | 图文（直贴提示词）                         | 同 10 用户     | 10（每人 1 帖）   | 10/10 成功   |
| 3    | OpenNana 图库                              | 图文（改写为用户口吻）                     | 同 10 用户     | 10（每人 1 帖）   | 10/10 成功   |
| 4    | OpenNana 图库（美女类）                    | 图文（用户口吻）                           | 同 10 用户     | 20（每人 2 帖）   | 20/20 成功   |
| 5    | OpenNana 图库（视频）                      | 视频                                       | `u_1wvpv9ak`   | 1                 | 成功         |
| 6    | OpenNana 图库（女性主题）                  | 图文（中文用户口吻+多场景）                | 同 10 用户     | 50（轮询分发）    | 50/50 成功（9/10 账号活跃）|
| 7 (batch1)  | OpenNana ChatGPT                       | 图文（中文用户口吻）                       | 老企管 20 用户（首 200） | 100 (20×5)        | 100/100 成功 |
| 8 (batch2)  | OpenNana ChatGPT，美女题材              | 图文（英/繁中/日 三语言，主体第一人称）    | test env 20 用户（500 池随机）| 100 (20×5) | 100/100 成功 |
| 9 (batch3)  | **open-prompts.com + lovimg.com**（非广告） | 图文（英/繁中/日 三语言，模板池刷新）      | 同 batch2 20 用户 | 100 (20×5)        | 100/100 成功 |

## 使用的 10 个样本用户 ID（早期批次）

> 来自 `accounts_10.csv`（企管用户前 10）。**邮箱 / 密码不入库**。

```
u_1wvpv9ak / u_c7o4vtvf / u_kf0fr1sd / u_27bhmbok / u_4zbo8v0k
u_64jfd832 / u_dh23k4d7 / u_2o3wx5hv / u_7c2cn4oc / u_djgwgl1j
```

## 经验小结

1. **直贴提示词的效果差**（批次 2），需要改写成用户口吻（批次 3 起）。
2. **图文 + 美女题材** 推送效果最佳（批次 4 / 批次 6 / 批次 8-9）。
3. **视频** 单独走 `post_video.py`，详见 [`06-post-video.md`](06-post-video.md)。
4. **批量登录有限流风险**：
   - 批次 6 出现 1/10 触发 429；
   - 批次 7 并发登录 20 账号触发 12/20 429；
   - 结论：登录必须**顺序 + 间隔**，见 `scripts/publish_from_tokens.py`
     + 环境变量 `LOGIN_SPACING`（默认 2.5 s）。
5. **多语言文案**（批次 8-9）：英/繁中/日 各 33/34/33，成功率与单语一致。
   工具：`scripts/caption_multilang.py`（见 `docs/13-multilang-captions.md`）。
6. **广告 / 商业素材过滤**（批次 9）：`open-prompts` 46% 条目是广告 / 海报，
   需通过 `--exclude-ads` 过滤，参见 `docs/11-anti-ad-filtering.md`。
7. **多源采集**（批次 9）：`multi_source_fetch.py` 一次采样 opennana +
   open-prompts + lovimg 三源，配合 `--dedupe-file` 保证不重复。
8. **昵称不可通过前台 / admin API 修改**：广场后端把发帖时的 nickname
   作为快照存到帖子记录里；前台 API `/me` 只读；后台 `/admin/user/update`
   仅接受 `user_id + level` 两个字段。若必须改昵称，需要联系服务端团队
   加接口。
9. **PowerShell 5.1 调用 `Invoke-RestMethod` 时需手动把 body 编为 UTF-8 byte 数组**，
   否则中文 + emoji 会被服务端存为 `?`。Python `requests` 已规避此问题。
