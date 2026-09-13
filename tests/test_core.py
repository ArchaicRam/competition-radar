# -*- coding: utf-8 -*-
"""自测：消息模板 + 增量存储 + 官方赛事规则 + 卡片/Excel（不联网）。

两种跑法等价（CI 用第二种）：
  python tests/test_core.py   # 零依赖直接跑
  pytest tests/ -q            # 兼容 pytest 收集
"""
import json
import os
import shutil
import sys
import xml.dom.minidom as minidom
import zipfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Competition
from src.message import build_message, build_no_new_message
from src.storage import Store
from src.csv_export import export_csv

_TMP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_test")


def _tmpdir(name: str) -> str:
    """每个测试用独立子目录（不用系统临时目录，兼容沙箱环境）。"""
    path = os.path.join(_TMP_ROOT, name)
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    return path


def _sample_new() -> list:
    # 截止日期用相对"今天"的未来时间，避免测试随日期漂移失败
    soon = (date.today() + timedelta(days=5)).isoformat()
    return [
        Competition(
            key="tianchi:1", title="AI+跨境黑客松巅峰赛", platform="tianchi",
            organizer="阿里云", url="https://tianchi.aliyun.com/competition/entrance/1",
            deadline=soon, reward="¥100,000", comp_type="AI",
            status="报名中",
        ),
        Competition(
            key="kaggle:test", title="Kaggle Titanic", platform="kaggle",
            organizer="Kaggle", url="https://www.kaggle.com/c/titanic",
            deadline="2026-08-10", reward="$10,000", comp_type="数据",
            status="报名中",
        ),
        Competition(
            key="nowcoder:NowCoder:1", title="牛客周赛 Round 155", platform="nowcoder",
            organizer="NowCoder", url="https://ac.nowcoder.com/acm/contest/138240",
            deadline="2099-01-01", comp_type="算法竞赛", status="未开始",
        ),
    ]


def test_message():
    new = _sample_new()
    updated = [
        Competition(
            key="df:999", title="某竞赛", platform="datafountain", organizer="某企业",
            deadline="2026-09-01", status="进行中",
        )
    ]
    msg = build_message(new, updated, max_items=20, deadline_alert_days=7)
    assert "AI+跨境黑客松" in msg
    assert "⏰" in msg  # 有即将截止标记
    assert "🔄" in msg  # 有更新列表
    assert build_message([], []) == ""
    assert build_no_new_message()


def test_store():
    tmp = _tmpdir("store")
    state = os.path.join(tmp, "state.json")
    store = Store(state)
    fetched = _sample_new()[:2]
    n, u = store.diff(fetched)
    assert len(n) == 2 and len(u) == 0, (n, u)
    store.update(fetched)
    # 第二次：只新增一条
    fetched2 = _sample_new()
    n2, u2 = store.diff(fetched2)
    assert len(n2) == 1 and n2[0].key == fetched2[2].key, (n2, u2)
    # 状态变化检测
    changed = Competition(**{**fetched2[0].to_dict(), "deadline": "2026-08-19"})
    n3, u3 = store.diff([changed, fetched2[1]])
    assert len(n3) == 0 and len(u3) == 1, (n3, u3)
    # url 变化也应视为更新
    moved = Competition(**{**fetched2[0].to_dict(), "url": "https://example.com/new"})
    n4, u4 = store.diff([moved])
    assert len(n4) == 0 and len(u4) == 1, (n4, u4)
    # last_total 元数据可用于骤降检测
    store.data["last_total"] = 2
    store.update([])
    assert Store(state).data["last_total"] == 2

    # CSV 导出
    csv_path = export_csv(store, os.path.join(tmp, "out.csv"))
    with open(csv_path, encoding="utf-8-sig") as f:
        content = f.read()
    assert "AI+跨境黑客松" in content


