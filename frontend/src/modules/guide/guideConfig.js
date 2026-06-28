// frontend/src/modules/guide/guideConfig.js

import { useAppStore } from "../../stores/appStore";
import { useModStore } from "../../stores/modStore";

export const GUIDE_VERSION = "v2.0"; // 修改版本号可以强制老用户重新看一遍新版引导

const GUIDE_DELAY = 400;

const wait = (ms = GUIDE_DELAY) => new Promise((resolve) => setTimeout(resolve, ms));

const clickTourTarget = async (selector) => {
  const target = document.querySelector(selector);
  if (!target) return false;
  target.click();
  await wait();
  return true;
};

export const mainGuideSteps = [
  {
    element: '[data-tour="inactive-list"]',
    popover: {
      title: "未启用列表",
      description: "这里是你拥有的所有未启用模组。可以拖拽它们到右侧，或者双击启用。",
      side: "right",
    },
  },
  {
    element: '[data-tour="active-list"]',
    popover: {
      title: "已启用列表",
      description:
        "这里是游戏的实际加载顺序。支持自由拖拽排序，也可以交给自动排序处理。红色和黄色提示代表前置、顺序或兼容性问题，需要优先处理。",
      side: "left",
    },
    onNextBefore: async () => {
      const modStore = useModStore();
      const tempId = modStore.inactiveIds[0] || modStore.activeIds[0];
      if (tempId) modStore.selectMods([tempId], tempId);
    },
  },
  {
    element: '[data-tour="details-column"]',
    popover: {
      title: "模组详情",
      description: "这里会显示当前选中模组的说明、依赖、作者、路径与自定义信息。",
      side: "left",
    },
  },
  {
    element: '[data-tour="sidebar-column"]',
    popover: {
      title: "辅助栏",
      description: "这里承载临时列表、分组、备份，以及单个模组的规则编辑入口。",
      side: "top",
    },
  },
  {
    element: '[data-tour="base-button-group"]',
    popover: {
      title: "主操作区",
      description: "刷新、自动排序、保存和启动游戏都在这里。处理完问题后，记得保存再启动。",
      side: "top",
    },
  },
  {
    element: '[data-tour="profile-switcher"]',
    popover: {
      title: "环境隔离",
      description:
        "你可以为不同玩法维护独立环境，例如纯净档、整合包档和测试档。每个环境的配置与排序相互隔离。",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="workspace-btn"]',
    popover: {
      title: "库存枢纽",
      description:
        "这里集中管理创意工坊、本地模组和管理器下载模组，也包含工坊检索、合集管理和 GitHub 订阅。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="rulePanel-btn"]',
    popover: {
      title: "规则中心",
      description: "这里管理排序规则、社区规则、动态规则和它们的生效优先级。",
      side: "bottom",
    },
  },
];

export const workflowGuideSteps = [
  {
    element: '[data-tour="refresh-button"]',
    popover: {
      title: "第一步：刷新",
      description: "先刷新模组清单。普通刷新走增量扫描；悬停后还能触发更彻底的强制刷新。",
      side: "top",
    },
  },
  {
    element: '[data-tour="autosort-button"]',
    popover: {
      title: "第二步：自动排序",
      description: "让程序根据规则和依赖关系重新整理启用列表。排序后先看警告，再决定是否继续。",
      side: "top",
    },
  },
  {
    element: '[data-tour="save-button"]',
    popover: {
      title: "第三步：保存",
      description: "自动排序或手动拖拽都只是内存里的变更，必须点保存才会真正写入加载顺序文件。",
      side: "top",
    },
  },
  {
    element: '[data-tour="launch-button"]',
    popover: {
      title: "第四步：启动游戏",
      description: "确认没有关键问题后再启动游戏，这样最不容易把坏序列带进存档。",
      side: "top",
    },
  },
];

export const modListGuideSteps = [
  {
    element: '[data-tour="list-header"]',
    popover: {
      title: "列表状态栏",
      description: "这里会显示列表名称、数量，以及当前筛选、排序和问题统计状态。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="list-toolbar"]',
    popover: {
      title: "搜索与筛选",
      description:
        "上半区偏定位，下半区偏筛选。支持模糊搜索、字段搜索、排除搜索，以及多条件与/或逻辑。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="list-modItem"]',
    popover: {
      title: "列表项交互",
      description:
        "支持拖拽、双击启停、Ctrl 多选、Shift 连选、Ctrl+A 全选，以及右键菜单的批量操作。Alt+左键可以直接打开规则编辑。",
      side: "left",
    },
  },
  {
    element: '[data-tour="list-modItem"] .swipe-trigger:first-child',
    popover: {
      title: "序号列",
      description: "序号列除了显示位置，还能用来划动扩选和快速定位搜索结果。",
      side: "left",
    },
  },
];

export const searchGuideSteps = [
  {
    element: '[data-tour="list-toolbar"]',
    popover: {
      title: "直接搜索",
      description: "直接输入关键词即可在默认字段里做模糊匹配，适合先快速缩小结果范围。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="list-toolbar"]',
    popover: {
      title: "类别搜索",
      description: "进阶时可以使用“类别:关键词”的格式做定向搜索，这比只输自然语言更适合排查大列表。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="list-toolbar"]',
    popover: {
      title: "排除、判断与组合",
      description: "支持 “-类别:关键词” 的排除写法；布尔字段还能用 + / - / _ 做是/否/空值判断，并配合与/或逻辑组合多个条件。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="list-header"]',
    popover: {
      title: "验证筛选结果",
      description: "筛完后看这里的数量和状态是否符合预期；结果不对时，回到工具栏继续收窄或放宽条件。",
      side: "bottom",
    },
  },
];

export const issueGuideSteps = [
  {
    element: '[data-tour="list-status-summary"]',
    popover: {
      title: "问题汇总区",
      description:
        "这里会集中显示当前启用列表的错误和警告数量。出现异常时先看这里，再决定是否筛选问题项。",
      side: "left",
    },
  },
  {
    element: '[data-tour="list-quick-actions"]',
    popover: {
      title: "一键处理区",
      description:
        "这里会根据当前状态出现一键订阅缺失项、一键下载、一键补依赖、补语言包或移除无效项等快捷处理按钮。",
      side: "left",
    },
  },
  {
    element: '[data-tour="list-modItem"]',
    popover: {
      title: "逐项排查",
      description: "如果一键处理不够，就在列表项上右键，结合规则编辑、忽略警告和定位功能逐项收敛问题。",
      side: "left",
    },
  },
];

export const profileGuideSteps = [
  {
    element: '[data-tour="profile-switcher"]',
    popover: {
      title: "环境入口",
      description: "从这里切换不同环境。每个环境有独立的排序、存档和配置上下文。",
      side: "bottom",
    },
    onNextBefore: async () => {
      const appStore = useAppStore();
      appStore.uiState.showProfileDrawer = true;
    },
  },
  {
    element: '[data-tour="profile-list"]',
    popover: {
      title: "环境列表",
      description: "这里可以查看环境路径、版本和启用来源，也可以编辑、删除或直接运行指定环境。",
      side: "right",
    },
  },
  {
    element: '[data-tour="profile-create"]',
    popover: {
      title: "创建环境",
      description:
        "新环境可以继承当前配置，也可以自定义用户数据目录。删除环境会清理其隔离区数据，这一步需要谨慎。",
      side: "right",
    },
  },
];

export const groupGuideSteps = [
  {
    element: '[data-tour="sidebar-tab"]',
    popover: {
      title: "辅助栏入口",
      description: "这里可以在临时列表、分组和备份之间切换。本教程聚焦分组，用于长期整理你的模组集合。",
      side: "left",
    },
  },
  {
    element: '[data-tour="group-list-header"]',
    popover: {
      title: "分组概览",
      description: "标题栏会显示当前分组数量。分组更像“收藏夹/剪贴板”，适合整理主题包、测试集和常用组合。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="group-list-search"]',
    popover: {
      title: "搜索定位",
      description: "输入关键词后可循环定位匹配分组。分组很多时，先搜再改，比手动滚动更快。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="group-list-actions"]',
    popover: {
      title: "展开、折叠与新建",
      description: "这里集中放了展开全部、折叠全部和新建分组。首次搭结构时，先建分组名，再慢慢往里归档最省事。",
      side: "left",
    },
  },
  {
    element: '[data-tour="group-list-help"]',
    popover: {
      title: "分组规则说明",
      description: "帮助按钮会说明分组拖拽规则：移入分组通常是复制思路，不会直接替代原列表里的模组状态。",
      side: "left",
    },
  },
  {
    element: '[data-tour="group-list-body"]',
    popover: {
      title: "分组主体",
      description: "分组本体支持拖拽排序，也能把整个分组拖到启用/停用列表里做批量启停，非常适合做整包切换。",
      side: "left",
    },
  },
];

export const backupGuideSteps = [
  {
    element: '[data-tour="sidebar-tab"]',
    popover: {
      title: "切到备份页",
      description: "备份页承载排序文件的导入、导出、查看差异、恢复和清理操作。",
      side: "left",
    },
    onNextBefore: async () => {
      const appStore = useAppStore();
      appStore.setSidebarTab("backup");
    },
  },
  {
    element: '[data-tour="backup-list"]',
    popover: {
      title: "备份列表",
      description: "这里同时包含临时导入、自动备份和手动备份。恢复前建议先对比，避免覆盖当前未保存变更。另外列表支持从外界直接拖入排序文件进行加载。",
      side: "left",
    },
  },
  {
    element: '[data-tour="backup-toolbar"]',
    popover: {
      title: "备份操作区",
      description: "你可以在这里导入/导出外部排序文件、打开备份目录和刷新列表。可以切换不同环境的备份进行操作。",
      side: "left",
    },
  },
];



export const workspaceGuideSteps = [
  {
    element: '[data-tour="workspace-workshop-list"]',
    popover: {
      title: "创意工坊库存",
      description: "这里列出 Steam 工坊库存，你可以查看模组时间线和执行启用、禁用、删除等库存管理操作。",
      side: "left",
    },
  },
  {
    element: '[data-tour="workspace-workshop-toolbar"]',
    popover: {
      title: "库存工具栏",
      description: "支持搜索、筛选、排序、缺失检测和更新检测，是日常盘点库存的主工作区。例如，可通过筛选出所有禁用的模组，多选后批量启用。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="workspace-self-list"]',
    popover: {
      title: "管理器库存",
      description: "这里是管理器自行下载的模组库。使用它们前，要确认环境里启用了管理器模组开关。",
      side: "left",
    },
  },
  {
    element: '[data-tour="workspace-tabs"]',
    popover: {
      title: "其它工作区页面",
      description: "顶部标签还能切到创意工坊检索、合集订阅和 GitHub 订阅页面。",
      side: "left",
    },
  },
];

export const workshopBrowserGuideSteps = [
  {
    element: '[data-tour="workspace-tabs"]',
    popover: {
      title: "切到工坊检索",
      description: "工作区顶部标签可以在库存矩阵和工坊检索间切换。",
      side: "bottom",
    },
    onNextBefore: async () => {
      await clickTourTarget('[data-tour="workspace-tab-workshop"]');
    },
  },
  {
    element: '[data-tour="workspace-workshop-search"]',
    popover: {
      title: "工坊搜索",
      description: "支持按模组名、包名或工坊 ID 搜索。适合先查存在性，再决定订阅还是下载到管理器。",
      side: "right",
    },
  },
  {
    element: '[data-tour="workspace-workshop-results"]',
    popover: {
      title: "结果列表",
      description: "左侧会显示缓存结果。点任意项后，右侧会载入该模组的详细信息。",
      side: "right",
    },
  },
  {
    element: '[data-tour="workspace-workshop-detail"]',
    popover: {
      title: "详情区",
      description:
        "这里会展示简介、依赖、截图和作者信息。你可以直接订阅、取消订阅、下载到管理器，或继续钻取依赖项。",
      side: "left",
    },
  },
];

export const collectionGuideSteps = [
  {
    element: '[data-tour="workspace-tabs"]',
    popover: {
      title: "切到合集页",
      description: "合集页适合导入别人分享的整合包链接，再快速补齐缺失模组。",
      side: "bottom",
    },
    onNextBefore: async () => {
      await clickTourTarget('[data-tour="workspace-tab-collection"]');
    },
  },
  {
    element: '[data-tour="workspace-collection-input"]',
    popover: {
      title: "导入合集",
      description: "粘贴 Steam 合集 URL 或直接输入合集 ID，即可把合集记录纳入本地管理。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="workspace-collection-list"]',
    popover: {
      title: "合集卡片",
      description: "选择右侧合集后，左侧会显示该合集包含的模组和缺失状态。",
      side: "left",
    },
  },
  {
    element: '[data-tour="workspace-collection-browser"]',
    popover: {
      title: "合集工作流",
      description:
        "典型流程是：导入合集 -> 选择一条记录 -> 订阅或补齐缺失项 -> 最后决定是否把合集顺序覆盖到当前启用列表。",
      side: "left",
    },
  },
];

export const githubGuideSteps = [
  {
    element: '[data-tour="workspace-tabs"]',
    popover: {
      title: "切到 GitHub 页",
      description: "这里适合订阅那些没有工坊页面、但作者持续在 GitHub 发布源码或 Release 的模组。",
      side: "bottom",
    },
    onNextBefore: async () => {
      await clickTourTarget('[data-tour="workspace-tab-github"]');
    },
  },
  {
    element: '[data-tour="workspace-github-input"]',
    popover: {
      title: "解析仓库链接",
      description: "先粘贴 GitHub 仓库地址。系统会解析仓库信息，然后让你选择 Source 或 Release 模式。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="workspace-github-list"]',
    popover: {
      title: "已订阅仓库",
      description: "左侧列表会显示已订阅的仓库、当前安装模式和版本状态。",
      side: "right",
    },
  },
  {
    element: '[data-tour="workspace-github-workspace"]',
    popover: {
      title: "部署与追踪",
      description: "右侧区域负责展示解析结果、部署入口以及本地执行日志时间线。",
      side: "left",
    },
  },
];

export const ruleCenterGuideSteps = [
  {
    element: '[data-tour="rule-tabs"]',
    popover: {
      title: "规则分类",
      description: "左侧区分动态规则、用户规则、社区规则和工坊依赖规则。不同来源会共同参与排序判定。",
      side: "right",
    },
  },
  {
    element: '[data-tour="rule-priority"]',
    popover: {
      title: "生效优先级",
      description: "来源优先级从上到下依次降低。这里会影响自动排序和问题检测出现冲突时该信谁。",
      side: "right",
    },
  },
  {
    element: '[data-tour="rule-import-export"]',
    popover: {
      title: "导入导出规则包",
      description: "如果你维护了自己的规则集，或者要在不同机器间迁移配置，这里是统一入口。",
      side: "right",
    },
  },
  {
    element: '[data-tour="rule-create"]',
    popover: {
      title: "动态规则",
      description: "动态规则适合写成“满足这些条件 -> 应用某种排序动作”的自动化规则。",
      side: "left",
    },
  },
  {
    element: '[data-tour="rule-search"]',
    popover: {
      title: "搜索规则",
      description: "可以按规则名、模组名或包名快速定位要检查的规则条目。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="rule-actions"]',
    popover: {
      title: "当前分类开关",
      description: "这里控制当前规则来源是否整体启用，以及少量分类专属选项。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="rule-list"]',
    popover: {
      title: "规则条目列表",
      description: "在这里逐条查看、启停、编辑或删除规则。排查异常排序时，优先从这里核对来源说明。",
      side: "left",
    },
  },
];

export const conflictGuideSteps = [
  {
    element: '[data-tour="conflict-summary"]',
    popover: {
      title: "冲突总览",
      description: "先看这里确认是硬冲突还是共存，再决定清理范围。删除前一定先分清来源。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="conflict-list"]',
    popover: {
      title: "副本选择区",
      description: "先选一个要保留的副本，再给其余副本指定禁用或删除动作。",
      side: "right",
    },
  },
  {
    element: '[data-tour="conflict-batch"]',
    popover: {
      title: "批量规则",
      description: "如果冲突很多，可以先设定“保留谁、其余怎么处理”，再一键应用到当前范围。",
      side: "left",
    },
  },
  {
    element: '[data-tour="conflict-submit"]',
    popover: {
      title: "执行处理",
      description: "提交后会自动刷新并重新扫描。含删除动作时要格外确认，因为这一步会直接改动文件状态。",
      side: "top",
    },
  },
];

export const aiConfigGuideSteps = [
  {
    element: '[data-tour="settings-tab-ai"]',
    popover: {
      title: "AI 集成页",
      description: "设置面板里单独给 AI 留了入口。后续所有模型、接口和提示词相关配置都从这里管理。",
      side: "right",
    },
    onNextBefore: async () => {
      await clickTourTarget('[data-tour="settings-tab-ai"]');
    },
  },
  {
    element: '[data-tour="settings-ai-enable"]',
    popover: {
      title: "启用 AI 功能",
      description: "先打开这个总开关，日志分析、批量别名/备注生成等功能才会显示完整配置。",
      side: "right",
    },
    onNextBefore: async () => {
      const appStore = useAppStore();
      if (!appStore.settings.ai?.enabled) {
        await clickTourTarget('[data-tour="settings-ai-enable"] button');
      }
    },
  },
  {
    element: '[data-tour="settings-ai-connection"]',
    popover: {
      title: "接口与凭证",
      description: "先选协议和模型，再按服务类型填写 Base URL 与 API Key。本地服务通常更关注地址，云服务通常更关注密钥。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="settings-ai-advanced"]',
    popover: {
      title: "高级参数",
      description: "最大 Token、并发数和随机性会直接影响成本、速度和输出稳定性。初次使用建议先保守，再逐步放开。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="settings-ai-test"]',
    popover: {
      title: "连通性测试",
      description: "正式使用前先做一次测试。能拿到返回结果，通常就说明模型名、接口地址和认证配置基本通了。",
      side: "top",
    },
  },
  {
    element: '[data-tour="settings-save-button"]',
    popover: {
      title: "保存配置",
      description: "测试通过后别忘了保存，否则这次修改不会写回正式设置。",
      side: "top",
    },
  },
];

export const textureOptGuideSteps = [
  {
    element: '[data-tour="texture-opt-entry"]',
    popover: {
      title: "贴图优化入口",
      description: "这里进入贴图优化中心。它的作用是把真实 PNG 源图预处理成 DDS，以换取更低显存占用和更快的贴图载入。",
      side: "bottom",
    },
    onNextBefore: async () => {
      if (!document.querySelector('[data-tour="texture-opt-modal"]')) {
        await clickTourTarget('[data-tour="texture-opt-entry"]');
      }
    },
  },
  {
    element: '[data-tour="texture-opt-summary"]',
    popover: {
      title: "总览统计",
      description: "这里会把当前范围内的源图数量、现有 DDS、待生成、无效 PNG、小图跳过和显存预估集中展示。先看这里，再决定是否需要生成或清理。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="texture-opt-list-toolbar"]',
    popover: {
      title: "列表筛选与排序",
      description: "左侧主体按模组展示贴图储存占比。你可以切换 PNG / DDS 视图，搜索模组名称或路径，并按占比、待生成数量或显存节省排序。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="texture-opt-list"]',
    popover: {
      title: "模组明细列表",
      description: "这里按模组汇总贴图情况。通常优先看待生成多、体积大、显存节省高的模组；遇到无效 PNG 或无源 DDS 也会在这里暴露出来。",
      side: "left",
    },
  },
  {
    element: '[data-tour="texture-opt-options"]',
    popover: {
      title: "优化选项",
      description: "这里可以调整优化参数，影响生成的 DDS 体积和显存占用。通常而言，缩放倍率越小，越省显存，但贴图也越容易变糊。",
      side: "left",
    },
  },
  {
    element: '[data-tour="texture-opt-actions"]',
    popover: {
      title: "主要操作",
      description: "这里有生成、扫描、清理等主要操作按钮。设置好优化参数后，直接生成即可，扫描可以分析现有贴图数量体积占用等信息。",
      side: "left",
    },
  },
];

export const aiReviewGuideSteps = [
  {
    element: '[data-tour="ai-review-entry"]',
    popover: {
      title: "结果入口",
      description: "批量 AI 任务完成后，这里会出现数字提示。即使你稍后关闭了检阅窗，也能从这里再次打开。",
      side: "bottom",
    },
    onNextBefore: async () => {
      const appStore = useAppStore();
      appStore.uiState.showModAliasReviewModal = true;
      await wait();
    },
  },
  {
    element: '[data-tour="ai-review-summary"]',
    popover: {
      title: "任务总览",
      description: "先看总任务数、成功数和失败数。失败或置空项目通常需要你手工补写，或者单独重试。",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="ai-review-list"]',
    popover: {
      title: "逐项检查区",
      description: "这里会把批量结果一条条展开。高亮告警项优先处理，能大幅降低把错误备注批量写回的风险。",
      side: "left",
    },
  },
  {
    element: '[data-tour="ai-review-card"]',
    popover: {
      title: "单项修订",
      description: "每张卡片都能直接改别名和备注；把鼠标移到右上角，还能单独重试生成或丢弃这条结果。",
      side: "left",
    },
  },
  {
    element: '[data-tour="ai-review-save"]',
    popover: {
      title: "确认写回",
      description: "确认没问题后再统一保存。这个动作会把当前检阅结果批量写回模组自定义资料。",
      side: "top",
    },
  },
];

export const logAnalysisGuideSteps = [
  {
    element: '[data-tour="log-viewer-entry"]',
    popover: {
      title: "日志中心入口",
      description: "日志分析教程会围绕这里展开。开始前请先确认你已经在“设置 -> AI 集成”里完成 AI 配置。",
      side: "bottom",
    },
    onNextBefore: async () => {
      const appStore = useAppStore();
      appStore.uiState.showLogDrawer = true;
      await wait();
    },
  },
  {
    element: '[data-tour="log-viewer-tabs"]',
    popover: {
      title: "日志来源切换",
      description: "这里可以在系统日志和游戏日志之间切换。AI 分析优先用于游戏日志；系统日志通常需要开启调试模式才会出现 AI 控件。",
      side: "bottom",
    },
    onNextBefore: async () => {
      await clickTourTarget('[data-tour="log-tab-game"]');
    },
  },
  {
    element: '[data-tour="log-viewer-stream"]',
    popover: {
      title: "先定位异常日志",
      description: "先在正文区找到最相关的报错文件或报错区间。你可以手动勾选关键日志，再交给右侧 AI 做针对性分析。",
      side: "right",
    },
  },
  {
    element: '[data-tour="log-viewer-auto-analyze"]',
    popover: {
      title: "一键分析全局错误",
      description: "如果错误很多、分布很散，优先用一键分析。它会先压缩全局异常，再自动发起更适合大日志的 AI 诊断。",
      side: "left",
    },
  },
  {
    element: '[data-tour="log-viewer-ai-toggle"]',
    popover: {
      title: "手动打开 AI 助手",
      description: "如果你已经选中了部分日志，或者只想围绕某个报错对话，就从这里打开 AI 助手侧栏。",
      side: "left",
    },
    onNextBefore: async () => {
      if (!document.querySelector('[data-tour="log-ai-sidebar"]')) {
        await clickTourTarget('[data-tour="log-viewer-ai-toggle"]');
      }
    },
  },
  {
    element: '[data-tour="log-ai-sidebar"]',
    popover: {
      title: "AI 分析侧栏",
      description: "这里会承接日志附件、对话历史和 AI 结论。长链路排错时，建议在同一会话里连续追问。",
      side: "left",
    },
  },
  {
    element: '[data-tour="log-ai-tool-selector"]',
    popover: {
      title: "工具权限",
      description: "这里决定 AI 是否允许主动读取日志上下文、模组资料、排序规则等后台信息。复杂问题建议保持默认开启。",
      side: "left",
    },
  },
  {
    element: '[data-tour="log-ai-input"]',
    popover: {
      title: "补充你的问题",
      description: "除了直接发日志，你还可以追加要求，例如“按优先级给修复步骤”或“先判断最可疑的 Mod”。",
      side: "left",
    },
  },
  {
    element: '[data-tour="log-ai-send"]',
    popover: {
      title: "发送分析请求",
      description: "确认已经挂上日志附件，或已经输入明确问题后，再点击发送。发送按钮置灰通常表示还没选日志，或 Token 预检尚未完成。",
      side: "left",
    },
  },
];
