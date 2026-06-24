/** Dashboard 机器人头像 — 唯一入口（替代 AGENT_ICONS emoji + cyberSvg） */
(function (global) {
  'use strict';

  var AGENT_COLORS = {
    lingzhao: '#00d4ff', lingjin: '#8b5cf6', lingxi: '#22d3ee', lingxun: '#f472b6',
    lingtuo: '#06b6d4', lingzhang: '#ec4899', xiaoqi: '#10b981', yige: '#f59e0b',
    lingxiao: '#3b82f6', dali: '#ef4444', lingjian: '#a78bfa', lingyan: '#34d399',
    ziyan: '#f59e0b',
  };

  var AVATAR_BASE = 'avatars/';

  /** 内联机器人 SVG（无文件时的 fallback） */
  function robotSvgInline(name, size, color) {
    var c = color || AGENT_COLORS[name] || '#64748b';
    var sz = size || 20;
    return '<svg class="agent-robot-inline" viewBox="0 0 32 32" width="' + sz + '" height="' + sz + '" aria-hidden="true">' +
      '<rect x="6" y="9" width="20" height="19" rx="5" fill="#12122a" stroke="' + c + '" stroke-width="1.4"/>' +
      '<line x1="16" y1="9" x2="16" y2="4" stroke="' + c + '" stroke-width="1.5"/>' +
      '<circle cx="16" cy="3" r="1.8" fill="' + c + '"/>' +
      '<circle cx="12" cy="17" r="2.5" fill="' + c + '"/><circle cx="20" cy="17" r="2.5" fill="' + c + '"/>' +
      '</svg>';
  }

  /** HTML：img 优先，fallback 内联 SVG */
  function agentIconHtml(name, size) {
    if (!name) return '';
    var sz = size || 20;
    var color = AGENT_COLORS[name] || '#64748b';
    var png = AVATAR_BASE + name + '_portrait.png';
    return '<img class="agent-avatar" src="' + png + '" width="' + sz + '" height="' + sz + '" alt="" ' +
      'onerror="this.style.opacity=0.3" ' +
      'style="border-radius:50%;border:2px solid ' + color + '88;vertical-align:middle;object-fit:cover;display:inline-block;box-shadow:0 0 8px ' + color + '33;background:' + color + '22"/>';
  }

  /** 兼容旧 emoji 拼接：返回 HTML 片段（非纯文本） */
  function agentIcon(name, size) {
    return agentIconHtml(name, size || 16);
  }

  /** Agent 列表卡片用大头像 */
  function agentAvatar(name, color, size) {
    return agentIconHtml(name, size || 32);
  }

  global.MailbusAvatars = {
    AGENT_COLORS: AGENT_COLORS,
    agentIconHtml: agentIconHtml,
    agentIcon: agentIcon,
    agentAvatar: agentAvatar,
    robotSvgInline: robotSvgInline,
  };
  global.agentIconHtml = agentIconHtml;
  global.agentAvatar = agentAvatar;
})(typeof window !== 'undefined' ? window : globalThis);