def test_official_rules():
    from src.official import is_official, prestige

    assert is_official("蓝桥杯全国软件和信息技术专业人才大赛", "") is True
    assert is_official("某某企业AI挑战赛", "某科技公司") is False
    # 学校竞赛目录补漏：新增识别的官方赛事
    for name in [
        "中国大学生工程实践与创新能力大赛", "全国大学生嵌入式芯片与系统设计竞赛",
        "中国高校智能机器人创意大赛", "中国机器人及人工智能大赛",
        "中国大学生程序设计竞赛", "大唐杯全国大学生移动通信5G技术大赛",
    ]:
        assert is_official(name, ""), name

    # 含金量评级（评分模型：业界+3 > 部委+2 > 名声+1）
    assert prestige("蓝桥杯", "", "") == "高"                      # 标题命中业界认可
    assert prestige("", "阿里云", "tianchi") == "高"               # 知名企业=业界认可
    assert prestige("", "某某科技有限公司", "datafountain") == "中"  # 无加分 → 默认中
    assert prestige("牛客周赛", "NowCoder", "nowcoder") == "低"     # 练习赛
    assert prestige("牛客暑期多校训练营", "NowCoder", "nowcoder") == "中"
    assert prestige("x", "x", "tianchi", rating="高") == "高"       # 规则无信号时 AI 评级兜底
    # "互联网+"同名赛事要区分：教育部主办 → 高；协会主办（技能应用赛）→ AI 评级为中
    assert prestige("2026年中国国际大学生创新大赛", "教育部、中央统战部、工业和信息化部等", "ai", rating="中") == "高"
    assert prestige("2026年第四届\"互联网+\"技能应用赛", "中国技术创业协会技术创新工作委员会", "ai", rating="中") == "中"
    assert prestige("\"互联网+\"大学生创新创业大赛", "教育部", "ai", rating="") == "高"  # 旧称也高
    # 用户规则：仅工信部认可（名声不大、业界不认可）→ 中
    assert prestige("某赛事", "工业和信息化部网络安全产业发展中心", "datafountain") == "中"
    # 工信部 + 业界认可 → 高
    assert prestige("某赛事", "工业和信息化部、中国计算机学会", "datafountain") == "高"
    # 名声大 + 业界认可 → 高
    assert prestige("创客中国", "工业和信息化部", "datafountain") == "高"
    # 练手赛 → 低
    assert prestige("用户新增预测练手赛", "科大讯飞股份有限公司", "xfyun") == "低"
    # 天池学习/新人/实战类 → 低；正规赛事（无主办方字段）→ 高
    assert prestige("天池新人实战赛", "", "tianchi") == "低"
    assert prestige("2026-具身极限挑战赛", "", "tianchi") == "高"
    assert prestige("Q力星期四", "", "tianchi") == "高"
    # 大学在讯飞平台挂的课题 → 中（不再因平台无脑高）
    assert prestige("野生东北虎个体识别挑战赛", "北京林业大学", "xfyun") == "中"
    assert prestige("智慧生活助理Skill开发挑战赛", "科大讯飞股份有限公司", "xfyun") == "高"


def test_schedules():
    from src.schedules import enrich_official

    today = datetime(2026, 8, 19)  # 模拟"当前"为 2026-08
    # 有真实截止日期 → 直接用，不推断
    note, keep = enrich_official("2026年高教社杯数学建模竞赛", "2026-09-10", {}, today)
    assert keep and note == ""
    # 数学建模报名窗口 6-9 月，8 月在窗口内 → 报名中（按往届）
    note, keep = enrich_official("2026年高教社杯数学建模竞赛", "", {}, today)
    assert keep and note == "报名中（按往届）"
    # 蓝桥杯窗口 10-3 月，8 月不在窗口且标题年份=今年 → 本届已过，移除
    note, keep = enrich_official("2026年蓝桥杯", "", {}, today)
    assert not keep
    # 下一届（2027年蓝桥杯）→ 保留并写"预计10月启动报名"
    note, keep = enrich_official("2027年蓝桥杯", "", {}, today)
    assert keep and "预计10月启动报名（按往届）" == note
    # 互联网+（窗口 3-5 月）8 月已过 → 移除
    note, keep = enrich_official("2026年中国国际大学生创新大赛", "", {}, today)
    assert not keep
    # 查不到往届规律 → 移除（不写"待核实"）
    note, keep = enrich_official("某某冷门官方赛事", "", {}, today)
    assert not keep


