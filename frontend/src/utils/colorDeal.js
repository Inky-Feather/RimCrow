/**
 * 获取Tailwind根节点的CSS变量颜色值
 * @param {string} name - 颜色名/完整CSS变量名(如 primary / --color-primary)
 * @returns {string} 纯净的颜色值（#xxx / rgb() / rgba()）
 */
export const getTailwindColor = (name) => {
  // 修复：严格入参校验，避免startsWith报错
  if (!name || typeof name !== 'string') return '';
  // 拼接规范的CSS变量名
  const varName = name.startsWith('--') ? name : `--color-${name}`;
  const root = document.documentElement;
  // 获取根节点计算后的样式并去空格
  const color = getComputedStyle(root).getPropertyValue(varName).trim();
  return color;
};

/**
 * 获取RGB格式的Tailwind颜色
 * @param {string} name - 颜色名/完整CSS变量名
 * @returns {string} rgb(r,g,b) 格式颜色值
 */
export const getTailwindColorRgb = (name) => {
  const color = getTailwindColor(name);
  if (color.startsWith('rgb') && !color.startsWith('rgba')) return color;
  else if (color.startsWith('#')) return hexToRgb(color);
  else {
    console.error(`getTailwindColorRgb Error: 颜色变量【${name}】取值无效，值为：${color}`);
    return 'rgb(0, 0, 0)';
  }
};

/**
 * 获取RGBA格式的Tailwind颜色（带透明度）
 * @param {string} name - 颜色名/完整CSS变量名
 * @param {number} alpha - 透明度 0~1
 * @returns {string} rgba(r,g,b,alpha) 格式颜色值
 */
export const getTailwindColorRgba = (name, alpha = 1) => {
  // 修复：校验透明度取值范围，强制兜底0~1
  const validAlpha = Math.max(0, Math.min(1, Number(alpha)) || 1);
  const color = getTailwindColorRgb(name);
  return color.replace('rgb', 'rgba').replace(')', `, ${validAlpha})`);
};

/**
 * 获取十六进制格式的Tailwind颜色
 * @param {string} name - 颜色名/完整CSS变量名
 * @returns {string} #xxxxxx 格式颜色值
 */
export const getTailwindColorHex = (name) => {
  const color = getTailwindColor(name);
  if (color.startsWith('rgb') && !color.startsWith('rgba')) return rgbToHex(color);
  else if (color.startsWith('#')) return color;
  else {
    console.error(`getTailwindColorHex Error: 颜色变量【${name}】取值无效，值为：${color}`);
    return '#000000';
  }
};

/**
 * 十六进制颜色转RGB格式
 * @param {string} hex - #fff / #ffffff 格式
 * @returns {string} rgb(r,g,b) 格式
 */
export const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return 'rgb(0, 0, 0)';
  let cleanHex = hex.replace('#', '');
  // 兼容3位短十六进制 #fff → #ffffff
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(char => char + char).join('');
  }
  // 校验是否为合法6位十六进制
  if (cleanHex.length !== 6 || !/^[0-9a-fA-F]+$/.test(cleanHex)) {
    console.error(`hexToRgb Error: 非法十六进制颜色值 → ${hex}`);
    return 'rgb(0, 0, 0)';
  }
  // 十六进制转十进制 + 边界校验0~255
  const r = Math.max(0, Math.min(255, parseInt(cleanHex.substring(0, 2), 16)));
  const g = Math.max(0, Math.min(255, parseInt(cleanHex.substring(2, 4), 16)));
  const b = Math.max(0, Math.min(255, parseInt(cleanHex.substring(4, 6), 16)));
  // 修复：函数名对应，返回纯rgb格式 ✔️
  return `rgb(${r}, ${g}, ${b})`;
};

/**
 * 十六进制颜色转RGBA格式（带透明度）
 * @param {string} hex - #fff / #ffffff 格式
 * @param {number} alpha - 透明度 0~1
 * @returns {string} rgba(r,g,b,alpha) 格式
 */
export const hexToRgba = (hex, alpha = 1) => {
  // 修复：校验透明度取值范围，强制兜底0~1 ✔️
  const validAlpha = Math.max(0, Math.min(1, Number(alpha)) || 1);
  return hexToRgb(hex).replace('rgb', 'rgba').replace(')', `, ${validAlpha})`);
};

/**
 * RGB颜色转十六进制格式 ✔️ 完全重构修复核心逻辑
 * @param {string} rgb - rgb(r,g,b) 格式（兼容有无空格）
 * @returns {string} #xxxxxx 格式（小写+补零）
 */
export const rgbToHex = (rgb) => {
  if (!rgb || typeof rgb !== 'string' || !rgb.startsWith('rgb(') || !rgb.endsWith(')')) {
    console.error(`rgbToHex Error: 非法RGB颜色值 → ${rgb}`);
    return '#000000';
  }
  // 修复：正确解析RGB，兼容带空格/无空格格式 ✔️
  const cleanRgb = rgb.replace(/rgb\(|\)/g, '').split(',').map(item => Number(item.trim()));
  // 校验是否为合法的3个数值分量
  if (cleanRgb.length !== 3) {
    console.error(`rgbToHex Error: RGB分量数量错误 → ${rgb}`);
    return '#000000';
  }
  // 转十六进制 + 补零 + 边界校验0~255
  const toHex = (num) => {
    const val = Math.max(0, Math.min(255, Number(num)) || 0);
    return val.toString(16).padStart(2, '0');
  };
  const [r, g, b] = cleanRgb;
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toLowerCase();
};