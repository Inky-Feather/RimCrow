import { FIELD_TYPES } from './SearchTypes';

/**
 * 生成搜索系统的帮助文档数据
 * @param {SearchEngine} engine - 搜索引擎实例
 * @returns {Array} 分组后的帮助条目列表
 */
export function generateSearchHelp(engine) {
  if (!engine || !engine.schema) return [];

  const helpData = [];
  const entries = Object.entries(engine.schema);
  
  // 1. 按类型分组或按重要性排序
  // 这里简单按字母顺序，或者可以优先展示用户 Schema 定义的字段
  entries.sort((a, b) => {
      // 让配置了 Label 的排前面 (通常是重要字段)
      if (a[1].label && !b[1].label) return -1;
      if (!a[1].label && b[1].label) return 1;
      return a[0].localeCompare(b[0]);
  });

  entries.forEach(([key, config]) => {
    // 隐藏不想展示的字段 (比如没有 Label 且不是自动检测的重要字段)
    // 这里策略是：只要生成了指令，就应该让用户知道，但可以折叠显示
    
    // 收集别名 (包含手动和自动生成的)
    const aliases = Array.isArray(config.alias) ? config.alias : (config.alias ? [config.alias] : []);
    const aliasStr = aliases.length > 0 ? aliases.join(', ') : '';

    let usage = '';
    let desc = '';

    switch (config.type) {
      case FIELD_TYPES.BOOLEAN:
        usage = `${key}:+ / ${key}:-`;
        desc = '布尔开关 (支持 true/false, yes/no)';
        break;
      case FIELD_TYPES.LIST:
        usage = `${key}:Value`;
        desc = '列表包含匹配';
        break;
      case FIELD_TYPES.DATE:
        usage = `${key}:2023-01`;
        desc = '日期匹配';
        break;
      default: // String, Number
        usage = `${key}:Value`;
        desc = '文本包含匹配';
    }

    helpData.push({
      name: config.label || key, // 显示名称
      key: key,                 // 完整指令
      aliases: aliasStr,        // 简写
      usage: usage,             // 用法示例
      description: desc,        // 描述
      isDefault: config.defaultSearch // 是否包含在全文搜索
    });
  });

  return helpData;
}

/**
 * 生成极简、高密度的 HUD 风格帮助文档 (HTML)
 */
export function generateHtmlHelp(engine) {
  if (!engine || !engine.schema) return '<div class="p-2 text-xs">Loading...</div>';

  const schema = engine.schema;
  const entries = Object.entries(schema).filter(([_, conf]) => conf.searchable !== false);
  
  // 1. 字段排序：默认搜索的在前 -> 布尔值在前 -> 其他按首字母
  entries.sort((a, b) => {
    if (a[1].defaultSearch && !b[1].defaultSearch) return -1;
    if (!a[1].defaultSearch && b[1].defaultSearch) return 1;
    if (a[1].type === FIELD_TYPES.BOOLEAN && b[1].type !== FIELD_TYPES.BOOLEAN) return -1;
    if (a[1].type !== FIELD_TYPES.BOOLEAN && b[1].type === FIELD_TYPES.BOOLEAN) return 1;
    return engine.getPreferredKey(a[0]).length - engine.getPreferredKey(b[0]).length;
  });

  // 2. 样式常量 (Tailwind)
  const C = {
    box: 'text-xs text-gray-300 font-sans overflow-hidden',
    header: 'bg-text-main/5 py-1 px-2 border-b border-text-main/10 flex items-center justify-between',
    sectionTitle: 'text-[0.65rem] uppercase tracking-wider opacity-40 font-bold mt-2 mb-1 px-1',
    syntaxGrid: 'grid grid-cols-4 gap-1 px-1',
    syntaxItem: 'bg-text-main/5 rounded px-0.5 py-0.5 flex flex-col items-center justify-center text-center border border-text-main/5',
    fieldGrid: 'grid grid-cols-2 gap-x-2 gap-y-1 px-1 pb-2', // 双栏布局
    fieldRow: 'flex items-center border-l-2 border-text-main/15 pl-1 group',
    keyBadge: 'font-mono font-bold text-accent-primary bg-accent-primary/10 px-1.5 rounded text-xs min-w-[20px] text-center border border-accent-primary/20 group-hover:bg-accent-primary/20 transition-colors',
    label: 'text-gray-400 text-xs text-end truncate flex-1',
    footer: 'bg-text-main/5 px-3 py-2 text-[0.65rem] text-gray-500 border-t border-text-main/5 flex flex-wrap gap-x-4 gap-y-1'
  };
  // 是否是默认搜索字段
  const defaultMarker = '<span class="text-accent-highlight ml-1" title="默认包含在模糊搜索中">•</span>';

  // 3. 构建 HTML
  let html = `<div class="${C.box}">`;

  // === 顶部：标题 + 状态 ===
  html += `<div class="${C.header}">
      <span class="font-bold text-text-main">搜索说明</span>
      <span class="text-[0.65rem] bg-accent-highlight/20 text-accent-highlight px-1.5 rounded border border-accent-highlight/10">搜索指令速查</span>
    </div>`;

  // === 区域 1：基础语法 (3个核心卡片) ===
  html += `<div class="${C.sectionTitle}">基础搜索语法</div>`;
  html += `<div class="${C.syntaxGrid}">
    <div class="${C.syntaxItem}">
      <span class="opacity-60">直接搜索${defaultMarker}</span>
      <span class="font-mono bg-text-main/15 px-1.5 rounded text-text-main">关键词</span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">类别搜索</span>
      <span class="font-mono bg-text-main/15 px-1.5 rounded"><span class="text-accent-primary">类别</span>:关键词</span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">排除搜索</span>
      <span class="font-mono bg-text-main/15 px-1.5 rounded text-accent-danger">-<span class="text-accent-primary">类别</span><span class="text-text-main">:关键词</span></span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">判断搜索</span>
      <span class="font-mono bg-text-main/15 px-1.5 rounded"><span class="text-accent-primary">类别</span>:<span class="text-accent-success">+</span>/<span class="text-accent-danger">-</span>/<span class="text-accent-warn">_</span></span>
    </div>
  </div>`;

  // === 区域 2：字段列表 (高密度双栏) ===
  html += `<div class="${C.sectionTitle}">可用类别字段</div>`;
  html += `<div class="${C.fieldGrid}">`;
  
  entries.forEach(([realKey, conf]) => {
    const shortKey = engine.getPreferredKey(realKey);

    html += `
      <div class="${C.fieldRow}">
        <div class="${C.keyBadge}">${shortKey}:</div>
        <div class="${C.label}">${conf.label===realKey ? realKey : realKey + ` (${conf.label})` }${conf.defaultSearch ? defaultMarker :''}</div>
      </div>
    `;
  });
  html += `</div>`; // End Field Grid

  html += `<div>判断搜索支持三态搜索：true / false / null  ( + / - / _ )</div>`;
  html += `<div>多个搜索条件关系可选 “与”/ “或” 逻辑</div>`;
  html += `<div class="text-xs text-gray-400">与：多个条件同时满足</div>`;
  html += `<div class="text-xs text-gray-400">或：满足任意一个条件即可</div>`;
  html += `</div>`;
  return html;
}