def test_sort_order():
    from src.official import prestige, sort_competitions

    new = _sample_new()
    sorted_comps = sort_competitions(new)
    # 官方A类排最前（本测试数据里没有官方赛，验证不报错即可）
    assert len(sorted_comps) == 3

    # 排序：官方赛事 > 含金量 > 主办方聚合（用户示例 ACBD）
    A = Competition(key="A", title="蓝桥杯全国软件和信息技术专业人才大赛", organizer="E", platform="tianchi")
    B = Competition(key="B", title="大学生创新创业训练计划年会展示", organizer="F", platform="tianchi")
    C = Competition(key="C", title="中国大学生计算机设计大赛", organizer="G", platform="tianchi")
    D = Competition(key="D", title="某某行业数据挑战赛", organizer="某市教育协会", platform="datafountain")
    assert prestige(A.title, A.organizer, A.platform) == "高"
    assert prestige(B.title, B.organizer, B.platform) == "中"
    assert prestige(C.title, C.organizer, C.platform) == "高"
    order = [c.key for c in sort_competitions([B, D, C, A])]
    assert order == ["A", "C", "B", "D"], order  # 官方(ABC)在前且按含金量 A,C > B，D 企业赛最后


def test_ctftime_convert():
    from src.fetchers.ctftime import CtfTimeFetcher

    f = CtfTimeFetcher({})
    # 用 CTFtime API 真实字段结构的样例（离线验证转换逻辑）
    ev = {
        "id": 3265,
        "title": "VolgaCTF 2026 Final",
        "start": "2026-09-17T05:00:00+00:00",
        "finish": "2026-09-17T15:00:00+00:00",
        "organizers": [{"id": 27094, "name": "VolgaCTF.org"}],
        "url": "https://volgactf.ru/en/volgactf-2026/final/",
        "ctftime_url": "https://ctftime.org/event/3265/",
        "format": "Attack-Defense",
        "onsite": True,
        "location": "Russia, Samara",
        "prizes": "TBA",
    }
    c = f._convert(ev)
    assert c is not None
    assert c.key == "ctftime:3265"
    assert c.platform == "ctftime"
    assert c.title == "VolgaCTF 2026 Final"
    assert c.deadline == "2026-09-17" and c.enabled_date == "2026-09-17"
    assert c.organizer == "VolgaCTF.org"
    assert c.url == "https://volgactf.ru/en/volgactf-2026/final/"  # 官网优先
    assert c.comp_type == "网络安全·攻防"
    assert c.reward == ""  # TBA 不展示

    # 缺 finish / 无标题 的坏数据要被拦
    assert f._convert({**ev, "finish": ""}) is None
    assert f._convert({**ev, "id": 9, "title": " "}) is None
    # prizes 文本保留并截断
    c2 = f._convert({**ev, "id": 7, "format": "Jeopardy",
                     "prizes": "现金奖励与纪念品，决赛资格与证书，" * 5})
    assert 0 < len(c2.reward) <= 60
    assert c2.comp_type == "网络安全"

    # 含金量：ctftime 平台默认中；国内权威安全赛标题命中规则为高
    from src.official import prestige
    assert prestige("某国际CTF", "某战队", "ctftime") == "中"
    assert prestige("第九届强网杯全国网络安全挑战赛", "", "ctftime") == "高"
    # 安全专项关键词识别
    from src.official import is_official
    for t in ["第四届网鼎杯网络安全大赛", "信息安全铁人三项赛（长城杯）",
              "第四届天网杯网络安全大赛", "第十届工业信息安全技能大赛"]:
        assert is_official(t, ""), t


