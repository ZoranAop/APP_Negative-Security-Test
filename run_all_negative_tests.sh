#!/usr/bin/env bash
"""
一键运行所有负向安全测试脚本
"""

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 默认值
OUTPUT_DIR="results"
ARTIFACTS_DIR="security/artifacts"
PLATFORM="android,ios"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --apk)
            APK_FILE="$2"
            shift 2
            ;;
        --ipa)
            IPA_FILE="$2"
            shift 2
            ;;
        --manifest)
            MANIFEST_FILE="$2"
            shift 2
            ;;
        --info-plist)
            INFO_PLIST_FILE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --artifacts-dir)
            ARTIFACTS_DIR="$2"
            shift 2
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo "选项:"
            echo "  --apk FILE           APK 文件路径"
            echo "  --ipa FILE           IPA 文件路径"
            echo "  --manifest FILE      AndroidManifest.xml 路径"
            echo "  --info-plist FILE    Info.plist 路径"
            echo "  --output-dir DIR     输出目录 (默认: results)"
            echo "  --artifacts-dir DIR  构建产物目录 (默认: security/artifacts)"
            echo "  --platform LIST      测试平台，逗号分隔 (默认: android,ios)"
            echo "  --help               显示帮助"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# 创建输出目录
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/evidence"
mkdir -p "$OUTPUT_DIR/artifacts"

# 日志开始
log_info "开始运行负向安全测试套件"
log_info "输出目录: $OUTPUT_DIR"
log_info "构建产物目录: $ARTIFACTS_DIR"
log_info "测试平台: $PLATFORM"

# 运行测试脚本
TEST_SCRIPTS=(
    "check_debug_isolation.py:NS-01:调试面板/抓包隔离"
    "check_domain_isolation.py:NS-02:接口/域名/Associated Domains 隔离"
    "check_deep_link_isolation.py:NS-03:Android 深链域名按构建环境隔离"
    "check_log_isolation.py:NS-04:日志输出按构建环境隔离"
    "check_encryption_storage.py:NS-05:登录态迁移至 Keychain/加密存储"
    "check_ios_file_sharing.py:NS-06:关闭 iOS Documents 文件共享"
    "check_mock_data_removal.py:NS-07:移除生产包 mock 数据"
    "check_dart_obfuscation.py:NS-08:Flutter Release 启用 Dart 混淆与符号文件留存"
    "check_binary_integrity.py:NS-09:发布前自动校验生产 IPA/APK"
)

FAILED_TESTS=()
PASSED_TESTS=()

# 运行每个测试脚本
for TEST_SPEC in "${TEST_SCRIPTS[@]}"; do
    IFS=':' read -r SCRIPT TEST_ID TEST_NAME <<< "$TEST_SPEC"
    SCRIPT_PATH="security/scripts/$SCRIPT"
    
    log_info "运行测试: [$TEST_ID] $TEST_NAME"
    
    # 构建命令行参数
    CMD_ARGS=(
        "--output-json" "$OUTPUT_DIR/evidence/${TEST_ID}.json"
    )
    
    # 添加平台特定参数
    if [[ "$TEST_ID" == "NS-01" ]]; then
        CMD_ARGS+=(--apk "$APK_FILE" --ipa "$IPA_FILE" --manifest "$MANIFEST_FILE" --info-plist "$INFO_PLIST_FILE")
    elif [[ "$TEST_ID" == "NS-02" ]]; then
        CMD_ARGS+=(--manifest "$MANIFEST_FILE" --info-plist "$INFO_PLIST_FILE" --artifacts-dir "$ARTIFACTS_DIR")
    elif [[ "$TEST_ID" == "NS-03" ]]; then
        CMD_ARGS+=(--manifest "$MANIFEST_FILE")
    elif [[ "$TEST_ID" == "NS-04" ]]; then
        CMD_ARGS+=(--log-dir "logs" --apk "$APK_FILE")
    elif [[ "$TEST_ID" == "NS-05" ]]; then
        CMD_ARGS+=(--apk "$APK_FILE" --ipa "$IPA_FILE")
        # 添加 Hive 文件（如果存在）
        if [ -d "build/symbols/ios" ]; then
            HIVE_FILES=$(find "build/symbols/ios" -name "*.hive" -print0 | xargs -0 printf "%s,")
            if [ -n "$HIVE_FILES" ]; then
                CMD_ARGS+=(--hive-files "$HIVE_FILES")
            fi
        fi
    elif [[ "$TEST_ID" == "NS-06" ]]; then
        CMD_ARGS+=(--info-plist "$INFO_PLIST_FILE" --ipa "$IPA_FILE" --artifacts-dir "$ARTIFACTS_DIR")
    elif [[ "$TEST_ID" == "NS-07" ]]; then
        CMD_ARGS+=(--apk "$APK_FILE" --ipa "$IPA_FILE")
        if [ -f "pubspec.yaml" ]; then CMD_ARGS+=(--pubspec "pubspec.yaml"); fi
        if [ -d "lib" ]; then CMD_ARGS+=(--dart-lib "lib"); fi
        if [ -d "assets" ]; then CMD_ARGS+=(--assets-dir "assets"); fi
    elif [[ "$TEST_ID" == "NS-08" ]]; then
        CMD_ARGS+=(--apk "$APK_FILE" --ipa "$IPA_FILE" --artifacts-dir "$ARTIFACTS_DIR")
        if [ -f "build.log" ]; then CMD_ARGS+=(--build-log "build.log"); fi
    elif [[ "$TEST_ID" == "NS-09" ]]; then
        CMD_ARGS+=(--apk "$APK_FILE" --ipa "$IPA_FILE" --manifest "$MANIFEST_FILE" --info-plist "$INFO_PLIST_FILE")
    fi
    
    # 运行测试
    if python "$SCRIPT_PATH" "${CMD_ARGS[@]}" 2>&1 | tee "$OUTPUT_DIR/evidence/${TEST_ID}.log"; then
        log_success "[$TEST_ID] $TEST_NAME - 通过"
        PASSED_TESTS+=("$TEST_ID")
    else
        log_error "[$TEST_ID] $TEST_NAME - 失败"
        FAILED_TESTS+=("$TEST_ID")
    fi
done

# 生成汇总报告
log_info "生成测试汇总..."
cat > "$OUTPUT_DIR/summary.json" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "total_tests": ${#TEST_SCRIPTS[@]},
  "passed": ${#PASSED_TESTS[@]},
  "failed": ${#FAILED_TESTS[@]},
  "passed_tests": [$(printf '"%s",' "${PASSED_TESTS[@]}" | sed 's/,$//')],
  "failed_tests": [$(printf '"%s",' "${FAILED_TESTS[@]}" | sed 's/,$//')]
}
EOF

# 输出结果
if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    log_success "所有测试通过！(${#PASSED_TESTS[@]}/${#TEST_SCRIPTS[@]})"
    log_info "详细报告: $OUTPUT_DIR/summary.json"
    exit 0
else
    log_error "有 ${#FAILED_TESTS[@]} 项测试失败: ${FAILED_TESTS[*]}"
    log_info "详细报告: $OUTPUT_DIR/summary.json"
    log_info "请检查 $OUTPUT_DIR/evidence/ 目录获取具体错误信息"
    exit 1
fi