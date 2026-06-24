/** Dashboard i18n — 唯一入口（勿在 index.html 内重复定义 LANG/I18N） */
(function (global) {
  'use strict';

  var STRINGS = {
    zh: {
      title: 'ziyan-mailbus Platform',
      search: '搜索消息...',
      refresh: '刷新全部',
      auto: '自动刷新',
      send: '发消息',
      heartbeat: '💓 心跳',
      api_token_ph: 'API Token（可选，写操作需 Bearer）',
      api_base_ph: 'API 地址',
      nav_ziyan: '子言',
      nav_human_queue: '任务处理',
      nav_intake: '商前',
      nav_workflows: 'Workflow',
      nav_content: '内容',
      nav_overview: '总览',
      nav_agents: 'Agent',
      nav_bulletin: '公告栏',
      nav_audit: '任务审计',
      nav_stats: '统计',
      nav_patrol: '巡检日报',
      nav_alerts: '告警',
      nav_clinic: 'mailbus诊所',
      nav_settings: '配置中心',
      footer_running: '系统运行中',
      noData: '暂无数据',
      loading: '加载中...',
      stats_total: '消息',
      stats_success: '完成',
      stats_timeout: '超时',
      stats_failed: '失败',
      stats_agent_rank: '📊 Agent 排行',
      stats_token: '🔋 Token 统计',
      stats_trend: '📈 7 日趋势',
      status_online: '在线',
      status_offline: '离线',
      btn_perm: '权限',
      lang_switched: '已切换为中文',
    },
    en: {
      title: 'ziyan-mailbus Platform',
      search: 'Search messages...',
      refresh: 'Refresh All',
      auto: 'Auto Refresh',
      send: 'Send Message',
      heartbeat: '💓 Heartbeat',
      api_token_ph: 'API Token (optional, Bearer for writes)',
      api_base_ph: 'API base URL',
      nav_ziyan: 'Ziyan',
      nav_human_queue: 'Human Queue',
      nav_intake: 'Intake',
      nav_workflows: 'Workflows',
      nav_content: 'Content',
      nav_overview: 'Overview',
      nav_agents: 'Agents',
      nav_bulletin: 'Bulletin',
      nav_audit: 'Task Audit',
      nav_stats: 'Statistics',
      nav_patrol: 'Patrol Reports',
      nav_alerts: 'Alerts',
      nav_clinic: 'Clinic',
      nav_settings: 'Settings',
      footer_running: 'System Online',
      noData: 'No data',
      loading: 'Loading...',
      stats_total: 'Messages',
      stats_success: 'Done',
      stats_timeout: 'Timeout',
      stats_failed: 'Failed',
      stats_agent_rank: '📊 Agent Ranking',
      stats_token: '🔋 Token Usage',
      stats_trend: '📈 7-Day Trend',
      status_online: 'Online',
      status_offline: 'Offline',
      btn_perm: 'Permissions',
      lang_switched: 'Switched to English',
    },
  };

  var lang = localStorage.getItem('mailbus_lang') || 'zh';

  function t(key) {
    var pack = STRINGS[lang] || STRINGS.zh;
    return pack[key] != null ? pack[key] : (STRINGS.zh[key] || key);
  }

  function applyLang(next) {
    lang = next || 'zh';
    localStorage.setItem('mailbus_lang', lang);
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';

    var h1 = document.querySelector('.top-bar h1');
    if (h1) h1.textContent = t('title');

    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.dataset.i18n;
      if (!key) return;
      var val = t(key);
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = val;
      else el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
      var key = el.dataset.i18nPlaceholder;
      if (key) el.placeholder = t(key);
    });

    var sel = document.getElementById('langSelect');
    if (sel && sel.value !== lang) sel.value = lang;
  }

  function switchLang(next) {
    applyLang(next);
    if (typeof global.toast === 'function') {
      global.toast(t('lang_switched'), 'success');
    }
    var active = document.querySelector('.tab-content.active');
    if (active && active.id === 'tab-stats' && typeof global.renderStatsTab === 'function') {
      global.renderStatsTab().catch(function () {});
    }
  }

  function initLang() {
    applyLang(lang);
  }

  global.MailbusI18n = { t: t, applyLang: applyLang, switchLang: switchLang, initLang: initLang, getLang: function () { return lang; } };
  global.t = t;
  global.switchLang = switchLang;
})(typeof window !== 'undefined' ? window : globalThis);
