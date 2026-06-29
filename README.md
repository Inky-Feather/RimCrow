# RimModManager

RimModManager 是一个面向 **RimWorld** 的桌面模组管理器，目标是把模组扫描、排序、备份、工坊管理、日志排错和常用辅助工具放到一个界面里，减少手动翻文件夹和反复切窗口的成本。

当前仓库处于持续开发中，正在持续迭代和逐步整理成公开项目。

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

## 技术栈

- 后端：Python 3.11
- 前端：Vue 3 + Vite
- 桌面壳：pywebview
- 依赖管理：uv
- 测试：pytest
- 打包：PyInstaller

## 运行环境

当前项目主要按 **Windows 桌面应用** 设计和验证。

运行前建议准备：

- Python 3.11+
- Node.js 18+
- `uv`
- Windows 上可用的 **WebView2 Runtime**
- RimWorld 本体与需要管理的模组环境
- 如需使用 Steam 客户端工坊订阅能力，需要准备 Steamworks 运行库，见下方“Steamworks 运行库”

## 快速开始

### 1. 克隆仓库

```powershell
git clone --recurse-submodules <your-repo-url>
cd RimModManager
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

说明：

- 仓库里还有一些本地实验性质内容，不建议直接用无参数 `pytest` 把所有目录一起扫
- 如果后续准备公开协作，建议先把默认测试入口整理到稳定可直接通过的状态

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

## 项目结构

```text
backend/    Python 后端、业务逻辑、数据与管理器
frontend/   Vue 前端界面
tests/      正式测试
main.py     应用入口
```

## 当前状态

这个项目已经具备较完整的功能骨架，但仍在快速迭代中。对外公开前，建议优先补齐以下内容：

- 更完整的 README 截图和功能说明
- 稳定的默认测试入口
- 更清晰的版本号与更新说明同步策略
- 更细致的 GitHub 发布流程与 issue / PR 模板

## 开发计划

下面这些内容仍在规划或开发中，优先级和具体实现方式后续可能会调整。

### 近期改进

- 多语言支持，逐步补齐界面文本、提示信息和功能说明
- 优化错误提示，尤其是外部工具、网络请求和 AI 相关报错
- 改进窗口缩放适配，检查各类弹窗、面板和文字缩放后的溢出问题
- 补齐按钮和异步操作的进行中状态，减少重复点击和状态不清的问题
- 强化路径识别和环境识别，包括 Steam、Workshop、用户数据目录和自动启用逻辑
- 提升密码等敏感配置的本地存储安全性
- 修复规则生成后无法即时应用、重置数据库误删默认环境等体验问题
- 完善本地模组更新检测、版本差异记录和同步时间记录
- 改进共存模组、重复模组、停用列表、标签输入、右键菜单和分组跳转等交互细节
- 优化推荐导出能力，包括游戏版本、语言包过滤、附录信息和动图支持

### 结构演进

- 统一前后端数据模型，减少重复字段和重复转换逻辑，提升复用性
- 调整代码与目录结构，让功能边界更清晰，降低后续维护成本
- 逐步把功能组织方式从“按文件堆叠”整理为更稳定的模块化 / 插件化结构
- 优化运行期内存占用，减少大型列表、缓存和图像相关功能带来的压力
- 补丁解析、社区数据展示、名称与翻译联动等能力会结合数据模型重整一起推进
- 规划设置搜索、新设置提示、默认值校验等通用基础能力
- 探索 MCP 集成，方便后续和外部工具或自动化能力对接

### AI 与翻译增强

- AI 辅助补全搜索推荐、分组、标签等整理能力
- 模组介绍翻译扩展到模组详情和工坊搜索等主要使用区域
- 当模组本地描述不足时，支持回退使用工坊描述作为 AI 输入
- 模组翻译语言包生成，支持一键生成语言包结构、AI 初译和人工校对协作
- 语言包分析 / 生成编辑器会考虑独立管理，同时保持和主管理器联动

### 功能扩展

- 存档管理能力继续补齐，包括导出、修改、整理和清理
- 模组依赖关系可视化，把依赖、前置、冲突等关系做成更直观的星空图
- 定义依赖关系可视化，从原版定义到模组新增、覆盖、补丁修改做统一追踪
- 定义问题分析，检查同一定义的修改顺序、缺失依赖、无效引用等问题，并辅助生成规则或优化自动排序
- 模组定义编辑器，支持浏览和编辑模组内部常见定义与属性
- 增强定义编辑器，支持生成简单定义模组、补丁模组，以及基于依赖模组扩展内容
- 增加 Multiplayer 兼容度规则支持

### 说明

- 上面的计划里有些内容互相关联，例如定义可视化、定义问题分析、排序规则优化、编辑器能力，本质上属于同一条更大的功能线
- 也有一些条目更适合在重构后统一做，而不是先零散补丁式堆功能
- 因此实际推进时会优先做对稳定性、可维护性和用户体验提升最大的部分

## License

MIT
