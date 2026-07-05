# RimCrow

<img src="./doc/assets/Preview.png" style="width:50%;" />

RimCrow（原名 RimModManager）是一个面向 **RimWorld** 的桌面模组管理器，目标是把模组扫描、排序、备份、工坊管理、日志排错和常用辅助工具放到一个界面里，减少手动翻文件夹和反复切窗口的成本。

![主界面](./doc/assets/主界面.png)

## 主要功能

- 模组扫描与列表管理
- 加载顺序查看、保存、备份与对比
- 规则编辑、依赖关系与问题提示
- Workshop / Git 仓库相关内容管理
- 模组残留扫描与清理
- 贴图优化辅助工具
- 推荐清单导出
- 游戏日志查看与排错辅助
- AI 助手相关能力

## 发布版下载与升级

不参与开发时，建议直接使用发布版：

- 蓝奏云：https://wwbns.lanzouu.com/b00mq4tqgf ，密码：`aite`
- GitHub：https://github.com/Inky-Feather/RimCrow/releases

升级说明：

- 程序支持从蓝奏云和 GitHub 检查更新并下载，内置更新的安装会自动解压覆盖自动重启，手动升级通常直接解压覆盖旧版文件即可。
- 安装更新前会备份配置，涉及数据库结构变动时会自动备份数据库。
- 新版 RimCrow 可直接覆盖旧版 RimModManager ，同样继承数据和凭据，并会在启动后清理冗余的旧版文件。
- 升级前仍建议先关闭游戏和管理器；如果更新失败，可从上方下载渠道重新下载发布包。
- 发布包应保持目录完整，不建议只替换单个 exe 或随意删除配套文件。

## 技术栈

- 后端：Python 3.11
- 前端：Vue 3 + Vite
- 桌面壳：pywebview
- 依赖管理：uv
- 测试：pytest
- 打包：PyInstaller

## 运行环境

当前项目主要按 **Windows 桌面应用** 设计和验证，同时支持 macOS 的核心运行路径。

运行前建议准备：

- Python 3.11+
- Node.js 18+
- `uv`
- Windows 上可用的 **WebView2 Runtime**
- RimWorld 本体与需要管理的模组环境
- 如需使用 Steam 客户端工坊订阅能力，需要准备 Steamworks 运行库，见下方“Steamworks 运行库”

当前 macOS 核心运行范围包括：

- 主程序启动
- RimWorld / Steam / 用户数据 / Player.log 定位
- 基础 Steam 启动路径

当前仍未承诺：

- macOS 上 `todds` 自动安装与使用
- SteamworksPy 的 macOS 编译产物随仓库直接提供
- 打包分发产物质量保证

## 快速开始

### 1. 克隆仓库

```powershell
git clone --recurse-submodules https://github.com/Inky-Feather/RimCrow
cd RimCrow
```

如果克隆时没有带 `--recurse-submodules`，可以在仓库目录补执行：

```powershell
git submodule update --init --recursive
```

### 2. 安装 Python 依赖

```powershell
uv sync
```

### 3. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

### 4. 准备 Steamworks 运行库

Steamworks 相关功能需要两类文件：

- `SteamworksPy`：项目通过 `submodules/SteamworksPy` 固定源码版本，提供 Python 包和可编译的 wrapper 源码。
- Steamworks SDK redistributable：提供 `steam_api64.dll`、`libsteam_api.so`、`libsteam_api.dylib` 等运行库。

如果只使用普通扫描、排序、SteamCMD 下载等功能，可以暂时跳过这一步；需要通过已登录的 Steam 客户端执行订阅、取消订阅、读取工坊状态或后续下载触发能力时，需要完成运行库准备。

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
- `SteamworksPy64.dll` 与 `steam_api64.dll` 最好来自同一 Steamworks SDK 版本的编译/redistributable 组合。

## 启动方式

### 方式一：前端开发模式

先启动前端开发服务器：

```powershell
cd frontend
npm run dev
```

再回到项目根目录启动桌面应用：

```powershell
cd ..
uv run python main.py
```

说明：

- 当前端开发服务器 `http://localhost:5173` 可用时，应用会优先连接它
- 这种方式适合日常开发前端界面和联调

