# -*- coding: utf-8 -*-
"""自测：消息模板 + 增量存储逻辑（不联网）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Competition
from src.message import build_message, build_no_new_message
from src.storage import Store
from src.csv_export import export_csv


def main():
    # ---- 消息模板 ----
    new = [
        Competition(
            key="tianchi:1", title="AI+跨境黑客松巅峰赛", platform="tianchi",
            organizer="阿里云", url="https://tianchi.aliyun.com/competition/entrance/1",
            deadline="2026-08-20", reward="¥100,000", comp_type="AI",
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
    updated = [
        Competition(
            key="df:999", title="某竞赛", platform="datafountain", organizer="某企业",
            deadline="2026-09-01", status="进行中",
        )
    ]
    msg = build_message(new, updated, max_items=20, deadline_alert_days=7)
    print("===== 推送消息预览 =====")
    print(msg)
    assert "AI+跨境黑客松" in msg
    assert "⏰" in msg  # 有即将截止标记
    assert "🔄" in msg  # 有更新列表
    print("===== 无新比赛消息 =====")
    print(build_no_new_message())
    assert build_message([], []) == ""

    # ---- 增量存储 ----
    # 沙箱环境无法写系统临时目录，这里用工作区内的临时目录（先清空上次残留）
    import shutil
    tmp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_test")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    state = os.path.join(tmp, "state.json")
    store = Store(state)
    fetched = [new[0], new[1]]
    n, u = store.diff(fetched)
    assert len(n) == 2 and len(u) == 0, (n, u)
    store.update(fetched)
    # 第二次：只新增一条
    fetched2 = [new[0], new[1], new[2]]
    n2, u2 = store.diff(fetched2)
    assert len(n2) == 1 and n2[0].key == new[2].key, (n2, u2)
    # 状态变化检测
    changed = Competition(**{**new[0].to_dict(), "deadline": "2026-08-19"})
    n3, u3 = store.diff([changed, new[1]])
    assert len(n3) == 0 and len(u3) == 1, (n3, u3)
    # CSV 导出
    csv_path = export_csv(store, os.path.join(tmp, "out.csv"))
    with open(csv_path, encoding="utf-8-sig") as f:
        content = f.read()
    assert "AI+跨境黑客松" in content
    print("\n===== 存储/CSV 自测通过 =====")
    print("csv sample:", content[:200].replace("\n", " | "))

    # ---- 卡片构建（情报日报） ----
    from src.card import build_digest_card
    from src.official import sort_competitions, is_official, prestige

    assert is_official("蓝桥杯全国软件和信息技术专业人才大赛", "") is True
    assert is_official("某某企业AI挑战赛", "某科技公司") is False

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

    sorted_comps = sort_competitions(new)
    # 官方A类排最前（本测试数据里没有官方赛，验证不报错即可）
    assert len(sorted_comps) == 3

    card = build_digest_card(new, {new[0].key}, bot_name="竞赛雷达", excel_link="", excel_path="data/competitions.xlsx")
    md = [e["text"]["content"] for e in card["elements"] if e.get("text", {}).get("tag") == "lark_md"]
    assert any("共 **3** 场" in m for m in md)
    assert any("今日新增" in m and "1" in m for m in md)  # 摘要含新增数
    assert card["header"]["template"] == "red"  # 有新增表头变红
    assert any("数据来源" in m for m in md)  # 来源说明
    import json
    assert len(json.dumps(card, ensure_ascii=False)) < 30000

    # 无新增时表头蓝色
    card2 = build_digest_card(new, set(), bot_name="竞赛雷达")
    assert card2["header"]["template"] == "blue"

    # ---- Excel 生成（纯标准库 xlsx，校验 zip 结构） ----
    from src.excel_export import export_excel
    import zipfile
    import xml.dom.minidom as minidom

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
    print("===== 卡片/Excel 自测通过 =====")
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
