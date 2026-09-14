#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛探静态网站生成器：data/state.json -> site/index.html（单文件，零依赖）。

风格参考 hello-ctf.com：深色终端风、英雄区、赛事按状态分组、
倒计时徽标、来源/类别/含金量筛选。数据以 JSON 内嵌，前端 JS 渲染，
双击本地文件即可打开（无 CORS 问题），GitHub Pages 直接托管。

用法：
  python scripts/build_site.py                       # 默认 data/state.json -> site/index.html
  python scripts/build_site.py --sheet-url <url>     # 英雄区加"在线表格"按钮
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.official import (
    categorize,
    concrete_stage,
    is_irrelevant,
    prestige,
)  # noqa: E402
from src.platforms import PLATFORM_NAMES  # noqa: E402

# 含金量颜色（与在线表格一致：高=红、中=橙、低=绿）
_RATING_RANK = {"高": 0, "中": 1, "低": 2}


def _bucket(status: str, deadline: str, dl_date, today) -> str:
    """把各种具体状态归到网页的标准分组（报名中/进行中/未开始）。"""
    s = status or ""
    if "报名中" in s:
        return "报名中"
    if "进行中" in s:
        return "进行中"
    if "未开始" in s or "预计" in s:
        return "未开始"
    if "已结束" in s:
        return "进行中"  # 理论上已被过滤，兜底不放"已结束"分组
    if dl_date and dl_date >= today:
        return "报名中"
    return "进行中"


def load_competitions(state_path: str) -> list:
    """从 state.json 读取并规范化比赛数据（与日报同口径）。"""
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    today = datetime.now().date()
    items = []
    for d in state.get("competitions", {}).values():
        title = (d.get("title") or "").strip()
        platform = d.get("platform", "")
        # 与日报同一套相关性兜底：语言/文科/设计/职业类与招募公告不上网页
        if not title or is_irrelevant(title, platform=platform):
            continue
        deadline = (d.get("deadline") or "").strip()
        try:
            dl_date = datetime.strptime(deadline[:10], "%Y-%m-%d").date() if deadline else None
        except ValueError:
            dl_date = None
        # 已截止的不上网页（与日报数据质量规则一致）
        if dl_date and dl_date < today:
            continue
        detected = (d.get("detected_at") or "")[:10]
        items.append({
            "title": (d.get("title") or "").strip(),
            "organizer": (d.get("organizer") or "").strip(),
            "url": (d.get("url") or "").strip(),
            "deadline": deadline[:10] if dl_date else "",
            "enabled": (d.get("enabled_date") or "").strip()[:10],
            "status": _bucket(d.get("status", ""), deadline, dl_date, today),
            "reward": (d.get("reward") or "").strip(),
            "type": (d.get("comp_type") or "").strip(),
            "platform": PLATFORM_NAMES.get(d.get("platform", ""), d.get("platform", "")),
            "category": categorize(d.get("title", ""), d.get("organizer", ""), d.get("platform", "")),
            "rating": prestige(d.get("title", ""), d.get("organizer", ""), d.get("platform", ""), d.get("rating", "")),
            "official": categorize(d.get("title", ""), d.get("organizer", ""), d.get("platform", "")) == "官方赛事",
            "today": detected == today.isoformat(),
        })
    # 排序与日报一致：官方优先 -> 含金量 -> 截止日期升序（无截止放后）
    items.sort(key=lambda x: (
        0 if x["official"] else 1,
        _RATING_RANK.get(x["rating"], 1),
        (0, x["deadline"]) if x["deadline"] else (1, ""),
    ))
    return items


