# 环境限制说明

当前仓库运行依赖以下外部工具（环境不可用时相关规则无法完全验证）：
- apktool / jadx / aapt2 / adb (Android 解析/运行时验证)
- apksigner / codesign (签名验证)
- unzip / python3 / pytest

无构建输入（APK/IPA）时：动态规则返回 SKIPPED（不允许直接 PASS）；静态规则在无输入时已注入 FAIL-OPEN 阻断逻辑（结构修复），完整行为验证仍需真实构建产物。
