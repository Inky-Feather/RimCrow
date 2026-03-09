// frontend/src/modules/guide/guideConfig.js

import { useAppStore } from "../../stores/appStore";
import { useModStore } from "../../stores/modStore";

export const GUIDE_VERSION = "v1.0"; // 修改版本号可以强制老用户重新看一遍新版引导

export const mainGuideSteps = [
  {
    element: '[data-tour="inactive-list"]',
    popover: {
      title: '未启用列表',
      description: '这里是你拥有的所有未启用模组。可以拖拽它们到右侧，或者双击启用。',
      side: "right"
    }
  },
  {
    element: '[data-tour="active-list"]',
    popover: {
      title: '已启用列表',
      description: '游戏的实际加载顺序。支持自由拖拽排序。你也可以点击“自动排序”按钮，让程序自动帮你解决排序问题。\n如果出现红色或黄色提示，说明存在前置缺失或冲突，可能影响游戏运行！另外，语言相关的提示基本不影响游戏运行，不需要可以在设置中关闭语言提示。',
      side: "left"
    },
    // 【关键】：进入这一步时触发的动作
    onNextBefore: async () => {
      const modStore = useModStore()
      const tempId = modStore.inactiveIds[0] || modStore.activeIds[0]
      console.log('详情引导')
      if (tempId) modStore.selectMods([tempId],tempId)
    }
  },
  {
    element: '[data-tour="details-column"]',
    popover: {
      title: '模组详情',
      description: '显示当前选中模组的详细信息，包括名称、版本、作者、描述、依赖等。\n你可以在这里自定义模组的信息，或者分组添加标记等操作。',
      side: "left"
    }
  },
  {
    element: '[data-tour="sidebar-column"]',
    popover: {
      title: '辅助/分组',
      description: '这里是辅助功能区，包含临时列表、分组管理、备份（加载序列）管理、模组的规则编辑也会在这里显示。\n临时列表是你在排序过程中用来临时存放的列表，你可以把它当作剪切板。',
      side: "top"
    }
  },
  {
    element: '[data-tour="base-button-group"]',
    popover: {
      title: '基础操作按钮组',
      description: '包含“刷新”、“自动排序”、“保存排序”、“启动游戏”四大基础基础操作按钮。如果一切准备就绪，你就可以开始游戏了。',
      side: "top"
    }
  },
  {
    element: '[data-tour="profile-switcher"]',
    popover: {
      title: '环境隔离',
      description: '在这里你可以切换多个独立的“环境”，比如“纯净版”、“中世纪”、“赛博朋克”，每个环境的模组和存档完全互不干扰。\n通过环境管理选项，你可以轻松创建、切换、删除环境。',
      side: "bottom",
      align: 'start'
    }
  },
  {
    element: '[data-tour="workspace-btn"]',
    popover: {
      title: '库存枢纽',
      description: '所有的创意工坊、本地模组、管理器下载模组在这里统一管理，支持检测模组缺失、更新检测、禁用管理，以及创意工坊模组的搜索订阅下载等操作。',
      side: "bottom"
    }
  },
  {
    element: '[data-tour="rulePanel-btn"]',
    popover: {
      title: '规则中心',
      description: '在这里你可以编辑和管理所有模组的排序及提示规则。\n包括动态规则、社区规则、工坊规则、自定义规则等，这些规则影响着自动排序以及列表中的错误提示，可以按需要启用或者调整优先级。',
      side: "bottom"
    }
  },
];