def build_html(items: list, sheet_url: str = "", generated_at: str = "") -> str:
    # "</" 转义成 "<\/"，防止内嵌 JSON 里出现 </script> 提前闭合标签
    data_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    sheet_btn = (
        f'<a class="btn line" href="{_esc(sheet_url)}" target="_blank" rel="noopener">在线表格 <span class="arr">→</span></a>'
        if sheet_url else ""
    )
    return (_TEMPLATE.replace("__DATA__", data_json)
            .replace("__SHEET_BTN__", sheet_btn)
            .replace("__UPDATED__", _esc(generated_at)))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>赛探 — 大学生计算机竞赛，一页看完</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{
  color-scheme: light;
  --paper:#ffffff; --wash:#f8fafc; --line:#e6eaf1;
  --ink:#33d3eb; --ink-2:rgba(51,211,235,.85); --ink-3:rgba(51,211,235,.55);
  --accent:#2563eb; --accent-soft:#eff6ff; --hl:rgba(0,241,255,.4);
  --red:#dc2626; --red-soft:#fef2f2;
  --orange:#d97706; --orange-soft:#fffbeb;
  --green:#059669; --green-soft:#ecfdf5;
  --mono:"JetBrains Mono","SFMono-Regular",Consolas,Menlo,monospace;
  --sans:Inter,-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
  --radius:14px;
  --glass:rgba(255,255,255,.4); /* 面板透明度：40%（覆盖在背景图上） */
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--wash) url('bg.png') center/cover no-repeat fixed;color:var(--ink);font-family:var(--sans);line-height:1.7}
::selection{background:var(--hl)}
a{color:inherit;text-decoration:none}
.wrap{max-width:1060px;margin:0 auto;padding:0 22px}
.mono{font-family:var(--mono)}

