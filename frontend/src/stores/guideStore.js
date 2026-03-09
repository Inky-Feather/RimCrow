// frontend/src/stores/guideStore.js
import { defineStore } from 'pinia'
import { useAppStore } from './appStore'
import { nextTick } from 'vue'
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import { GUIDE_VERSION, mainGuideSteps, workspaceGuideSteps, modListGuideSteps, profileGuideSteps, backupGuideSteps } from '../modules/guide/guideConfig'
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
    key: 'modList', 
    title: '模组列表快速上手',
    description: '了解如何在模组列表中查看、启用、禁用、搜索模组。',
    steps: modListGuideSteps 
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
      beforeStartCallback()
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