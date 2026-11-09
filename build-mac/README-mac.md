# RimCrow macOS 打包与本地签名（build-mac/）

本目录是 RimCrow 在 macOS 上的「打包 .app + 可选本地签名」一键管线，只在 mac 分支使用；
Windows 侧仍走原来的 `pack_pyinstaller.py` 打包流程（本目录不影响 Win）。

## 命令

```bash
# 试构建（默认）：用当前 frontend/dist 验证管线
build-mac/build-rimcrow-mac.sh --trial

# 正式构建：前端修完 / dist 是最新时用
build-mac/build-rimcrow-mac.sh --final

# 自定义安装目标 / 构建目录（默认 ~/Applications/RimCrow.app 与 /tmp/rimcrow-build）
RIMCROW_DEST_APP=/tmp/RimCrow.app RIMCROW_BUILD_ROOT=/tmp/rimcrow-build \
  build-mac/build-rimcrow-mac.sh --trial
```

## 两种签名模式（重点）

| 模式 | 触发方式 | 行为 |
|---|---|---|
| **adhoc（默认）** | 不设置 `RIMCROW_SIGN_IDENTITY` | 保留 PyInstaller 自带的 adhoc 签名，本脚本不做证书重签；只校验 `codesign --verify --deep --strict` rc=0。适合本机自用、CI 试构建。 |
| **证书重签** | `RIMCROW_SIGN_IDENTITY="证书签名身份"` | 先 `xattr -cr` + 清 `.DS_Store`，再 `codesign --force --deep --sign "<身份>"` 统一重签；硬校验：`codesign --verify --deep --strict` rc=0、`Authority=<身份>`、`flags=0x0(none)`、无 entitlements。适合分发给本机其他用户或固定签名身份的场景。 |

```bash
# 证书重签模式（身份名以本机钥匙串为准：security find-identity -v -p codesigning）
RIMCROW_SIGN_IDENTITY="例如个人自签证书名" build-mac/build-rimcrow-mac.sh --final
```

签名口径说明：

- **不要**给 PyInstaller 传 `--codesign-identity`：那会强开 hardened runtime，
  自签证书下包内动态库加载可能失败。PyInstaller 默认 adhoc 签即可，需要证书时构建完统一重签；
- 本脚本不写 entitlements、不加 `--options runtime`、不做 notarize；
- 自签证书没有 notarize 时 `spctl --assess` 会 `rejected`，属于正常现象；拷贝到其他机器后
  可能需要先 `xattr -cr <app>` 清掉隔离属性再打开。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `RIMCROW_SIGN_IDENTITY` | 空（adhoc） | 证书签名身份；设置后走统一重签 + 硬校验，见上表 |
| `RIMCROW_DEST_APP` | `~/Applications/RimCrow.app` | 最终 .app 安装路径 |
| `RIMCROW_BUILD_ROOT` | `/tmp/rimcrow-build` | 构建根目录（staging、图标、日志都在这里） |
| `RIMCROW_SEED_LANGUAGE` | 空 | 可选，覆写首启种子 config 的界面语言（如 `zh-CN`） |

脚本内部还会给 `pack_pyinstaller.py` 传两个变量（维护者用）：
`RIMCROW_ICON_PATH`（mac 用 `.icns` 图标）、`RIMCROW_PACK_SEED_DATA`（首启播种目录）。

## 管线做了什么（7 步）

1. 预检：确认 `uv`、`frontend/dist/index.html` 存在；证书模式还会 `security find-identity`
   确认签名身份可用；
2. 生成 `RimCrow.icns`：把 `icon.svg` 的 viewBox 放大到 1024 后用 `sips` 渲染 PNG，
   再由 `sips` 生成各尺寸 iconset、`iconutil` 合成 `.icns`（矢量放大，不糊）；
3. `rsync` 源码到 `$RIMCROW_BUILD_ROOT/src`（排除 `.git/.venv/node_modules/data/cache/backups/__pycache__/dist`），
   避开 iCloud / FinderInfo 附加属性；
4. 组 `seed-data`：从仓库 `data/` 复制 `config.json`、`rules/`、`profiles/`、
   `idle*.html`、`github_mirrors.json`、`known_game_installs.json`（**不含** SQLite 库，首启自动建库），
   通过 `RIMCROW_PACK_SEED_DATA` 交给打包脚本打进包内 `data/`；
5. `uv run python pack_pyinstaller.py --skip frontend,docs,tree,zip`（复用仓库 `.venv`，
   通过 `UV_PROJECT_ENVIRONMENT` 指定，不在 /tmp 重装依赖）；
6. 按签名模式处理（adhoc 保留 / 证书重签）并校验；
7. `ditto` 到 `RIMCROW_DEST_APP`，再对安装产物复验一次，输出耗时/体积/日志路径。

构建日志：`$RIMCROW_BUILD_ROOT/logs/build-<mode>-<时间戳>.log`、
`$RIMCROW_BUILD_ROOT/src/dist/pyinstaller-build.log`。

## 依赖

- macOS、Xcode Command Line Tools 提供的 `codesign`/`sips`/`iconutil`/`rsync`/`ditto`；
- `uv` 0.13+（`~/.local/bin/uv`），仓库 `.venv` 已由 `uv sync` 准备好（含 pyinstaller、pywebview、pyobjc）；
- 证书重签模式还需要钥匙串里可用的签名身份（`security find-identity -v -p codesigning`）；
- 前端产物：`frontend/dist/`（不在 git 里，需 `cd frontend && npm run build` 生成）。

## macOS 专属实现说明

### 数据目录

`backend/settings.py` 在「macOS + PyInstaller 打包态」会把 `HOME_DIR` 从 `Contents/MacOS`
重定向到 `~/Library/Application Support/RimCrow`。原因：包内写 `data/` 会让
`codesign --verify` 失败，且换版本会丢配置。首次启动时若包内含 `data/`（即本脚本的 seed-data），
会复制一份到用户目录作为初始数据；之后只读写用户目录。Windows/Linux 行为不变。

### 图标

Windows 用 `icon.ico`；macOS 必须 `.icns`，由脚本从 `icon.svg` 现场生成，
通过 `RIMCROW_ICON_PATH` 交给 `pack_pyinstaller.py`（该脚本在 mac 上会跳过非 `.icns` 图标）。

### Steamworks 与 Valve 动态库

打包层把 Steamworks 降级为**可选**：`submodules/SteamworksPy` 存在时随包分发纯 Python 的
`steamworks` 模块；缺少 `tools/steamworks/*.dylib` 时跳过 `--add-data`，不报错。

**不打包、不拷贝 Valve 的 `libsteam_api.dylib`**：该库的许可与分发受限，
运行时由后端从 Steam 游戏目录探测加载（macOS 上位于
`.../steamapps/common/RimWorld/RimWorldMac.app/Contents/PlugIns/steam_api.bundle/...`）。

## 已知限制

- 自签证书无 notarize：`spctl --assess` 会 rejected（正常）；跨机器需 `xattr -cr`；
- adhoc 模式下产物未绑定证书身份，`codesign -dv` 显示 `Signature=adhoc`；
- 未编译 macOS 版 `SteamworksPy.dylib`，工坊运行时能力依赖后端从游戏目录探测；
- 构建产物在 `$RIMCROW_BUILD_ROOT`（默认 /tmp，重启会被清理），最终只保留 `RIMCROW_DEST_APP`；
- 首次启动会生成 `~/Library/Application Support/RimCrow/data/`（config、数据库、日志），
  替换新版本时先退出旧进程再覆盖（SQLite 抢锁）；换版本构建前建议先退出应用。
