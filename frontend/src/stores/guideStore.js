// frontend/src/stores/guideStore.js
import { defineStore } from 'pinia'
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import {
  GUIDE_VERSION,
  mainGuideSteps,
  workflowGuideSteps,
  modListGuideSteps,
  issueGuideSteps,
  profileGuideSteps,
  backupGuideSteps,
  workspaceGuideSteps,
  workshopBrowserGuideSteps,
  collectionGuideSteps,
  githubGuideSteps,
  ruleCenterGuideSteps,
  conflictGuideSteps,
  aiConfigGuideSteps,
  aiReviewGuideSteps,
  logAnalysisGuideSteps,
} from '../modules/guide/guideConfig'
import { useToast } from 'vue-toastification'

// 1. 将所有可用的引导流程集中定义在这里，便于“引导中心”组件动态渲染
export const allGuides = [
  { 
    key: 'main', 
    title: '主界面快速上手',
    description: '了解软件的基本功能及功能分布，还有一些常用操作。',
    steps: mainGuideSteps 
  },
  {
    key: 'workflow',
    title: '主线操作闭环',
    description: '掌握 刷新 -> 排序 -> 保存 -> 启动 的标准流程。',
    steps: workflowGuideSteps,
  },
  { 
    key: 'modList', 
    title: '模组列表快速上手',
    description: '了解如何在模组列表中查看、启用、禁用、搜索模组。',
    steps: modListGuideSteps 
  },
  {
    key: 'issues',
    title: '问题处理与一键修复',
    description: '学会看问题汇总、快速补缺失项和逐项排查。',
    steps: issueGuideSteps,
  },
  { 
    key: 'backup', 
    title: '备份管理快速上手',
    description: '了解如何备份和管理排序文件。',
    steps: backupGuideSteps 
  },
  { 
    key: 'profile', 
    title: '环境管理快速上手',
    description: '了解如何管理游戏环境、路径设置和其他相关配置。',
    steps: profileGuideSteps 
  },
  {
    key: 'rules',
    title: '规则中心快速上手',
    description: '了解规则来源、优先级、动态规则与全局启停。',
    steps: ruleCenterGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.uiState.showRuleDrawer = true;
    }
  },
  {
    key: 'aiConfig',
    title: 'AI 配置快速上手',
    description: '了解如何启用 AI、配置接口并完成连通性测试。',
    steps: aiConfigGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.openSettingsPanel();
    }
  },
  {
    key: 'aiReview',
    title: 'AI 结果检阅',
    description: '了解如何复核批量生成结果、单项修订并统一写回。',
    steps: aiReviewGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      const hasResults = Array.isArray(appStore.aiBatchResults) && appStore.aiBatchResults.length > 0;
      if (!hasResults) return false;
      appStore.uiState.showAiReviewModal = false;
      return true;
    }
  },
  {
    key: 'logAnalysis',
    title: '日志分析快速上手',
    description: '了解如何切换日志、发起 AI 分析，并利用侧栏持续追问排错。',
    steps: logAnalysisGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      const ai = appStore.settings.ai || {};
      const hasMinimalAiConfig = !!(
        ai.enabled &&
        String(ai.model || '').trim() &&
        (String(ai.api_key || '').trim() || String(ai.base_url || '').trim())
      );
      if (!hasMinimalAiConfig) {
        return {
          blocked: true,
          message: '请先在“设置 -> AI 集成”中启用并配置好 AI，建议完成一次连通性测试后再继续日志分析教程。'
        };
      }
      appStore.uiState.showLogDrawer = false;
      return true;
    }
  },
  {
    key: 'workspace', 
    title: '库存枢纽导览',
    description: '了解如何在库存枢纽中查看、管理和操作库存。',
    steps: workspaceGuideSteps,
    // 【关键】增加一个 pre-action，告诉引导中心在开始前要先打开某个弹窗
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.uiState.showWorkspace = true;
    }
  },
  {
    key: 'workspaceWorkshop',
    title: '创意工坊检索',
    description: '了解如何搜索工坊模组并决定订阅、下载或继续查看依赖。',
    steps: workshopBrowserGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.uiState.showWorkspace = true;
    }
  },
  {
    key: 'workspaceCollection',
    title: '合集订阅管理',
    description: '了解如何导入合集、补齐缺失项并应用合集顺序。',
    steps: collectionGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.uiState.showWorkspace = true;
    }
  },
  {
    key: 'workspaceGithub',
    title: 'GitHub 订阅',
    description: '了解如何解析仓库、订阅来源并查看部署时间线。',
    steps: githubGuideSteps,
    beforeStart: () => {
      const appStore = useAppStore();
      appStore.uiState.showWorkspace = true;
    }
  },
  {
    key: 'conflict',
    title: '重复模组冲突处理',
    description: '了解如何保留正确副本，并批量禁用或删除其余副本。',
    steps: conflictGuideSteps,
    beforeStart: () => {
      const modStore = useModStore();
      const hasConflicts =
        (Array.isArray(modStore.conflictList) && modStore.conflictList.length > 0) ||
        (Array.isArray(modStore.coexistenceList) && modStore.coexistenceList.length > 0);
      return hasConflicts;
    }
  },
]