/* 顶栏 */
header{position:sticky;top:0;z-index:9;background:rgba(255,255,255,.2);backdrop-filter:blur(4px);border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:58px}
.logo{font-weight:800;font-size:16px;letter-spacing:-.01em;color:#33d3eb;text-shadow:0 1px 3px rgba(0,0,0,.25)}
.logo .m{font-family:var(--mono);color:#33d3eb;animation:blink 1.1s steps(1) infinite}
header .upd{font-family:var(--mono);font-size:11.5px;color:#33d3eb;letter-spacing:.06em;text-shadow:0 1px 3px rgba(0,0,0,.25)}
@keyframes blink{50%{opacity:0}}

/* Hero banner：圆角大卡片 + 点阵纹理 + 柔光 */
.banner{position:relative;margin-top:26px;border:1px solid var(--line);border-radius:26px;overflow:hidden;background:transparent;padding:52px 54px 44px}
.banner-grid{position:relative}
.kicker{font-family:var(--mono);font-size:14px;color:#00f1ff;min-height:24px;letter-spacing:.02em;white-space:pre;display:block;line-height:1.5;text-shadow:0 1px 3px rgba(255,255,255,.9),0 0 8px rgba(255,255,255,.7)}
.cursor{display:inline-block;width:9px;height:17px;background:#00f1ff;vertical-align:-3px;margin-left:2px;animation:blink 1s steps(1) infinite}
.banner h1{font-size:clamp(30px,3.6vw,42px);font-weight:800;letter-spacing:-.03em;line-height:1.2;margin:10px 0 14px;color:#000}
.hl{background:linear-gradient(transparent 62%,var(--hl) 62%)}
.banner .sub{font-size:15.5px;color:#000;max-width:560px;text-shadow:0 1px 2px rgba(255,255,255,.85)}
.cta-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:10px;font-weight:600;font-size:14px;border:1.5px solid transparent;transition:all .15s}
.btn.dark{background:#4a52bc;color:#fff;box-shadow:0 12px 26px -12px rgba(74,82,188,.55)}
.btn.dark:hover{transform:translateY(-2px)}
.btn.line{border-color:var(--line);color:var(--ink);background:transparent}
.btn.line:hover{border-color:var(--ink);transform:translateY(-2px)}
.btn .arr{font-family:var(--mono)}

/* 统计条 */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:22px}
.stat{background:rgba(255,255,255,.2);border:1px solid var(--line);border-radius:var(--radius);padding:14px 18px;backdrop-filter:blur(2px)}
.stat b{display:block;font-family:var(--mono);font-size:26px;font-weight:700;letter-spacing:-.02em}
.stat.hot b{color:var(--red)}
.stat span{font-size:12.5px;color:var(--ink-2);text-shadow:0 1px 2px rgba(255,255,255,.9)}
.stat .lbl{font-family:var(--mono);font-size:10px;color:#475569;letter-spacing:.16em;text-shadow:0 1px 2px rgba(255,255,255,.9)}

/* 筛选区 */
.filters{position:sticky;top:58px;z-index:8;background:rgba(255,255,255,.05);backdrop-filter:blur(4px);border-bottom:1px solid var(--line);padding:13px 0;margin-top:34px}
.search{width:100%;padding:10px 16px;border-radius:10px;border:1px solid #5b37b7;background:rgba(255,255,255,.05);color:#33a8eb;font-family:var(--mono);font-size:13.5px;outline:none;transition:border-color .15s}
.search:focus{border-color:var(--accent);background:var(--paper)}
.search::placeholder{color:rgba(58,168,235,.85)}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.chip{padding:4px 13px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:rgb(93,216,244);font-size:12px;font-family:var(--mono);cursor:pointer;user-select:none;transition:all .12s}
.chip:hover{border-color:var(--ink)}
.chip.on{background:var(--ink);border-color:var(--ink);color:#fff;font-weight:600}
.chip.on.blue{background:var(--accent);border-color:var(--accent)}
.chip.on.red{background:var(--red);border-color:var(--red)}
.chip.on.orange{background:var(--orange);border-color:var(--orange)}
.chip.on.green{background:var(--green);border-color:var(--green)}

/* 分组与卡片 */
section{margin:38px 0 10px;scroll-margin-top:150px} /* 锚点跳转时给吸顶筛选栏留出空间，第一行卡片不被遮挡 */
h2{font-size:20px;font-weight:800;letter-spacing:-.02em;display:flex;align-items:baseline;gap:10px;margin-bottom:16px}
h2 .en{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--ink-3);letter-spacing:.16em}
h2 .n{font-family:var(--mono);font-size:12px;color:var(--ink-3);font-weight:400;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
.card{background:rgba(255,255,255,.2);backdrop-filter:blur(2px);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;display:flex;flex-direction:column;gap:9px;transition:all .15s}
.card:hover{transform:translateY(-2px);border-color:var(--ink)}
.card.today{box-shadow:0 0 0 2px var(--accent)}
.card .top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.card .title{font-weight:700;font-size:14.5px;line-height:1.45;color:#000}
.card .title:hover{color:var(--accent)}
.badge{flex-shrink:0;font-family:var(--mono);font-size:11px;font-weight:700;padding:2px 10px;border-radius:999px}
.badge.高{background:var(--red-soft);color:var(--red)}
.badge.中{background:var(--orange-soft);color:var(--orange)}
.badge.低{background:var(--green-soft);color:var(--green)}
.meta{font-size:13px;color:rgb(118,157,255)}
.meta b{color:var(--ink);font-weight:600}
.foot{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:auto;padding-top:4px}
.tag{font-family:var(--mono);font-size:11px;padding:2px 9px;border-radius:7px;background:rgba(255,255,255,.55);border:1px solid var(--line);color:var(--ink-2)}
.tag.dl.soon{background:var(--red-soft);color:var(--red);border-color:transparent;font-weight:700}
.tag.dl.week{background:var(--orange-soft);color:var(--orange);border-color:transparent;font-weight:600}
.tag.dl.ok{background:var(--green-soft);color:var(--green);border-color:transparent}
.tag.new{background:var(--accent-soft);color:var(--accent);border-color:transparent;font-weight:700}
.tag.official{background:#fffbeb;color:#b45309;border-color:#fde68a;font-weight:600}
.empty{color:var(--ink-3);text-align:center;padding:48px 0;font-family:var(--mono);font-size:13px}
footer{border-top:1px solid var(--line);margin-top:54px;padding:24px 0 44px;color:var(--ink-3);font-size:12.5px}
footer .m{font-family:var(--mono);color:var(--accent)}
@media (max-width:720px){.banner{padding:34px 24px 30px;border-radius:18px}}
</style>
</head>
<body>
<header><div class="wrap">
  <div class="logo">赛探<span class="m">_</span></div>
  <div class="upd">updated __UPDATED__</div>
</div></header>

<div class="wrap">
  <div class="banner"><div class="banner-grid">
    <div>
      <div class="kicker"><span id="typewriter"></span><span class="cursor"></span></div>
      <h1>大学生计算机竞赛，<br>一页看完，<span class="hl">不再错过。</span></h1>
      <p class="sub">每天自动扫描天池 / DataFountain / 讯飞 / 牛客 / Kaggle / CTFtime 与权威官方渠道，AI 复核阶段与含金量，只收录技术性强的比赛。</p>
      <div class="cta-row">
        <a class="btn dark" href="#报名中">看正在报名的 <span class="arr">→</span></a>
        __SHEET_BTN__
      </div>
    </div>
    <div class="stats">
      <div class="stat"><span class="lbl">TOTAL</span><b id="st-total">-</b><span>进行中总览</span></div>
      <div class="stat hot"><span class="lbl">NEW</span><b id="st-new">-</b><span>今日新增</span></div>
      <div class="stat"><span class="lbl">DEADLINE</span><b id="st-dl">-</b><span>7 天内截止</span></div>
      <div class="stat"><span class="lbl">OFFICIAL</span><b id="st-official">-</b><span>官方赛事</span></div>
    </div>
  </div></div>
</div>

<div class="filters"><div class="wrap">
  <input class="search" id="q" type="search" placeholder="$ grep 赛事名称 / 主办方 ...">
  <div class="chips" id="chips"></div>
</div></div>

<main class="wrap" id="main"></main>

<footer><div class="wrap">
  <div>数据由「赛探」每日自动抓取与 AI 复核，仅供参考；报名前请以赛事官网原文为准。</div>
  <div>来源：阿里云天池 · DataFountain · 科大讯飞 · 牛客 · Kaggle · CTFtime · 官方赛事渠道 · AI 情报员 <span class="m">EOF _</span></div>
</div></footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const q = document.getElementById('q'), chipsEl = document.getElementById('chips'), main = document.getElementById('main');
const GROUPS = [["报名中","SIGN-UP","var(--green)"],["进行中","LIVE","var(--accent)"],["未开始","UPCOMING","var(--ink-3)"]];
let active = {tag:null};

/* 打字机：几行终端命令，从头敲到尾一遍（55ms/字），敲完停住、光标继续闪 */
const LINES = [
  "$ saitan scan --sources all --daily",
  "  [ok] tianchi ......... 26 comps",
  "  [ok] ctftime ......... 30 comps",
  "  [ai] stage verified, expired dropped",
  "$ deadline --within 7d --notify",
  "$ flag{never_miss_a_deadline}",
];
(function(){ const el = document.getElementById('typewriter'); let li = 0, ci = 0;
  (function tick(){ const line = LINES[li];
    el.textContent = LINES.slice(0, li).join("\\n") + (li ? "\\n" : "") + line.slice(0, ++ci);
    if (ci === line.length) {
      li += 1;
      if (li === LINES.length) return;   // 敲完即停，光标仍闪烁
      return setTimeout(tick, 350);
    }
    setTimeout(tick, 55);
  })();
})();

const catSet=[...new Set(DATA.map(x=>x.category))], ratSet=["高","中","低"], srcSet=[...new Set(DATA.map(x=>x.platform))];
const chips=[...catSet.map(c=>({k:"category",v:c,cls:"blue"})),
             {k:"today",v:"🆕 今日新增",cls:"blue"},
             ...ratSet.map(r=>({k:"rating",v:r,cls:r==="高"?"red":r==="中"?"orange":"green"})),
             ...srcSet.map(s=>({k:"platform",v:s,cls:""}))];
chips.forEach(c=>{
  const el=document.createElement("span");el.className="chip";el.textContent=c.v;
  el.onclick=()=>{ if(active.tag===c){el.classList.remove("on",c.cls);active.tag=null;}
    else{ chipsEl.querySelectorAll(".chip.on").forEach(e=>e.className="chip");el.classList.add("on",c.cls);active.tag=c;}
    render();};
  chipsEl.appendChild(el);
});
q.oninput=render;

function daysLeft(d){ if(!d)return null; const t=new Date(d+"T23:59:59+08:00")-new Date(); return Math.floor(t/864e5); }
function dlTag(x){ const n=daysLeft(x.deadline);
  if(n===null) return '<span class="tag dl">截止未知</span>';
  if(n<0) return '<span class="tag dl">已结束</span>';
  if(n===0) return '<span class="tag dl soon">⏰ 今天截止</span>';
  const cls=n<=3?"soon":n<=7?"week":"ok";
  return '<span class="tag dl '+cls+'">⏰ '+n+' 天后截止</span>'; }
function card(x){
  const inner='<div class="top"><span class="title">'+x.title+'</span><span class="badge '+x.rating+'">'+x.rating+'</span></div>'
    +'<div class="meta"><b>'+(x.organizer||"主办方未知")+'</b>'+(x.type?' · '+x.type:'')+' · '+x.category+'</div>'
    +'<div class="foot">'+(x.official?'<span class="tag official">教育部目录</span>':'')
    +(x.today?'<span class="tag new">🆕 今日新增</span>':'')+dlTag(x)
    +(x.reward?'<span class="tag">💰 '+x.reward+'</span>':'')
    +(x.enabled?'<span class="tag">开始 '+x.enabled+'</span>':'')
    +'<span class="tag">'+x.platform+'</span></div>';
  // 有链接的赛事：整张卡片都是可点击的链接
  const cls='card'+(x.today?' today':'');
  return x.url
    ? '<a class="'+cls+'" href="'+x.url+'" target="_blank" rel="noopener" title="'+x.title+'">'+inner+'</a>'
    : '<div class="'+cls+'">'+inner+'</div>';
}
function render(){
  const kw=q.value.trim().toLowerCase();
  const list=DATA.filter(x=>{
    if(kw && !(x.title+" "+x.organizer).toLowerCase().includes(kw)) return false;
    const t=active.tag; if(!t) return true;
    return t.k==="today" ? x.today : x[t.k]===t.v;
  });
  let html="", shown=0;
  for(const [name,en,color] of GROUPS){
    const g=list.filter(x=>x.status===name);
    if(!g.length) continue;
    shown+=g.length;
    html+='<section id="'+name+'"><h2>'+name+' <span class="en">'+en+'</span><span class="n">'+g.length+' 场</span></h2><div class="grid">'+g.map(card).join("")+'</div></section>';
  }
  main.innerHTML = shown ? html : '<div class="empty">[0 results] 没有符合条件的赛事，换个筛选试试_</div>';
  document.getElementById("st-total").textContent=DATA.length;
  document.getElementById("st-new").textContent=DATA.filter(x=>x.today).length;
  document.getElementById("st-dl").textContent=DATA.filter(x=>{const n=daysLeft(x.deadline);return n!==null&&n>=0&&n<=7}).length;
  document.getElementById("st-official").textContent=DATA.filter(x=>x.official).length;
}
render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="生成赛探静态网站")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--out", default="site/index.html")
    ap.add_argument("--sheet-url", default="", help="在线表格链接（英雄区按钮）")
    ap.add_argument("--bg", default="assets/bg.png", help="页面背景图（复制到输出目录 bg.png）")
    args = ap.parse_args()

    items = load_competitions(args.state)
    html = build_html(items, sheet_url=args.sheet_url, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    bg_note = ""
    if args.bg and os.path.exists(args.bg):
        import shutil
        bg_out = os.path.join(os.path.dirname(os.path.abspath(args.out)), "bg.png")
        shutil.copy2(args.bg, bg_out)
        bg_note = f"，背景图 {os.path.getsize(bg_out) // 1024} KB"
    print(f"网站已生成: {args.out}（{len(items)} 场，{len(html) // 1024} KB{bg_note}）")


if __name__ == "__main__":
    main()