### 方式二：本地构建后启动

先构建前端静态文件：

```powershell
cd frontend
npm run build
cd ..
```

再启动应用：

```powershell
uv run python main.py
```

说明：

- 当前端开发服务器未启动时，应用会尝试读取 `frontend/dist/index.html`
- 这种方式更接近实际发布后的运行形态

### 方式三：浏览器模式

部分情况下如果桌面模式受 WebView2 或本地环境影响，也可以尝试：

```powershell
uv run python main.py --browser
```

## 测试

建议优先运行正式测试目录：

```powershell
uv run pytest -q tests
```

## 打包

### PyInstaller

```powershell
uv run python pack_pyinstaller.py
```

### Nuitka

```powershell
uv run python pack_nuitka.py
```

说明：

- 打包脚本当前偏向作者本机环境，直接跨机器复用前可能还需要调整

## 常见问题排查

- 启动白屏或窗口加载超时：先确认 WebView2 Runtime 已安装；仍异常时可尝试 `uv run python main.py --browser` 使用浏览器模式。
- 窗口跑到屏幕外或尺寸异常：可使用 `uv run python main.py --reset-window-state` 重置窗口状态。
- 前端资源缺失：开发模式需要先运行 `frontend` 的 Vite 服务；本地构建模式需要先执行 `npm run build`。
- SteamCMD 下载失败：检查 SteamCMD 环境、SteamCMD 代理、网络连通性、磁盘空间和目标工坊项状态。
- AI 请求失败：检查协议、Base URL、API Key、模型名、代理、额度和服务商状态；请求参数会在日志中脱敏。
- 游戏或数据路径识别异常：重新选择 RimWorld 本体目录、用户数据目录和 Workshop 目录后重新扫描。
- 更新失败：换用另一个发布渠道下载新版，或尝试手动下载。

## 隐私与安全

- RimCrow 主要处理本机 RimWorld、模组、配置、日志和管理器数据库。
- AI API Key、Steam Web API Key、代理用户名和密码属于受保护字段，优先保存到系统凭据库。
- 如果系统凭据库不可用，程序会回退到明文暂存并给出提示；不建议在共享电脑上保存敏感凭据。
- 写入配置文件时会清空受保护字段，接口调用日志和 AI 请求参数会做脱敏处理。
- 使用 AI、Steam、GitHub、蓝奏云、社区规则或外置数据库功能时，请求会发送到对应第三方服务；不需要联网的本地列表管理、排序、备份等功能仍可本地使用。
- 分享日志、配置或导出包前，建议自行检查是否包含本地路径、模组清单、游戏日志或其它个人信息。


## 项目结构

完整目录树见 [files_tree.txt](./files_tree.txt)

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
- [x] GitHub / GitLab / GitGud / zip 直链订阅，支持推荐清单、多源合并、签名刷新和本地路径打开
- [x] 工坊 / Git 时间线显示、状态角标、缺失与删除状态识别、更新检查调度
- [x] 包名溯源：基于本地数据进行关联匹配，检索排序文件中纯包名模组的工坊来源，以此提供下载、订阅等补全功能。
- [ ] 包名溯源支持 Git 推荐清单
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
- [ ] 优化 AI 报错提示，统一日志上下文与用户可读说明
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
- [ ] 多语言 i18n 支持，逐步覆盖前端界面、后端提示、设置说明和文档
- [ ] 优化外部工具和网络请求报错提示，统一日志上下文与用户可读说明
- [ ] 补充 `alt`、`aria-label` 等辅助文本，提升键盘与读屏可用性
- [ ] 美化悬浮预览组件、整体配色结构和重点页面视觉层级
- [ ] 优化全局主题配色与组件颜色层级的对应
- [ ] 增加设置项定位搜索、新设置提示和默认值校验
- [ ] 继续检查所有文字缩放、默认 Steam 设置和复杂窗口状态下的界面表现

</details>

<details>
<summary>8. 底层架构与性能优化 (Backend & API)</summary>

> 软件内部结构优化、内存控制及开放接口拓展。

- [ ] 继续收敛前端数据模型和后端数据结构，减少重复字段、重复转换和状态分叉
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
