#!/usr/bin/env bash
# build-rimcrow-mac.sh — RimCrow macOS 一键打包（可选证书重签）
#
# 用法:
#   build-mac/build-rimcrow-mac.sh --trial   # 试构建（默认，用于验证管线）
#   build-mac/build-rimcrow-mac.sh --final   # 正式构建（前端 dist 应为最新）
#
# 可选环境变量:
#   RIMCROW_SIGN_IDENTITY  证书签名身份（codesign --sign 的值）。
#                          不设置 = 保留 PyInstaller 自带的 adhoc 签名，不做证书重签；
#                          设置   = 用该身份对 .app 统一重签，并硬校验
#                                   Authority=该身份、flags=0x0(none)、无 entitlements。
#                          本机可用身份：security find-identity -v -p codesigning
#   RIMCROW_DEST_APP       安装目标 .app 路径，默认 ~/Applications/RimCrow.app
#   RIMCROW_BUILD_ROOT     构建根目录，默认 /tmp/rimcrow-build
#   RIMCROW_SEED_LANGUAGE  可选，覆写首启种子 config 的界面语言（如 zh-CN）
#
# 设计要点:
#   1. 全程在 /tmp/rimcrow-build/ 构建，避开 iCloud / FinderInfo 附加属性；
#      只把最终产物 ditto 到 RIMCROW_DEST_APP。
#   2. 不给 PyInstaller 传 --codesign-identity（会强开 hardened runtime，
#      自签证书下包内动态库加载可能失败）；PyInstaller 先 adhoc 签，需要时再统一重签。
#   3. 不打包 Valve 的 libsteam_api.dylib：Steamworks 在打包层降级为可选，
#      运行时由后端从 Steam 游戏目录探测。
#   4. macOS 打包态数据目录在 ~/Library/Application Support/RimCrow
#      （backend/settings.py 已重定向），这里用 seed-data 做首启播种。
#
# 依赖: uv(0.13+)、macOS 自带 codesign/sips/iconutil/rsync/ditto；
#       证书重签模式还需要钥匙串里可用的签名身份。
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${RIMCROW_BUILD_ROOT:-/tmp/rimcrow-build}"
SRC_DIR="$BUILD_ROOT/src"
LOG_DIR="$BUILD_ROOT/logs"
APP_NAME="RimCrow"
DEST_APP="${RIMCROW_DEST_APP:-$HOME/Applications/$APP_NAME.app}"
SIGN_IDENTITY="${RIMCROW_SIGN_IDENTITY:-}"
MODE="trial"
START_TS=$(date +%s)

for arg in "$@"; do
  case "$arg" in
    --trial) MODE="trial" ;;
    --final) MODE="final" ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *)
      echo "未知参数: ${arg}（可用 --trial / --final）" >&2
      exit 2
      ;;
  esac
done

log() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

verify_app() {
  local app="$1"
  # rc 必须为 0，否则 set -e 直接中断
  codesign --verify --deep --strict "$app"
  if [ -z "$SIGN_IDENTITY" ]; then
    echo "✓ codesign --verify --deep --strict: rc=0（adhoc 模式，未做证书重签）"
    return 0
  fi
  local info
  info="$(codesign -dv --verbose=4 "$app" 2>&1)"
  if ! printf '%s\n' "$info" | grep -q "Authority=$SIGN_IDENTITY"; then
    printf '%s\n' "$info" >&2
    fail "签名 Authority 不是 $SIGN_IDENTITY"
  fi
  if ! printf '%s\n' "$info" | grep -q "flags=0x0(none)"; then
    printf '%s\n' "$info" >&2
    fail "签名 flags 不是 0x0(none)（可能开了 hardened runtime）"
  fi
  local ent
  ent="$(codesign -d --entitlements :- "$app" 2>/dev/null || true)"
  if printf '%s\n' "$ent" | grep -q "<key>"; then
    printf '%s\n' "$ent" >&2
    fail "包内存在 entitlements（本脚本口径要求无 entitlements）"
  fi
  echo "✓ codesign --verify --deep --strict: rc=0"
  echo "✓ Authority=$SIGN_IDENTITY | flags=0x0(none) | 无 entitlements"
}

