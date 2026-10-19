// 浮层只挂到所属主体，避免全局 body 层级互相覆盖。
export const POPOVER_PORTAL_KEY = Symbol('popover-portal')

// 只记录已打开的面板；Esc 交给仍可交互的最内层，关闭即移除。
export const openPopovers = []
