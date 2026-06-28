"""生成统一风格的拟人 SVG 头像 for mailbus dashboard"""

import os

AVATARS = {
    "lingzhao": {"name": "灵昭", "role": "方案设计", "color": "#00d4ff", "hair": "M280 240 Q320 200 380 230 Q440 200 480 240", "accent": "星环"},
    "lingjin": {"name": "灵瑾", "role": "网络安全", "color": "#8b5cf6", "hair": "M280 260 Q320 210 380 240 Q440 210 480 260", "accent": "盾牌"},
    "xiaoqi": {"name": "小七", "role": "调度", "color": "#10b981", "hair": "M280 250 Q350 190 380 220 Q410 190 480 250", "accent": "齿轮"},
    "yige": {"name": "一哥", "role": "运营", "color": "#f59e0b", "hair": "M280 230 Q340 210 380 240 Q420 210 480 230", "accent": "罗盘"},
    "lingxiao": {"name": "灵霄", "role": "技术负责人", "color": "#3b82f6", "hair": "M275 245 Q330 195 380 225 Q430 195 485 245", "accent": "闪电"},
    "dali": {"name": "大力", "role": "编码", "color": "#ef4444", "hair": "M278 255 Q340 205 380 235 Q420 205 482 255", "accent": "代码"},
    "lingxi": {"name": "灵犀", "role": "技术雷达", "color": "#22d3ee", "hair": "M282 235 Q345 205 380 220 Q415 205 478 235", "accent": "雷达"},
    "lingjian": {"name": "灵鉴", "role": "代码审查", "color": "#a78bfa", "hair": "M285 248 Q335 215 380 238 Q425 215 475 248", "accent": "眼镜"},
    "lingyan": {"name": "灵验", "role": "测试验证", "color": "#34d399", "hair": "M280 242 Q340 198 380 228 Q420 198 480 242", "accent": "勾选"},
    "lingxun": {"name": "灵巡", "role": "巡检官", "color": "#f472b6", "hair": "M276 252 Q338 208 380 232 Q422 208 484 252", "accent": "望远镜"},
}

def gen_svg(key, info):
    c = info["color"]
    name = info["name"]
    role = info["role"]
    hair = info["hair"]
    
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 762 762" fill="none" shape-rendering="auto">
<defs>
  <style>
    @keyframes blink {{ 0%, 90%, 100% {{ transform: scaleY(1); }} 95% {{ transform: scaleY(0.1); }} }}
    @keyframes float {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-4px); }} }}
    @keyframes glow {{ 0%, 100% {{ opacity: 0.5; }} 50% {{ opacity: 1; }} }}
    @keyframes pulse {{ 0%, 100% {{ r: 2.5; opacity: 0.8; }} 50% {{ r: 4; opacity: 0.3; }} }}
    .eye {{ animation: blink 4s ease-in-out infinite; transform-origin: center; }}
    .body {{ animation: float 6s ease-in-out infinite; }}
    .halo {{ animation: glow 3s ease-in-out infinite; }}
    .pulse-dot {{ animation: pulse 2s ease-in-out infinite; }}
  </style>
</defs>
<mask id="vm">
  <rect width="762" height="762" fill="#fff" />
</mask>
<g mask="url(#vm)">
  <rect width="762" height="762" fill="#0d0a2a"/>
  <!-- 背景光环 -->
  <circle cx="381" cy="381" r="320" stroke="{c}22" stroke-width="1.5" fill="none" class="halo"/>
  <circle cx="381" cy="381" r="290" stroke="{c}11" stroke-width="0.5" fill="none"/>
  <!-- 头部主体 -->
  <ellipse cx="381" cy="350" rx="110" ry="120" fill="#1a1535" stroke="{c}33" stroke-width="1"/>
  <!-- 头发 -->
  <path d="{hair}" stroke="{c}" stroke-width="6" fill="none" stroke-linecap="round" class="body"/>
  <!-- 刘海 -->
  <path d="M340 215 Q360 205 370 220 Q380 205 400 215" stroke="{c}" stroke-width="4" fill="none" stroke-linecap="round"/>
  <!-- 左眼 -->
  <ellipse cx="340" cy="320" rx="18" ry="20" fill="#e0e6f0" class="eye"/>
  <!-- 右眼 -->
  <ellipse cx="422" cy="320" rx="18" ry="20" fill="#e0e6f0" class="eye"/>
  <!-- 瞳孔 -->
  <ellipse cx="340" cy="320" rx="8" ry="10" fill="{c}"/>
  <ellipse cx="422" cy="320" rx="8" ry="10" fill="{c}"/>
  <!-- 高光 -->
  <circle cx="336" cy="316" r="3" fill="#fff" opacity="0.8"/>
  <circle cx="418" cy="316" r="3" fill="#fff" opacity="0.8"/>
  <!-- 嘴巴 -->
  <path d="M365 380 Q381 395 397 380" stroke="{c}88" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- 脸颊彩点 -->
  <circle cx="310" cy="350" r="6" fill="{c}22" class="pulse-dot"/>
  <circle cx="452" cy="350" r="6" fill="{c}22" class="pulse-dot" style="animation-delay:1s"/>
  <!-- 装饰元素 -->
  <g class="body">
    <text x="381" y="540" font-family="'Noto Serif SC','Source Han Serif SC',serif" font-size="32" fill="{c}" text-anchor="middle" font-weight="600">{name}</text>
    <text x="381" y="570" font-family="sans-serif" font-size="15" fill="#8892b0" text-anchor="middle">{role}</text>
  </g>
</g>
</svg>'''

out_dir = "/mnt/e/ai_tools/mail/docs/avatars"
os.makedirs(out_dir, exist_ok=True)

for key, info in AVATARS.items():
    svg = gen_svg(key, info)
    path = os.path.join(out_dir, f"{key}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"✅ {key}.svg")

print(f"\n共生成 {len(AVATARS)} 个头像")
