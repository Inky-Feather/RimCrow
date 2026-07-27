# RimCrow

<img src="./doc/assets/Preview.png" style="width:50%;" />

RimCrow（原名 RimModManager）是一个面向 **RimWorld** 的桌面模组管理器，把模组扫描、排序、备份、工坊管理、Git 来源安装、日志排错、贴图优化和 AI 辅助集中到一个界面里，减少手动翻文件夹和反复切窗口的成本。

![主界面](./doc/assets/主界面.png)

## 阅读导航

- 普通玩家：优先看 [主要功能](#主要功能)、[发布版下载与升级](#发布版下载与升级)、[普通用户快速上手](#普通用户快速上手)、[常见问题排查](#常见问题排查)。
- 开发人员：优先看 [开发与本地运行](#开发与本地运行)、[Steamworks 运行库](#steamworks-运行库)、[测试与维护脚本](#测试与维护脚本)、[打包](#打包)。
- 翻译贡献：优先看 [多语言与翻译贡献](#多语言与翻译贡献)。
- Mod 作者：可直接看 [Mod 创作者工具规划](#mod-创作者工具规划)。
- 贴图优化：详细说明见 [贴图优化说明](./doc/贴图优化说明.md)。

## 兼容状态

| 平台 | 当前状态 | 说明 |
| --- | --- | --- |
| Windows | 主要支持平台 | 桌面应用、打包和完整功能主要按 Windows 验证，需要 WebView2 Runtime。 |
| macOS | 基础路径支持 | 主程序启动、RimWorld / Steam / 用户数据 / Player.log 定位和基础 Steam 启动路径可用；SteamworksPy 编译产物和打包质量暂不承诺。 |
| Linux | 逐步补充 | 已扩展部分 Steam 路径识别，但桌面运行、Steamworks 和打包分发暂不保证。 |

## 主要功能

- 模组扫描、启用 / 停用列表、分组、标签、颜色、备注和批量编辑。
- 加载顺序查看、保存、备份、差异对比和多格式导入导出。
- 自动排序、社区规则、用户规则、依赖关系、联锁模组和常见问题提示。
- Steam Workshop 搜索、工坊 ID 搜索、合集解析、SteamCMD 下载、Steam 客户端订阅管理和内置工坊浏览。
- GitHub / GitLab / GitGud / zip 直链等 Git 模组来源订阅、部署记录和推荐清单来源补全。
- 模组残留扫描、重复包名 / 共存版本识别、缺失项检查和清理辅助。
- 贴图优化，支持 DDS 生成、ZSTD 输出、缩放、自动回退、失败统计、历史结果和残留清理；详细说明见 [贴图优化说明](./doc/贴图优化说明.md)。
- 推荐清单导出，支持文本、Markdown、DOCX、PDF、图片、游戏版本、语言包附录和动图。
- 游戏日志查看、错误聚类、文件内容搜索和 AI 日志诊断辅助。
- AI 批量生成模组别名，支持长文本动态裁切、Token 分块、并发限流和实时进度反馈。
- 多语言界面、翻译模式、用户覆盖语言包和外部翻译工作文件导入导出。


## 发布版下载与升级

不参与开发时，建议直接使用发布版，不需要配置 Python、Node.js 或前端构建环境。

### 下载渠道

- 蓝奏云：https://wwbns.lanzouu.com/b00mq4tqgf
  提取密码：`aite`
- GitHub Releases：https://github.com/Inky-Feather/RimCrow/releases

### 全新安装

1. 下载完整发布包。
2. 解压到一个固定目录。
3. 启动程序后选择 RimWorld 本体目录、用户数据目录和 Workshop 目录。
4. 扫描模组，再按需要管理加载顺序、分组、标签、规则和备份。

### 旧版升级

- 新版 RimCrow 可直接覆盖旧版 RimModManager，并继承数据和凭据。
- 程序更新前会备份配置；涉及数据库结构变更时会自动备份数据库。
- 升级前建议先关闭游戏和管理器。
- 发布包应保持目录完整，不建议只替换单个 exe 或随意删除配套文件。

### 更新失败处理

- 优先换用另一个发布渠道重新下载完整发布包覆盖。
- 如果内置更新安装失败，手动解压完整包通常可以恢复。
- 不确定缓存是否异常时，可先关闭程序，再清理程序目录下临时缓存后重新启动。

## 普通用户快速上手

1. 准备 RimWorld 本体和需要管理的模组环境。
2. 下载发布版并完整解压。
3. 首次启动后确认游戏本体、用户数据、Workshop 和管理器库路径。
4. 执行模组扫描，确认工坊、本地和管理器库模组都能正常显示。
5. 使用列表、分组、标签、规则和自动排序整理加载顺序。
6. 保存前先查看问题提示和排序差异；重要列表建议保留备份。


## 常见问题排查

### 启动与窗口

- 启动白屏或窗口加载超时：先确认 Windows WebView2 Runtime 已安装；仍异常时可尝试浏览器模式。
- 窗口跑到屏幕外或尺寸异常：使用 `uv run python main.py --reset-window-state` 重置窗口状态。
- 前端资源缺失：开发模式需要先运行 Vite 服务；本地构建模式需要先执行 `npm run build`。

### 模组与下载

- SteamCMD 下载失败：检查 SteamCMD 环境、SteamCMD 代理、网络连通性、磁盘空间和目标工坊项状态。
- 工坊项缺失或失效：先重新扫描，再检查工坊项是否仍公开可访问。
- 游戏或数据路径识别异常：重新选择 RimWorld 本体目录、用户数据目录和 Workshop 目录后重新扫描。

### AI 与网络

- AI 请求失败：检查协议、Base URL、API Key、模型名、代理、额度和服务商状态。
- GitHub、蓝奏云、社区规则或外置数据库无法访问：先确认代理和网络，再切换备用来源。

### 更新与数据

- 更新失败：换用另一个发布渠道下载新版，或手动下载完整包覆盖。
- 数据异常：先保留现有目录和备份，不要直接删除数据库；必要时使用程序内的修复或恢复功能。

## 隐私与安全

- RimCrow 主要处理本机 RimWorld、模组、配置、日志和管理器数据库。
- AI API Key、Steam Web API Key、代理用户名和密码属于受保护字段，优先保存到系统凭据库。
- 如果系统凭据库不可用，程序会回退到明文暂存并给出提示；不建议在共享电脑上保存敏感凭据。
- 写入配置文件时会清空受保护字段，接口调用日志和 AI 请求参数会做脱敏处理。
- 使用 AI、Steam、GitHub、蓝奏云、社区规则或外置数据库功能时，请求会发送到对应第三方服务。
- 不需要联网的本地列表管理、排序、备份等功能仍可本地使用。
- 分享日志、配置或导出包前，建议自行检查是否包含本地路径、模组清单、游戏日志或其它个人信息。

## 开发与本地运行

### 分支说明

- `main` 分支跟随发布打包和存档节点，适合查看相对稳定的发布状态，但不代表最新开发进度。
- `dev` 分支是当前最新开发分支。准备提交代码、文档或跟进最新功能时，建议基于 `dev` 分支开始。
- 普通用户优先使用发布版下载渠道，不建议直接从开发分支运行未打包代码。

### 技术栈

- 后端：Python 3.11
- 前端：Vue 3 + Vite
- 桌面壳：pywebview
- 依赖管理：uv
- 测试：pytest
- 打包：PyInstaller / Nuitka

### 前置依赖

| 依赖 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Python | 3.11+ | 3.11+ | 3.11+ |
| Node.js | 18+ | 18+ | 18+ |
| uv | 必需 | 必需 | 必需 |
| WebView2 Runtime | 桌面模式必需 | 不需要 | 不需要 |
| Steamworks SDK | 完整 Steam 客户端工坊功能需要 | 需要自行编译 | 需要自行编译 |

### 克隆源码

拉取仓库和子模块。开发和提交建议基于 `dev`：

```powershell
git clone --recurse-submodules https://github.com/Inky-Feather/RimCrow
cd RimCrow
git switch dev
```

如果克隆时没有带 `--recurse-submodules`，在仓库目录补执行：

```powershell
git submodule update --init --recursive
```

### 安装依赖

安装 Python 依赖：

```powershell
uv sync
```

安装前端依赖：

```powershell
cd frontend
npm install
cd ..
```

### 启动方式

前端开发模式适合日常界面开发和联调。先启动 Vite：

```powershell
cd frontend
npm run dev
```

再回到项目根目录启动桌面应用：

```powershell
cd ..
uv run python main.py
```

本地构建模式更接近发布形态。先构建前端静态文件：

```powershell
cd frontend
npm run build
cd ..
```

再启动应用：

```powershell
uv run python main.py
```

桌面模式受 WebView2 或本地环境影响时，可使用浏览器模式排查：

```powershell
uv run python main.py --browser
```

重置窗口位置和尺寸：

```powershell
uv run python main.py --reset-window-state
```

## Steamworks 运行库

Steamworks 相关功能需要两类文件：

- `SteamworksPy`：项目通过 `submodules/SteamworksPy` 固定源码版本，提供 Python 包和可编译的 wrapper 源码。
- Steamworks SDK redistributable：提供 `steam_api64.dll`、`libsteam_api.so`、`libsteam_api.dylib` 等运行库。

如果只使用普通扫描、排序、SteamCMD 下载等功能，可以跳过本节。需要通过已登录的 Steam 客户端执行订阅、取消订阅、读取工坊状态或后续下载触发能力时，需要完成运行库准备。

先从 [Steamworks Partner](https://partner.steamgames.com/) 获取 Steamworks SDK，并保留下载得到的 `steamworks_sdk_*.zip`。Steamworks SDK 通常需要 Steamworks 账号权限。

推荐通过参数指定 SDK zip，生成本地运行库目录：

```powershell
uv run python scripts/setup_steamworks_runtime.py --sdk "<path-to-steamworks_sdk_*.zip>"
```

也可以用环境变量指定 SDK zip：

```powershell
$env:STEAMWORKS_SDK_ZIP="<path-to-steamworks_sdk_*.zip>"
uv run python scripts/setup_steamworks_runtime.py
```

脚本会把文件归拢到：

```text
tools/steamworks/
```

当前 Windows 可直接复制 `submodules/SteamworksPy/redist/windows/SteamworksPy64.dll`。Linux 和 macOS 的 `SteamworksPy.so` / `SteamworksPy.dylib` 需要在对应平台用 Steamworks SDK 编译后放入 `tools/steamworks/`。

说明：

- `tools/` 是本地运行目录，默认不提交到 git。
- `tools/steamworks/` 只存放 Steamworks 运行库；程序会在 `cache/steamworks_runtime` 自动重建可写运行环境。
- `SteamworksPy64.dll` 与 `steam_api64.dll` 最好来自同一 Steamworks SDK 版本的编译 / redistributable 组合。

## 测试与维护脚本

### 测试

建议优先运行正式测试目录：

```powershell
uv run pytest -q tests
```

### 多语言同步与校验

生成或同步默认中文语言包：

```powershell
uv run python scripts/extract_i18n_messages.py
```

检查 `zh-CN.json` 是否和代码默认文本同步，不写入文件：

```powershell
uv run python scripts/extract_i18n_messages.py --check
```

按 `zh-CN.json` 对齐其它内置语言包的字段结构和顺序：

```powershell
uv run python scripts/extract_i18n_messages.py --align-locales
```

报告疑似未接入多语言结构的裸中文：

```powershell
uv run python scripts/extract_i18n_messages.py --report-bare-chinese --report-limit 200
```

检查非中文语言包质量：

```powershell
uv run python scripts/validate_locale_quality.py --limit 200
```

分析重复或相似文案，辅助精简 key 和调整作用域：

```powershell
uv run python scripts/analyze_i18n_duplicates.py --json
```

## 多语言与翻译贡献

RimCrow 当前内置以下界面语言：

- 简体中文：`zh-CN`
- 繁體中文：`zh-TW`
- English：`en`
- Deutsch：`de`
- 한국어：`ko`
- Русский：`ru`

除简体中文外，当前内置翻译主要由 GPT 辅助生成，并经过脚本同步与基础校验。它们可能仍存在语法不自然、词义不准确、操作语境理解偏差或个别漏译。

语言包分为两类：

```text
frontend/src/locales/          # 内置语言包，随程序发布
data/locales/<language>.json   # 用户覆盖语言包，运行时读取
```

默认中文文案以代码里的 `t(...)` / `tr(...)` 默认文本为准，`zh-CN.json` 由脚本生成，不建议直接手动改内置中文语言包。需要调整中文源文时，优先修改对应代码里的默认文本，再运行生成脚本同步语言包。

用户覆盖语言包按深度合并覆盖内置语言包，只需要写想覆盖的 key。切换语言时程序会重新读取 `data/locales/<language>.json`，适合用户自行修正翻译、补充新语言或临时覆盖个别文案。

创建一个完整的新语言包骨架：

```powershell
uv run python scripts/create_locale.py --lang <language-code> --from en --mode untranslated
```

校验外部翻译工作文件：

```powershell
uv run python scripts/locale_workfile.py <workfile>
```

校验通过后导入外部翻译工作文件：

```powershell
uv run python scripts/locale_workfile.py <workfile> --import
```

导入只会写入 `data/locales/<language>.json`，不会覆盖内置语言包。外部翻译文件适合先导出完整中文或其它参考语言，再交给翻译工具、人工校对或第三方协作处理。

## 打包

### PyInstaller

```powershell
uv run python pack_pyinstaller.py
```

### Nuitka

```powershell
uv run python pack_nuitka.py
```

打包脚本当前偏向作者本机环境，直接跨机器复用前可能还需要调整。

## 项目结构

完整目录树见 [files_tree.txt](./files_tree.txt)。

```text
backend/    Python 后端、业务逻辑、数据与管理器
frontend/   Vue 前端界面
tests/      正式测试
main.py     应用入口
```

## 开发计划

这个项目已经具备较完整的功能骨架，但仍在快速迭代中。

<details>
<summary>1. 核心功能：模组列表与加载管理</summary>

> 涵盖玩家日常使用最频繁的列表操作、排序与基础管理。

- [x] 模组扫描、启用 / 停用列表、分组、标签、自定义颜色、备注和批量编辑
- [x] 列表拖拽、多选、键盘选择、撤销 / 重做、分组折叠、分组定位和分割线模组管理
- [x] 列表排序与筛选，支持名称、创建时间、修改时间、启用时间、来源、类型、坏档状态、未知模组等条件
- [x] 自动排序引擎、依赖贴合、语言包贴合、置顶 / 置底规则和排序差异对比
- [x] 严格禁用模式，确保禁用模组不进入环境，并自动清理相关加载记录
- [x] 本地模组、工坊模组、管理器库模组的共存识别、复制 / 移动、转本地和冲突提示

</details>

<details>
<summary>2. 获取与维护：来源、下载与版本同步</summary>

> 整合了原有的“工坊管理”与“更新/时间线”，统一管理模组的生命周期。

- [x] SteamCMD 下载、任务进度、任务停止、工具环境检查和代理配置
- [x] Steam 客户端订阅、取消订阅、合集解析、缺失项补订阅和 Steam 分享支持
- [x] 工坊搜索、工坊详情、封面 / 截图缓存、同作者推荐、替代项推荐和工坊网页访问
- [x] 工坊离线数据库、社区规则库、替代数据库、更新时间显示和远端签名检查
- [x] GitHub / GitLab / GitGud / zip 直链订阅，支持推荐清单、多源合并、签名刷新、部署记录和本地路径打开
- [x] 工坊 / Git 时间线显示、状态角标、缺失与删除状态识别、更新检查调度
- [x] 包名溯源：基于本地数据进行关联匹配，检索排序文件中纯包名模组的工坊来源，以此提供下载、订阅等补全功能。
- [x] 工坊 ID 搜索、内置工坊主页入口和工坊模组强制重新下载
- [x] 包名溯源支持 Git 推荐清单
- [ ] 订阅或下载前探测目标模组是否仍有效，提前拦截失效工坊项
- [ ] 检查 SteamCMD 的 VDF 记录稳定性，统一管理模组生命周期与更新识别
- [ ] 统一更新管理记录，减少 SteamCMD、Git、软件更新等记录口径差异
- [ ] 记录本地 / 工坊差异版本和本地化同步时间，明确本地版创建与修改来源
- [ ] 完善本地模组更新检测，综合外置数据库、文件修改时间和模组版本

</details>

<details>
<summary>3. 规则引擎：冲突检测与兼容性分析</summary>

> 专注于模组间的逻辑关系、冲突预警及自动化处理。

- [x] 社区规则、动态规则、用户规则、规则编辑器、规则权重校验、`loadTop` / `loadBottom` 支持
- [x] 模组问题检测、规则错误提示、冲突忽略、缺失依赖补全、联锁模组检测与断裂修复
- [x] Multiplayer 兼容度规则与联机兼容性数据库
- [ ] 分析 Mod 定义冲突，识别同一定义被多个模组覆盖、缺失引用和顺序风险
- [ ] 根据定义分析结果辅助生成排序规则或排序建议

</details>

<details>
<summary>4. 环境与数据：沙盒、备份与导入导出</summary>

> 整合了多环境管理、数据安全、导入导出与存档分享，统一归属“数据资产”管理。

- [x] 多环境管理、多游戏版本管理、默认环境创建、Steam 启动和环境快捷方式
- [x] 游戏本体、用户数据、Workshop、Steam、管理器库等路径识别与自动纠偏
- [x] 环境切换后的扫描、日志路径、备份路径、规则路径和运行时链接同步
- [x] 敏感配置使用系统级安全存储，支持凭据迁移
- [x] 数据迁移、项目更名迁移、路径规范化迁移、数据库重置修复和手动强制修复
- [x] 重复包名、共存版本、已删除状态、幽灵模组和残留数据清理
- [x] 加载顺序备份、打开备份目录、另存为、删除、改名、加载和跨环境查看
- [x] `ModsConfig.xml`、`ModList.xml`、RML、RimSort 文本和分享码导入导出
- [x] 备份导入的缺失项检查、版本差异提示、补订阅 / 补下载入口
- [x] 软件数据导入导出，支持设置、提示词、规则和环境数据模块化打包
- [x] 模组实体包导入导出，支持范围选择、冲突预检、磁盘空间检查和任务取消
- [x] 推荐清单导出，支持文本、Markdown、DOCX、PDF、图片、游戏版本、语言包附录和动图
- [ ] 存档管理继续补齐，覆盖导出、修改、整理和清理流程

</details>

<details>
<summary>5. 辅助工作台：外部工具、优化与搜索</summary>

> 剥离独立的实用工具模块（如贴图压缩、文件检索等）。

- [x] 贴图优化、DDS 生成、显存占用估算、缩放策略、清晰度底线和 100% 缩放处理
- [x] ZSTD 输出、失败跳过、重试、历史结果、排除规则、残留 DDS 清理
- [x] 外部工具检查、工具更新
- [x] 文件内容搜索，支持正则、流式结果、多编码读取和系统默认程序打开

</details>

<details>
<summary>6. 智能诊断：AI 助手与日志查错</summary>

> 将排错、日志解析和 AI 功能高度整合，解决“游戏报错怎么办”的核心痛点。

- [x] 游戏日志查看、日志聚类、实时监视、静默模式日志入口和日志路径随环境切换
- [x] AI 日志诊断、多轮对话、流式回复、工具调用、Token 统计和任务中断
- [x] AI 设置、模型测试、模型偏好、协议兼容、错误回退和请求重试
- [x] AI 定义与提示词管理，支持自定义 Prompt、助手、任务绑定和数据导入导出
- [x] AI 批量生成模组别名、结果检阅、重试和回写
- [ ] 修正 AI 相关依赖导入引起的证书请求问题，继续推进按需导入
- [ ] 当本地模组描述不足时，允许 AI 使用工坊描述作为补充输入
- [x] 优化 AI 报错提示，统一日志上下文与用户可读说明
- [ ] AI 搜索推荐、AI 分组、AI 标签分类和操作前确认流程
- [ ] MCP 集成，方便后续接入外部工具和自动化流程

</details>

<details>
<summary>7. 界面、交互与本地化 (UI/UX & i18n)</summary>

> 统一管理所有的视觉展示、快捷操作、辅助功能及文本翻译。

- [x] 设置界面结构、统一表单组件、主题配置、字体缩放和界面尺寸适配
- [x] 窗口位置、尺寸、多屏幕与 DPI 状态持久化，支持重置窗口配置
- [x] 右键菜单、工具栏菜单、快捷键系统、`Ctrl+S` 保存、拖入文件加载和菜单提示
- [x] 弹窗尺寸、缩放溢出、加载状态、删除确认、缺失项弹窗和数据库更新弹窗层级
- [x] 引导中心、全部跳过、启动页、关于页面、更新日志弹窗和静默模式后台体验
- [x] 详情页布局顺序切换、标签输入、分组搜索、悬浮预览、图片预览和工坊浏览空白间隔修复
- [x] 通用翻译服务、工坊内容翻译、译文标题显示和说明缓存翻译
- [x] 多语言 i18n 支持，覆盖主要前端界面、后端提示、设置说明和文档
- [x] 翻译模式、语言包自动对齐、质量校验、重复文案分析和外部翻译工作文件导入导出
- [x] 优化外部工具和网络请求报错提示，统一日志上下文与用户可读说明
- [ ] 补充 `alt`、`aria-label` 等辅助文本，提升键盘与读屏可用性
- [ ] 美化悬浮预览组件、整体配色结构和重点页面视觉层级
- [ ] 优化全局主题配色与组件颜色层级的对应
- [ ] 增加设置项定位搜索、新设置提示和默认值校验
- [ ] 继续检查所有文字缩放、默认 Steam 设置和复杂窗口状态下的界面表现
- [ ] 继续补齐非默认语言翻译质量校对和新增界面的本地化覆盖

</details>

<details>
<summary>8. 底层架构与性能优化 (Backend & API)</summary>

> 软件内部结构优化、内存控制及开放接口拓展。

- [ ] 继续收敛前端数据模型和后端数据结构，减少重复字段、重复转换和状态分叉
- [x] 统一 API 错误契约、错误码映射和结构化日志上下文
- [ ] 统一数据模型后复查共存部署链接冲突风险
- [ ] 改进代码文件结构与功能组织形式，实现插件化结构管理
- [ ] 优化运行期内存占用，重点关注大型列表、图片缓存、外置数据库和日志分析场景
- [ ] 提供对外 MCP 接口或其它接口，让外部 AI 工具可直接调用管理器功能

</details>

<details>
<summary>9. 创作者工具与高级视图 (远期扩展)</summary>

> 针对 Mod 作者及硬核玩家的高阶工具（将原“扩展”和“翻译包生成”整合）。

- [ ] 模组依赖关系星空图，把依赖、前置、冲突和替代关系做成更直观的可视化视图
- [ ] 定义依赖关系星空图，从原版定义到模组新增、覆盖和补丁修改做统一追踪
- [ ] 模组定义编辑器，支持读取和编辑常见 Def 与属性，可直接生成补丁模组
- [ ] 增强定义编辑器，支持生成简单定义模组、补丁模组和基于依赖模组的扩展内容
- [ ] 扩展模组编辑器，支持通过Agent与MCP工具在定义编辑器的基础上实现相对完整的模组开发流程，包括贴图生成、逻辑代码生成、定义文本生成等功能
- [ ] 模组翻译语言包生成，支持解析 XML、生成翻译文件、AI 初译、对比和人工校对
- [ ] 支持发布模组到工坊，实现从创建到发布的全流程管理
- [ ] 将语言包生成 / 编辑器按插件化功能独立管理，并保持和主管理器联动
- [ ] 二分法排错自动化，辅助定位导致坏档或报错的模组组合

</details>

## License

MIT