# ---------- 0. 预检 ----------
log "0/7 预检"
if [ -n "$SIGN_IDENTITY" ]; then
  echo "签名模式: 证书重签（${SIGN_IDENTITY}）"
  security find-identity -v -p codesigning | grep -q "$SIGN_IDENTITY" \
    || fail "找不到签名身份: ${SIGN_IDENTITY}（可用 security find-identity -v -p codesigning 查看）"
  echo "✓ 签名身份存在: $SIGN_IDENTITY"
else
  echo "签名模式: adhoc（未设置 RIMCROW_SIGN_IDENTITY，保留 PyInstaller 自带 adhoc 签名）"
fi
command -v uv >/dev/null || fail "找不到 uv（$HOME/.local/bin）"
echo "✓ uv: $(uv --version)"
[ -f "$REPO_ROOT/frontend/dist/index.html" ] \
  || fail "frontend/dist/index.html 不存在，请先构建前端"
echo "✓ frontend/dist 时间戳: $(date -r "$REPO_ROOT/frontend/dist/index.html" '+%Y-%m-%d %H:%M:%S')"
mkdir -p "$BUILD_ROOT" "$LOG_DIR" "$(dirname "$DEST_APP")"

# ---------- 1. 生成 icon.icns ----------
log "1/7 生成 icon.icns"
ICON_DIR="$BUILD_ROOT/icon"
ICNS="$ICON_DIR/$APP_NAME.icns"
rm -rf "$ICON_DIR"
mkdir -p "$ICON_DIR"
# icon.svg 的 viewBox 是 96x96，先放大到 1024 再让 sips 渲染成 PNG（矢量放大，不糊）
sed 's/width="96" height="96"/width="1024" height="1024"/' "$REPO_ROOT/icon.svg" > "$ICON_DIR/icon-1024.svg"
sips -s format png "$ICON_DIR/icon-1024.svg" --out "$ICON_DIR/icon-1024.png" >/dev/null
ICONSET="$ICON_DIR/$APP_NAME.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_DIR/icon-1024.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$ICON_DIR/icon-1024.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICNS"
echo "✓ $ICNS ($(du -h "$ICNS" | cut -f1))"

# ---------- 2. rsync 源码到 /tmp ----------
log "2/7 rsync 源码 → $SRC_DIR"
rm -rf "$SRC_DIR"
mkdir -p "$SRC_DIR"
# 注意用 / 前缀锚定只排除仓库顶层目录（否则会把 frontend/dist 一起排掉）
rsync -a \
  --exclude='/.git' \
  --exclude='/.venv' \
  --exclude='/node_modules' \
  --exclude='/data' \
  --exclude='/cache' \
  --exclude='/backups' \
  --exclude='/dist' \
  --exclude='/build' \
  --exclude='/updates' \
  --exclude='__pycache__' \
  --exclude='.DS_Store' \
  --exclude='*.pyc' \
  "$REPO_ROOT"/ "$SRC_DIR"/
echo "✓ staging 体积: $(du -sh "$SRC_DIR" | cut -f1)"

# ---------- 3. seed-data（首启播种到 ~/Library/Application Support/RimCrow） ----------
log "3/7 准备 seed-data"
SEED_DIR="$SRC_DIR/seed-data"
mkdir -p "$SEED_DIR"
for item in config.json rules profiles idle.html idle_logs.html github_mirrors.json known_game_installs.json; do
  [ -e "$REPO_ROOT/data/$item" ] && cp -R "$REPO_ROOT/data/$item" "$SEED_DIR/"
done
# 可选：指定首启界面语言（如 zh-CN），只在种子 config 副本上改这一项，不改仓库源文件
if [ -n "${RIMCROW_SEED_LANGUAGE:-}" ] && [ -f "$SEED_DIR/config.json" ]; then
  python3 - "$SEED_DIR/config.json" "$RIMCROW_SEED_LANGUAGE" <<'PY'