export const useGuideStore = defineStore('guide', () => {

  const appStore = useAppStore();
  const toast = useToast();

  // 内部标记完成的函数，可复用
  const markAsDone = async (uniqueKey) => {
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.guide_mark_as_done(uniqueKey)
      appStore.settings.completed_guides[uniqueKey] = 'done'
    }
  }

  // 通用执行引擎
  const runGuide = async (guideKey, stepsConfig, force = false, beforeStartCallback = null) => {
    const uniqueKey  = `${guideKey}_${GUIDE_VERSION}`
    // 从后端 settings 中读取状态
    const completedGuides = appStore.settings.completed_guides || {}
    
    if (!force && completedGuides[uniqueKey] === 'done') {
      return // 已经看过了，跳过
    }
    // 如果定义了前置动作，先执行
    if (beforeStartCallback) {
      const canStart = await beforeStartCallback()
      if (typeof canStart === 'string') {
        toast.info(canStart)
        return
      }
      if (canStart && typeof canStart === 'object' && canStart.blocked) {
        toast.info(canStart.message || '当前教程需要先满足前置条件后才能开始')
        return
      }
      if (canStart === false) {
        toast.info('当前教程需要先进入对应场景后才能开始')
        return
      }
      // 等待弹窗动画
      await new Promise(r => setTimeout(r, 400)) 
    }

    const driverObj = driver({
      showProgress: true,
      animate: true,
      allowClose: false,
      doneBtnText: '我知道了',
      closeBtnText: '跳过',
      nextBtnText: '下一步',
      prevBtnText: '上一步',
      // 【关键配置】针对高 z-index 的弹窗，如果不加这个，遮罩可能会被你的弹窗盖住！
      // 我们的弹窗通常 z-index 是 100 左右，这里设个大的
    //   popoverClass: 'driver-popover', 
      onDestroyStarted: () => {
        markAsDone(uniqueKey) // 调用统一的标记函数
        driverObj.destroy()
      },
      steps: stepsConfig.map(step => ({
        ...step,
        popover: {
          ...step.popover,
          // 拦截下一步点击
          onNextClick: async () => {
            // 如果当前步骤定义了“前往下一步之前”的动作
            if (step.onNextBefore) {
              await step.onNextBefore();
              // 如果有异步操作（比如打开弹窗），这里等待一下动画
              await new Promise(r => setTimeout(r, 400));
            }
            driverObj.moveNext();
          }
        }
      }))
    });

    // 【重要延迟】如果是弹窗刚打开，需要等弹窗的 CSS Transition 动画播放完毕（通常300ms）
    // 否则获取到的坐标是动画过程中的坐标，会导致高亮框错位
    setTimeout(() => {
      driverObj.drive()
    }, 400) 
  }

  // 暴露具体的场景触发器
  // const startMainGuide = (force = false) => runGuide('main', mainGuideSteps, force)
  // const startWorkspaceGuide = (force = false) => runGuide('workspace', workspaceGuideSteps, force)
  // const startModListGuide = (force = false) => { 
  //   // 检测主页引导是否完成
  //   const mainGuideDone = localStorage.getItem('rim_guide_main_' + GUIDE_VERSION) === 'done'
  //   if (!mainGuideDone) return
  //   runGuide('modList', modListGuideSteps, force) 
  // }
  
  // 根据 key 动态启动引导
  const startGuideByKey = (guideKey, force = false) => {
    const guide = allGuides.find(g => g.key === guideKey)
    if (guide) {
      runGuide(guide.key, guide.steps, force, guide.beforeStart)
    }
  }
  // 跳过单个引导
  const skipGuideByKey = (guideKey) => {
    const uniqueKey = `${guideKey}_${GUIDE_VERSION}`
    markAsDone(uniqueKey)
    toast.info(`已跳过教程: ${allGuides.find(g=>g.key===guideKey)?.title || ''}`)
  }

  // 重置所有引导状态
  const resetAllGuides = async () => {
    if (window.pywebview && window.pywebview.api) {
      appStore.closeSettingsPanel()
      await window.pywebview.api.guide_reset_all()
      appStore.settings.completed_guides = {}
      toast.success("所有教程引导已重置！")
    }
  }

  return { startGuideByKey, skipGuideByKey, resetAllGuides }
})