export const modListGuideSteps = [
  {
    element: '[data-tour="list-header"]',
    popover: {
      title: '列表状态栏',
      description: '这里显示了列表名称以及当前列表中的模组数量，以及筛选、排序时的状态提示，还有问题提示汇总。',
      side: "bottom"
    }
  },
  {
    element: '[data-tour="list-toolbar"]',
    popover: {
      title: '列表搜索功能区',
      description: '在这里输入关键词，即可 搜索定位 或 快速筛选 出包含该关键词的模组。\n支持模糊搜索，也可以使用“-”前缀来表示不包含某个关键词。\n还有排序显示功能，你可以根据模组名称、版本、作者等进行排序方便查找。',
      side: "bottom"
    }
  },
  {
    element: '[data-tour="list-dependency"]',
    popover: {
      title: '模组依赖可视区',
      description: '显示当前选中模组的依赖关系。\n你可以停留在依赖线上来查看其详细信息，或者点击依赖线条在列表中筛选出所有依赖于该模组的其他模组，再次点击即可取消筛选。',
      side: "right"
    }
  },
  {
    element: '[data-tour="list-modItem"]',
    popover: {
      title: '模组列表项',
      description: '每个模组列表项可直接拖拽到其它列表，支持`Ctrl+左键`多选、`Shift+左键`范围选择、`Ctrl+A`全选，以及`序号列划动`扩选 进行多选操作。\n点击列表项即可在左侧详情区域查看模组详情，右键菜单支持更多操作。\n还支持`Alt+左键`支持快速打开规则编辑栏。',
      side: "left"
    }
  },
  {
    element: '[data-tour="list-modItem"] .swipe-trigger:first-child',
    popover: {
      title: '序号列',
      description: '序号列显示当前模组所在的位置，在序号列划动鼠标即可扩选多行，也可以直接点击选中单行。另外序号列还提供搜索结果的高亮标记，方便你快速定位到搜索结果。',
      side: "left"
    }
  },
];

export const profileGuideSteps = [
  {
    element: '[data-tour="profile-switcher"]',
    popover: {
      title: '环境隔离',
      description: '在这里你可以切换多个独立的“环境”，\n通过环境管理选项，你可以轻松创建、切换、删除环境。',
      side: "bottom"
    }
  },
  {
    element: '[data-tour="profile-list"]',
    popover: {
      title: '环境列表',
      description: '这里记录了每个环境的基本信息，包括环境名称、环境路径、环境描述等。\n你可以点击任意环境项来切换到该环境，也可以点击相应按钮编辑、删除、启动环境。',
      side: "right"
    },
    onNextBefore: async () => {
      const appStore = useAppStore()
      appStore.uiState.showProfileDrawer = true
    }
  },
  {
    element: '[data-tour="profile-create"]',
    popover: {
      title: '创建环境',
      description: '在这里你可以创建新的环境，\n每个环境都有独立的模组列表、存档、路径配置等。',
      side: "right"
    },
  },
];

export const backupGuideSteps = [
  {
    element: '[data-tour="sidebar-tab"]',
    popover: {
      title: '备份（排序文件）管理',
      description: '在这里你可以切换到备份标签页，管理所有的排序文件，包括导入导出、自动备份、恢复、删除等操作。',
      side: "left"
    },
    onNextBefore: async () => {
      const appStore = useAppStore()
      // 切换到备份标签页
      appStore.setSidebarTab('backup')
    }
  },
  {
    element: '[data-tour="backup-list"]',
    popover: {
      title: '备份列表',
      description: '这里记录了所有的排序文件备份，可以点击任意备份项来查看该备份与现有排序文件的差异，也可以点击相应按钮加载、删除备份。',
      side: "left"
    }
  },
  {
    element: '[data-tour="backup-toolbar"]',
    popover: {
      title: '备份操作区',
      description: '这里提供了备份操作的按钮，包括导入导出排序文件、打开备份文件夹、刷新列表等操作，通过左侧帮助按钮可以查看自动备份的规则说明。',
      side: "left"
    },
  },
];

// 二级页面：库存枢纽引导
export const workspaceGuideSteps = [
  {
    element: '[data-tour="workspace-workshop-list"]', 
    popover: {
      title: '创意工坊库存列表',
      description: '这里显示了所有已订阅的创意工坊模组，你可以在列表中查看模组的基本信息，点击列表项即可查看模组该模组的变动时间线。\n也可以右键菜单进行更多操作，如禁用、启用、删除等。',
      side: "left"
    }
  },
  {
    element: '[data-tour="workspace-workshop-toolbar"]', 
    popover: {
      title: '库存操作区',
      description: '在这里你可以进行库存的搜索、筛选、排序查看等操作，支持禁用、新增、缺失模组的检测与筛选。',
      side: "bottom"
    }
  },
  {
    element: '[data-tour="workspace-self-list"]', 
    popover: {
      title: '管理器库存列表',
      description: '这里显示了所有由管理器下载的模组，跟其它列表操作一致。\n要注意使用该库的模组需要在环境开关中启用，另外首次下载时需要注意SteamCMD的初始化是否成功。',
      side: "left"
    }
  },
  {
    element: '[data-tour="workspace-tabs"]', 
    popover: {
      title: '其它页面',
      description: '这里可以切换页面，包括创意工坊检索、合集订阅、Github订阅等，功能简单就不多赘述了。',
      side: "left"
    }
  }
];