import json, sys
path, language = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["language"] = language
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print(f"已把种子 config 的 language 覆写为 {language}")
PY
fi
echo "✓ seed-data: $(ls -A "$SEED_DIR" | tr '\n' ' ')"
# 说明：种子含本机已有 config.json（路径会在首启时由 apply_config_relocation 重定位），
# 不含各 SQLite 库（首启自动建库）。对外分发的构建建议去掉 config.json。

# ---------- 4. PyInstaller 打包 ----------
log "4/7 PyInstaller 打包（${MODE}）"
cd "$SRC_DIR"
# 复用仓库已有 .venv，避免在 /tmp 里重新安装整套依赖
export UV_PROJECT_ENVIRONMENT="$REPO_ROOT/.venv"
# 播种目录 + mac 图标（pack_pyinstaller.py 读取）
export RIMCROW_PACK_SEED_DATA="seed-data"
export RIMCROW_ICON_PATH="$ICNS"
# 注意：不传 --codesign-identity，让 PyInstaller 走默认 adhoc 签
uv run python pack_pyinstaller.py --skip frontend,docs,tree,zip \
  2>&1 | tee "$LOG_DIR/build-$MODE-$(date +%Y%m%d-%H%M%S).log"

APP_SRC="$SRC_DIR/dist/$APP_NAME.app"
[ -d "$APP_SRC" ] || fail "未生成 $APP_SRC"
[ -x "$APP_SRC/Contents/MacOS/$APP_NAME" ] || fail "包内缺少可执行文件 Contents/MacOS/$APP_NAME"
if ! find "$APP_SRC/Contents" -path "*frontend/dist/index.html" | grep -q .; then
  fail "包内缺少 frontend/dist/index.html（前端未打进包）"
fi
echo "✓ 产物: $APP_SRC ($(du -sh "$APP_SRC" | cut -f1))"

# ---------- 5. 签名 ----------
log "5/7 签名"
if [ -n "$SIGN_IDENTITY" ]; then
  echo "用证书统一重签: $SIGN_IDENTITY"
  xattr -cr "$APP_SRC"
  find "$APP_SRC" -name .DS_Store -delete
  codesign --force --deep --sign "$SIGN_IDENTITY" "$APP_SRC"
else
  echo "保留 PyInstaller 自带 adhoc 签名（未设置 RIMCROW_SIGN_IDENTITY）"
fi
verify_app "$APP_SRC"

# ---------- 6. 安装到目标路径 ----------
log "6/7 ditto → $DEST_APP"
if [ -d "$DEST_APP" ]; then
  # 不删除、直接替换不安全（旧文件残留）；先整体挪到 /tmp 备份，再从备份里清理。
  PREV="$BUILD_ROOT/prev-$APP_NAME.app"
  rm -rf "$PREV"
  mv "$DEST_APP" "$PREV"
  echo "✓ 旧版已备份到 $PREV"
fi
ditto "$APP_SRC" "$DEST_APP"
xattr -cr "$DEST_APP"
echo "✓ 已安装: $DEST_APP ($(du -sh "$DEST_APP" | cut -f1))"

# ---------- 7. 复验 + 报告 ----------
log "7/7 复验安装产物"
verify_app "$DEST_APP"
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
printf '\n\033[32m★ 构建完成（%s）: %s\033[0m\n' "$MODE" "$DEST_APP"
printf '  签名模式: %s\n' "$([ -n "$SIGN_IDENTITY" ] && echo "证书重签（${SIGN_IDENTITY}）" || echo "adhoc（PyInstaller 默认）")"
printf '  耗时: %ss | 体积: %s\n' "$DURATION" "$(du -sh "$DEST_APP" | cut -f1)"
printf '  Bundle ID: %s\n' "$(plutil -extract CFBundleIdentifier raw "$DEST_APP/Contents/Info.plist" 2>/dev/null || echo '?')"
printf '  构建日志: %s\n' "$(ls -t "$LOG_DIR"/build-"$MODE"-*.log | head -1)"
printf '  PyInstaller 日志: %s\n' "$SRC_DIR/dist/pyinstaller-build.log"
