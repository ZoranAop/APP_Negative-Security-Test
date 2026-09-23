# 外部工具固化（不入库二进制）

本目录固化三个 wrapper 脚本，指向本机安装的外部工具：

| 脚本 | 用途 | 外部工具位置 |
|---|---|---|
| aapt2_dump_manifest.bat | 解析 binary AndroidManifest.xml（NS-02/03/14 确定性结论） | build-tools/android-14/aapt2.exe |
| apksigner_verify.bat | 真实签名验证 + 证书指纹（NS-09） | build-tools/android-14/lib/apksigner.jar + JDK 17 |
| unzip_fallback.bat | 解包 APK/IPA（NS-04/09/11） | tools/unzip/unzip.exe |

## 一键执行（APK 在场）

\\\ash
# 1. apksigner 验证（真实签名 + 证书）
call security/tools/apksigner_verify.bat C:/path/to/app-release.apk

# 2. aapt2 解析 manifest（确定性 NS-02/03/14）
call security/tools/aapt2_dump_manifest.bat C:/path/to/app-release.apk

# 3. unzip 解包（NS-04/09/11 运行）
call security/tools/unzip_fallback.bat C:/path/to/app-release.apk -d C:/tmp/apk
\\\

## 安装外部工具（一次性）

- \u5b89\u88c5 unzip\uff1a\winget install GnuWin32.Unzip\
- \u5b89\u88c5 JDK 17\uff1a\winget install Microsoft.OpenJDK.17\
- \u4e0b\u8f7d Android build-tools 34\uff1a\curl -L -o build-tools.zip https://dl.google.com/android/repository/build-tools_r34-windows.zip\

本目录仅含 wrapper .bat，不含大体积二进制（gitignore \u89c4\u5219\u5df2\u8986\u76d6）。
