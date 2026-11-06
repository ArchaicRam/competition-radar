# -*- coding: utf-8 -*-
"""official_registry 自测：用一张小目录验证判定是否修好了体检报告里的 4 类错误。

运行： python test_official_registry.py
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:                                   # 仓库根：from src import official_registry
    import official_registry as reg
except ImportError:                    # 跑在 src/ 里
    from src import official_registry as reg
CATALOG = next((p for p in (HERE / "registry_catalog.json",
                            HERE / "src" / "registry_catalog.json",
                            HERE / "data" / "registry_catalog.json")
                if p.is_file()), None)

# 目录不存在时先造一份最小可用目录，保证逻辑可测
if CATALOG is None:
    CATALOG = HERE / "registry_catalog.json"
    stub = {
        "meta": {"source": "stub", "verified_at": "2026-11-05"},
        "events": [
            {"id": "lanqiao", "name": "蓝桥杯全国大学生软件和信息技术大赛",
             "aliases": ["蓝桥杯"], "organizer": "中国软件行业协会",
             "organizer_ok": ["中国软件行业协会"],
             "site": "https://dasai.lanqiao.cn/", "list_type": "main", "official_grade": "A"},
            {"id": "gcxl", "name": "中国大学生工程实践与创新能力大赛",
             "aliases": ["工创赛", "工程实践与创新能力大赛"], "organizer": "教育部",
             "organizer_ok": ["教育部", "工程训练教学指导委员会"],
             "site": "http://www.gcxl.edu.cn", "list_type": "main", "official_grade": "A"},
            {"id": "jieneng", "name": "全国大学生节能减排社会实践与科技竞赛",
             "aliases": ["节能减排社会实践与科技竞赛"],
             "organizer": "教育部高等教育司", "organizer_ok": ["教育部"],
             "site": "http://www.jienengjianpai.org", "list_type": "main", "official_grade": "A"},
            {"id": "culsc", "name": "全国大学生生命科学竞赛",
             "aliases": ["大学生生命科学竞赛"], "organizer": "全国大学生生命科学竞赛委员会",
             "organizer_ok": ["生命科学竞赛委员会"],
             "site": "http://www.culsc.cn", "list_type": "main", "official_grade": "A"},
            {"id": "chengtu", "name": "全国大学生先进成图技术与产品信息建模创新大赛",
             "aliases": ["先进成图技术与产品信息建模创新大赛"],
             "organizer": "中国图学学会", "organizer_ok": ["中国图学学会"],
             "site": "http://www.chengtudasai.com", "list_type": "main", "official_grade": "A"},
            {"id": "3chuang", "name": "全国大学生电子商务创新创意及创业挑战赛",
             "aliases": ["三创赛", "电子商务创新创意及创业挑战赛"],
             "organizer": "全国电子商务产教融合创新联盟",
             "organizer_ok": ["电子商务产教融合创新联盟"],
             "site": "https://www.3chuang.net", "list_type": "main", "official_grade": "A"},
            {"id": "mcm", "name": "美国大学生数学建模竞赛",
             "aliases": ["美国大学生数学建模竞赛", "MCM/ICM"],
             "organizer": "美国数学及其应用联合会", "organizer_ok": ["数学及其应用联合会"],
             "site": "https://www.contest.comap.com", "list_type": "observe", "official_grade": "B"},
        ],
    }
    CATALOG.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print("（已生成 stub 目录用于自测）\n")

reg.reload_catalog(str(CATALOG))

# (标题, 主办方, 期望类别, 期望含金量)
CASES = [
    # —— 假阳性组：赛氪上那批必须被打回 ——
    ("2026年第十六届APMCM亚太地区大学生数学建模竞赛",
     "中国国际科技促进会物联网工作委员会 等", "其他", "低"),
    ("第三届“中西挑战杯”大学生数学建模大赛",
     "中国西部研究与发展促进会教育工作委员会", "其他", "低"),
    ("第五届“数学周报”全国大学生数学建模大赛", "数学周报社", "其他", "低"),
    # 主办方字段是空的，只有标题里写着「数学周报」——靠标题里的媒体名也要打回
    ("第五届“数学周报”全国大学生数学建模大赛", "", "其他", "低"),
    ("2026年第十六届亚太地区大学生数学建模竞赛（塔里木大学报名入口）",
     "中国国际科技促进会物联网工作委员会、北京图象图形学学会", "其他", "低"),
    ("某某杯大学生数学建模大赛", "某某民营公司", "其他", "低"),
    # —— 非竞赛：考试/测评/证书一律剔除，绝不能算赛事 ——
    ("2026年高校学生数学建模能力测评考试", "工业和信息化部人才交流中心", "非竞赛", "低"),
    ("职业技能证书-数学建模考试入口", "", "非竞赛", "低"),
    ("全国大学生数学建模能力等级考试", "教育部高等教育司", "非竞赛", "低"),
    # —— 校赛：不是官方赛事 ——
    ("2026年中国矿业大学“博学杯”数学建模竞赛", "", "高校赛事", "中"),
    # —— 假阴性组：真正的主目录赛事必须被认出来 ——
    ("第十八届蓝桥杯全国大学生软件和信息技术大赛", "中国软件行业协会", "官方赛事", "高"),
    ("第二十届全国大学生节能减排社会实践与科技竞赛", "教育部高等教育司", "官方赛事", "高"),
    ("第十二届全国大学生生命科学竞赛（科学探究类）",
     "全国大学生生命科学竞赛委员会", "官方赛事", "高"),
    ("第二十届全国大学生先进成图技术与产品信息建模创新大赛", "中国图学学会", "官方赛事", "高"),
    ("第十七届全国大学生电子商务“创新、创意及创业”挑战赛",
     "全国电子商务产教融合创新联盟", "官方赛事", "高"),
    ("2027年中国大学生工程实践与创新能力大赛", "教育部工程训练教学指导委员会", "官方赛事", "高"),
    # —— 观察目录：中 ——
    ("2027年美国大学生数学建模竞赛", "美国数学及其应用联合会", "官方赛事", "中"),
    # —— 弱命中 + 公司主办：仍然要打回（防止"XX杯蓝桥杯"挂名）——
    ("某某杯蓝桥杯技能大赛", "某某教育科技有限公司", "其他", "低"),
]

# 睿抗的主办是「工业和信息化部人才交流中心」，而"人才交流中心"在反面词表里
# （为了挡挂名发证的野鸡赛）。这里验证"标题强证据"能把它救回来。
# 用 stub 目录时没有 raicom 条目，跳过这两条。
if "raicom" in ((reg.load_catalog() or {}).get("by_id") or {}):
    CASES += [
        ("睿抗机器人开发者大赛（RoboCom）CAIP信息技术创新赛道",
         "工业和信息化部人才交流中心", "官方赛事", "中"),
        ("RoboCom机器人开发者大赛", "工业和信息化部人才交流中心", "官方赛事", "中"),
    ]

print("%-4s %-52s %-8s %-8s %-8s %-8s" % ("", "赛事", "类别", "期望", "含金量", "期望"))
print("-" * 100)
fails = 0
for title, org, want_cat, want_pr in CASES:
    cat = reg.categorize(title, org, "saikr")
    pr = reg.prestige(title, org, "saikr", "")
    ok = (cat == want_cat) and (pr == want_pr)
    if not ok:
        fails += 1
    print("%-4s %-52s %-8s %-8s %-8s %-8s %s" % (
        "OK" if ok else "FAIL", title[:50], cat, want_cat, pr, want_pr, ""))

print("\n失败 %d / %d" % (fails, len(CASES)))

print("\n=== lookup 返回的目录条目 ===")
for t, o in [("第十八届蓝桥杯全国大学生软件和信息技术大赛", "中国软件行业协会"),
             ("某某杯大学生数学建模大赛", "某某民营公司")]:
    ev = reg.lookup(t, o)
    print("  %-46s -> %s" % (t[:44], (ev or {}).get("id") or "(未命中)"))

print("\n=== 截止口径识别 ===")
for txt in ["报名时间自即日起，至2026年11月19日24时",
            "校内选拔赛报名截止时间暂定于2026年11月13日",
            "被选拔竞赛作品申报书一般在2027年5月20日下午16：00进行网上提交",
            "比赛将于北京时间2027年1月29日-2月2日举行"]:
    print("  %-52s -> %s" % (txt[:50], reg.classify_deadline_kind(txt)))

print("\n=== 主办方权威度 ===")
for o in ["教育部高等教育司", "中国图学学会", "中国西部研究与发展促进会教育工作委员会",
          "数学周报社", "某某民营公司", "湖南省教育厅"]:
    print("  %-40s -> %s" % (o, reg.organizer_authority(o)))

print("\n=== 阶段（不再强行写报名中）===")
print("  无截止日期      ->", reg.stage_for(""))
print("  2027-01-15      ->", reg.stage_for("2027-01-15"))
print("  2026-10-31      ->", reg.stage_for("2026-10-31"))

sys.exit(0 if fails == 0 else 1)
