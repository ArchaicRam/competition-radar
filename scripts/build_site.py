#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛雷达静态网站生成器：data/state.json -> site/index.html（单文件，零依赖）。

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
    data_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    sheet_btn = (
        f'<a class="btn ghost" href="{_esc(sheet_url)}" target="_blank" rel="noopener">📊 在线表格</a>'
        if sheet_url else ""
    )
    return _TEMPLATE.replace("__DATA__", data_json).replace("__SHEET_BTN__", sheet_btn) \
                    .replace("__UPDATED__", _esc(generated_at))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>竞赛雷达 · 大学生计算机竞赛聚合</title>
<style>
:root{
  --bg:#0a0e14;--panel:#111826;--panel2:#0d1320;--line:#1e2a3d;
  --text:#d6deeb;--muted:#8b98ab;--accent:#4ade80;--accent2:#38bdf8;
  --red:#ff5c5c;--orange:#ffb020;--green:#26de81;--blue:#5b9dff;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
code,.mono{font-family:ui-monospace,Consolas,"JetBrains Mono",monospace}
a{color:var(--accent2);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header{border-bottom:1px solid var(--line);background:rgba(10,14,20,.85);position:sticky;top:0;backdrop-filter:blur(8px);z-index:9}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:56px}
.logo{font-weight:700;font-size:17px;color:var(--text)}.logo span{color:var(--accent)}
.hero{padding:56px 0 28px}
.hero h1{font-size:34px;line-height:1.25}
.hero h1 em{font-style:normal;color:var(--accent)}
.hero p.sub{color:var(--muted);margin:10px 0 22px;font-size:15px}
.btns{display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-block;padding:9px 18px;border-radius:8px;font-weight:600;font-size:14px;border:1px solid var(--line)}
.btn.primary{background:var(--accent);color:#06210f;border-color:transparent}
.btn.primary:hover{filter:brightness(1.08);text-decoration:none}
.btn.ghost{color:var(--text)}.btn.ghost:hover{border-color:var(--accent2);text-decoration:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:26px 0 8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:26px;color:var(--accent)}
.stat.hot b{color:var(--red)}
.stat span{font-size:13px;color:var(--muted)}
.filters{position:sticky;top:56px;background:var(--bg);padding:12px 0;z-index:8;border-bottom:1px solid var(--line)}
.search{width:100%;padding:9px 14px;border-radius:8px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:14px;outline:none}
.search:focus{border-color:var(--accent2)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.chip{padding:4px 12px;border-radius:999px;border:1px solid var(--line);background:var(--panel2);color:var(--muted);font-size:12.5px;cursor:pointer;user-select:none}
.chip.on{color:#06210f;background:var(--accent);border-color:transparent;font-weight:700}
.chip.on.red{background:var(--red);color:#2b0505}
.chip.on.orange{background:var(--orange);color:#2b1a02}
.chip.on.blue{background:var(--blue);color:#04162e}
section{margin:30px 0}
h2{font-size:19px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
h2 .n{color:var(--muted);font-weight:400;font-size:14px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.card:hover{border-color:#2d3d57}
.card.高{border-left-color:var(--red)}.card.中{border-left-color:var(--orange)}.card.低{border-left-color:var(--green)}
.card.today{box-shadow:0 0 0 1px var(--accent2)}
.card .top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.card .title{font-weight:700;font-size:15px;color:var(--text)}
.card .title:hover{color:var(--accent2)}
.badge{flex-shrink:0;font-size:11.5px;padding:2px 9px;border-radius:999px;font-weight:700}
.badge.高{background:rgba(255,92,92,.14);color:var(--red)}
.badge.中{background:rgba(255,176,32,.14);color:var(--orange)}
.badge.低{background:rgba(38,222,129,.14);color:var(--green)}
.meta{font-size:13px;color:var(--muted)}
.meta b{color:var(--text);font-weight:600}
.foot{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:auto;padding-top:4px}
.tag{font-size:11.5px;padding:2px 9px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);color:var(--muted)}
.tag.dl.soon{background:rgba(255,92,92,.14);color:var(--red);border-color:transparent;font-weight:700}
.tag.dl.week{background:rgba(255,176,32,.14);color:var(--orange);border-color:transparent}
.tag.dl.ok{color:var(--green)}
.tag.new{background:rgba(56,189,248,.14);color:var(--accent2);border-color:transparent;font-weight:700}
.tag.official{background:rgba(255,215,0,.12);color:#ffd700;border-color:transparent}
.empty{color:var(--muted);text-align:center;padding:40px 0}
footer{border-top:1px solid var(--line);margin-top:50px;padding:22px 0 40px;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header><div class="wrap"><div class="logo">📡 竞赛<span>雷达</span></div><div class="mono" style="font-size:12.5px;color:var(--muted)">updated __UPDATED__</div></div></header>
<div class="hero"><div class="wrap">
  <h1>大学生计算机竞赛，<br><em>一页看完，不再错过。</em></h1>
  <p class="sub">每天自动扫描天池 / DataFountain / 讯飞 / 牛客 / Kaggle / CTFtime 与权威官方赛事渠道，AI 复核阶段与含金量，一条不漏。</p>
  <div class="btns"><a class="btn primary" href="#报名中">看正在报名的</a>__SHEET_BTN__</div>
  <div class="stats">
    <div class="stat"><b id="st-total">-</b><span>进行中总览</span></div>
    <div class="stat hot"><b id="st-new">-</b><span>今日新增</span></div>
    <div class="stat"><b id="st-dl">-</b><span>7 天内截止</span></div>
    <div class="stat"><b id="st-official">-</b><span>官方赛事</span></div>
  </div>
</div></div>
<div class="filters"><div class="wrap">
  <input class="search" id="q" type="search" placeholder="搜索赛事名称 / 主办方…">
  <div class="chips" id="chips"></div>
</div></div>
<main class="wrap" id="main"></main>
<footer><div class="wrap">数据由「竞赛雷达」每日自动抓取与 AI 复核，仅供参考；报名前请以赛事官网原文为准。<br>来源：阿里云天池 · DataFountain · 科大讯飞 · 牛客 · Kaggle · CTFtime · 官方赛事渠道 · AI 情报员</div></footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const q = document.getElementById('q'), chipsEl = document.getElementById('chips'), main = document.getElementById('main');
const GROUPS = [["报名中","var(--green)"],["进行中","var(--blue)"],["未开始","var(--muted)"]];
let active = {tag:null};

// 筛选 chips：类别 / 含金量 / 来源 / 今日新增
const catSet=[...new Set(DATA.map(x=>x.category))], ratSet=["高","中","低"], srcSet=[...new Set(DATA.map(x=>x.platform))];
const chips=[...catSet.map(c=>({k:"category",v:c,cls:"blue"})),
             ...ratSet.map(r=>({k:"rating",v:r,cls:r==="高"?"red":r==="中"?"orange":""})),
             {k:"today",v:"🆕 今日新增",cls:"blue"},
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
  const a=x.url?'<a class="title" href="'+x.url+'" target="_blank" rel="noopener">'+x.title+'</a>':'<span class="title">'+x.title+'</span>';
  return '<div class="card '+x.rating+(x.today?' today':'')+'">'
    +'<div class="top">'+a+'<span class="badge '+x.rating+'">'+x.rating+'</span></div>'
    +'<div class="meta"><b>'+(x.organizer||"主办方未知")+'</b>'+(x.type?' · '+x.type:'')+' · '+x.category+'</div>'
    +'<div class="foot">'+(x.official?'<span class="tag official">教育部目录</span>':'')
    +(x.today?'<span class="tag new">🆕 今日新增</span>':'')+dlTag(x)
    +(x.reward?'<span class="tag">💰 '+x.reward+'</span>':'')
    +(x.enabled?'<span class="tag">开始 '+x.enabled+'</span>':'')
    +'<span class="tag">'+x.platform+'</span></div></div>';
}
function render(){
  const kw=q.value.trim().toLowerCase();
  const list=DATA.filter(x=>{
    if(kw && !(x.title+" "+x.organizer).toLowerCase().includes(kw)) return false;
    const t=active.tag; if(!t) return true;
    return t.k==="today" ? x.today : x[t.k]===t.v;
  });
  let html="", shown=0;
  for(const [name,color] of GROUPS){
    const g=list.filter(x=>x.status===name);
    if(!g.length) continue;
    shown+=g.length;
    html+='<section id="'+name+'"><h2><span class="dot" style="background:'+color+'"></span>'+name+' <span class="n">'+g.length+' 场</span></h2><div class="grid">'+g.map(card).join("")+'</div></section>';
  }
  main.innerHTML = shown ? html : '<div class="empty">没有符合条件的赛事，换个筛选试试。</div>';
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
    ap = argparse.ArgumentParser(description="生成竞赛雷达静态网站")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--out", default="site/index.html")
    ap.add_argument("--sheet-url", default="", help="在线表格链接（英雄区按钮）")
    args = ap.parse_args()

    items = load_competitions(args.state)
    html = build_html(items, sheet_url=args.sheet_url, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"网站已生成: {args.out}（{len(items)} 场，{len(html) // 1024} KB）")


if __name__ == "__main__":
    main()
