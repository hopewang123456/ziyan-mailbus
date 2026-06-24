/** Agent 资料卡 — 3D 动态肖像容器 */
(function (global) {
  'use strict';

  function textureCandidates(profile, agentId) {
    var id = agentId || profile.name || '';
    var urls = [];
    if (profile.avatar_url) urls.push(profile.avatar_url);
    urls.push('avatars/' + id + '_portrait.png');
    urls.push('avatars/' + id + '_portrait.svg');
    return urls;
  }

  function videoCandidate(profile, agentId) {
    var id = agentId || profile.name || '';
    var a = profile.avatar_animated || '';
    if (/\.(webp|mp4|webm)$/i.test(a)) return a;
    return 'avatars/' + id + '_animated.webp';
  }

  function portraitHostHtml(agentId) {
    return '<div class="portrait-hud">'
      + '<div class="portrait-hud-inner" id="agentPortrait3dHost" data-agent="' + agentId + '" '
      + 'style="width:340px;height:400px">'
      + '<span class="portrait-hud-tag">NEURAL · AVATAR</span>'
      + '<span class="portrait-hud-corner tl"></span><span class="portrait-hud-corner tr"></span>'
      + '<span class="portrait-hud-corner bl"></span><span class="portrait-hud-corner br"></span>'
      + '<span class="portrait-hud-scan"></span></div></div>';
  }

  function mountPortrait3D(profile, agentId, accent) {
    var host = document.getElementById('agentPortrait3dHost');
    if (!host) return;
    var id = agentId || profile.name || '';
    var colors = (global.AGENT_COLORS || (global.MailbusAvatars && MailbusAvatars.AGENT_COLORS)) || {};
    var acc = accent || colors[id] || '#38bdf8';
    var candidates = [
      'avatars/' + id + '_animated.webp',
      'avatars/' + id + '_portrait.png',
      profile.avatar_url,
    ].filter(Boolean);

    // candidates 供 Three.js 静态兜底；动图优先走 probeAnimated

    function showLiveMotion(src) {
      host.innerHTML = '<div class="portrait-live-wrap" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:14px;background:radial-gradient(ellipse at 50% 30%,' + acc + '22,transparent 70%)">'
        + '<img class="portrait-live-motion" src="' + src + '" alt="" '
        + 'style="max-width:108%;max-height:108%;object-fit:cover;border-radius:12px;'
        + 'box-shadow:0 16px 48px rgba(0,0,0,0.5),0 0 24px ' + acc + '33"/></div>';
    }

    function showStatic(src) {
      host.innerHTML = '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:14px;background:radial-gradient(ellipse at 50% 30%,' + acc + '22,transparent 70%)">'
        + '<img src="' + src + '" alt="" style="max-width:108%;max-height:108%;object-fit:cover;border-radius:12px;'
        + 'box-shadow:0 16px 48px rgba(0,0,0,0.5),0 0 24px ' + acc + '33"/></div>';
    }

    function tryThree(urls) {
      if (global.MailbusThree && MailbusThree.mountAgentPortrait3D) {
        MailbusThree.mountAgentPortrait3D(host, { textureUrls: urls, accent: acc, staticPortrait: true });
      }
    }

    var animUrl = 'avatars/' + id + '_animated.webp';
    var staticCandidates = [
      'avatars/' + id + '_portrait.png',
      profile.avatar_url,
    ].filter(Boolean);

    function tryStatic(idx) {
      if (idx >= staticCandidates.length) { tryThree(staticCandidates); return; }
      var src = staticCandidates[idx];
      var img = new Image();
      img.onload = function() { showStatic(src); };
      img.onerror = function() { tryStatic(idx + 1); };
      img.src = src + (src.indexOf('?') >= 0 ? '&' : '?') + '_t=' + Date.now();
    }

    function probeAnimated() {
      var img = new Image();
      img.onload = function() { showLiveMotion(animUrl + '?_t=' + Date.now()); };
      img.onerror = function() { tryStatic(0); };
      img.src = animUrl + '?_t=' + Date.now();
    }
    if (global.MailbusThree && MailbusThree.destroyAgentPortrait3D) MailbusThree.destroyAgentPortrait3D();
    probeAnimated();
  }

  function mergeProfile(profile, agentId) {
    var id = agentId || (profile && profile.name) || '';
    var cfg = (profile && profile.config) || {};
    var card = (profile && profile.card) || {};
    var idText = (profile && profile.identity) || '';
    function field(key) {
      var re = new RegExp('\\*\\*' + key + '\\*\\*[：:]\\s*([^|\\n]+)');
      var m = idText.match(re);
      return m ? m[1].trim() : '';
    }
    function ziyanBond() {
      if (card.ziyan_bond) return card.ziyan_bond;
      var pats = [/-\s+\*\*对子言[^*]*\*\*[：:]\s*(.+)/, /-\s+\*\*与子言\*\*[：:]\s*(.+)/];
      for (var i = 0; i < pats.length; i++) { var m = idText.match(pats[i]); if (m) return m[1].trim(); }
      return '';
    }
    function parseTraits() {
      var out = [], tm = idText.match(/##\s*(?:核心特质|人格特质)[\s\S]*?(?=##|$)/);
      if (!tm) return out;
      tm[0].split('\n').forEach(function (line) {
        var x = line.match(/-\s+\*\*(.+?)\*\*[：:]?\s*(.*)/);
        if (x && !/^对子言|^与子言/.test(x[1])) out.push(x[2] ? x[1] + ' — ' + x[2] : x[1]);
      });
      return out;
    }
    return {
      id: id,
      name: card.name || cfg.name || id,
      gender: card.gender || field('性别'),
      age: card.age || field('年龄'),
      zodiac: card.zodiac || field('星座'),
      mbti: card.mbti || field('MBTI'),
      role: card.role || field('角色') || cfg.role || '',
      motto: card.motto || field('座右铭'),
      ziyan_bond: ziyanBond(),
      personality: card.personality || '',
      traits: (card.traits && card.traits.length) ? card.traits : parseTraits(),
      work: (idText.match(/##\s*职责[\s\S]*?(?=##|$)/) || [''])[0].replace(/##\s*职责[：:]*\s*/, '').trim(),
      skills: profile.skills || [],
      soul: profile.soul || '',
      identityFull: idText,
      animated: profile.avatar_animated || ('avatars/' + id + '_animated.webp'),
      portrait: profile.avatar_url || ('avatars/' + id + '_portrait.png'),
    };
  }

  function infoGrid(p, esc) {
    function cell(label, val, style) {
      return '<div class="profile-field"><div class="profile-label">' + label + '</div><div class="profile-value"' + (style ? ' style="' + style + '"' : '') + '>' + esc(val) + '</div></div>';
    }
    var h = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    h += cell('姓名', p.name) + cell('性别', p.gender || '—');
    h += cell('年龄', p.age || '—') + cell('星座', p.zodiac || '—');
    h += cell('MBTI', p.mbti || '—', 'color:var(--accent-cyan)') + cell('角色', p.role || '—');
    h += '</div>';
    if (p.motto) h += '<div class="profile-field" style="margin-top:10px"><div class="profile-label">座右铭</div><div class="profile-value" style="font-size:13px;font-style:italic;color:var(--accent-cyan)">' + esc(p.motto) + '</div></div>';
    if (p.ziyan_bond) h += '<div class="profile-field" style="margin-top:10px;border-color:rgba(244,114,182,0.25)"><div class="profile-label">💫 与子言</div><div class="profile-value" style="font-size:13px;line-height:1.65;color:var(--text-secondary);font-weight:400">' + esc(p.ziyan_bond) + '</div></div>';
    if (p.personality || (p.traits && p.traits.length)) {
      h += '<div class="profile-field" style="margin-top:10px"><div class="profile-label">性格</div><div class="profile-value" style="font-size:13px;line-height:1.6;color:var(--text-secondary);font-weight:400">' + esc(p.personality || p.traits.slice(0, 2).join(' · ')) + '</div></div>';
    }
    if (p.traits && p.traits.length) {
      h += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:8px">' + p.traits.slice(0, 6).map(function (t) {
        return '<span style="background:rgba(0,212,255,0.06);color:var(--accent-cyan);padding:3px 10px;border-radius:8px;font-size:11px;border:1px solid rgba(0,212,255,0.08)">' + esc(String(t).split('—')[0].substring(0, 24)) + '</span>';
      }).join('') + '</div>';
    }
    return h;
  }

  global.MailbusProfiles = {
    mergeProfile: mergeProfile,
    portraitHostHtml: portraitHostHtml,
    mountPortrait3D: mountPortrait3D,
    infoGrid: infoGrid,
  };
})(typeof window !== 'undefined' ? window : globalThis);