def test_digest_card():
    new = _sample_new()
    from src.card import build_digest_card

    card = build_digest_card(new, {new[0].key}, bot_name="竞赛雷达", excel_link="", excel_path="data/competitions.xlsx")
    md = [e["text"]["content"] for e in card["elements"] if e.get("text", {}).get("tag") == "lark_md"]
    assert any("共 **3** 场" in m for m in md)
    assert any("今日新增" in m and "1" in m for m in md)  # 摘要含新增数
    assert card["header"]["template"] == "red"  # 有新增表头变红
    assert any("数据来源" in m for m in md)  # 来源说明
    assert len(json.dumps(card, ensure_ascii=False)) < 30000

    # 无新增时表头蓝色
    card2 = build_digest_card(new, set(), bot_name="竞赛雷达")
    assert card2["header"]["template"] == "blue"


def test_excel_export():
    tmp = _tmpdir("excel")
    new = _sample_new()
    from src.excel_export import export_excel

    xlsx = os.path.join(tmp, "out.xlsx")
    export_excel(new, {new[0].key}, path=xlsx)
    assert os.path.exists(xlsx)
    with zipfile.ZipFile(xlsx) as z:
        names = set(z.namelist())
        assert "[Content_Types].xml" in names
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        assert "xl/styles.xml" in names
        # 所有 XML 格式合法
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                minidom.parseString(z.read(n))
        sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "AI+跨境黑客松" in sheet1  # 数据写入
        assert 's="2"' in sheet1  # 新增行样式存在
        assert "蓝桥杯" not in sheet1


def test_sanitize():
    from src.runner import postprocess
    from src.official import concrete_stage

    good = Competition(
        key="x:1", title="某AI数据挑战赛", platform="datafountain",
        deadline=(date.today() + timedelta(days=10)).isoformat(),
    )
    undated = Competition(key="x:4", title="某开源活动项目招募", platform="AI发现·示例")
    pending = Competition(key="x:5", title="某黑客松活动", platform="AI发现·示例", status="待核实")
    dropped_c = Competition(key="x:2", title="全国大学生英语翻译大赛", platform="AI发现·示例")
    empty_c = Competition(key="x:3", title="", platform="tianchi")
    kept, dropped = postprocess([good, undated, pending, dropped_c, empty_c], {})
    assert [c.key for c in kept] == ["x:1", "x:4", "x:5"]
    by_key = {c.key: c for c in kept}
    # 阶段硬性要求：绝不出现"待核实"/空值
    assert by_key["x:1"].status == "报名中"   # 有有效截止
    assert by_key["x:4"].status == "进行中"   # 无截止
    assert by_key["x:5"].status == "进行中"   # 待核实 + 无截止 → 具体化
    reasons = {c.key: r for c, r in dropped}
    assert "与计算机主题无关" in reasons["x:2"]
    assert "标题为空" in reasons["x:3"]

    # concrete_stage 各分支
    assert concrete_stage("进行中", "") == "进行中"          # 具体状态原样保留
    assert concrete_stage("待核实", "2099-01-01") == "报名中"  # 待核实 + 未来截止
    assert concrete_stage("待核实", "以官网通知为准") == "进行中"  # 截止不可解析
    assert concrete_stage("", "") == "进行中"


def test_ai_stage_filter():
    from src.ai_discover import _to_competition

    soon = (date.today() + timedelta(days=10)).isoformat()
    base = {"title": "某开源活动", "organizer": "某研究所", "type": "开源活动"}

    # 提取阶段=已结束 → 直接剔除
    assert _to_competition({**base, "stage": "已结束"}, "https://x.example", "示例") is None
    # 提取阶段=报名中 → 保留并作为具体状态
    c = _to_competition({**base, "stage": "报名中", "deadline": soon}, "https://x.example", "示例")
    assert c is not None and c.status == "报名中"
    # 阶段看不出 → 状态留空（后续核实/兜底）
    c2 = _to_competition(dict(base), "https://x.example", "示例")
    assert c2 is not None and c2.status == ""
    # 乱值阶段不进入状态
    c3 = _to_competition({**base, "stage": "不知道"}, "https://x.example", "示例")
    assert c3 is not None and c3.status == ""


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
