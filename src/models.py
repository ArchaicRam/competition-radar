# -*- coding: utf-8 -*-
"""比赛数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Competition:
    """一场比赛/竞赛的标准化记录。

    key 是全库唯一键，形如 ``kaggle:competitionId`` 或 ``tianchi:xx``，
    用于增量去重。
    """

    key: str
    title: str
    platform: str          # tianchi / datafountain / nowcoder / xfyun / kaggle / saikr
    organizer: str = ""    # 主办方/企业
    url: str = ""
    deadline: str = ""     # 报名/提交截止，ISO 日期优先，无则留空或写人类可读文本
    reward: str = ""       # 奖金/奖品
    comp_type: str = ""    # 赛道类型：算法/AI/开发/数据/安全/硬件/综合
    status: str = ""       # 报名中/进行中/已结束
    enabled_date: str = "" # 开始日期
    rating: str = ""       # 含金量：高/中/低（空则按规则推算）
    # —— 口径与证据（均有默认值，向后兼容；旧 state.json 可直接读）——
    deadline_kind: str = ""   # 报名截止 / 校内报名截止 / 作品提交截止 / 比赛结束 / 未公布
    deadline_alt: str = ""    # 同通知里的其它口径截止，如 "2026-12-18(报名截止);2027-04-26(作品提交截止)"
    evidence_url: str = ""    # 官方通知原文地址（区别于报名入口 url）
    evidence_quote: str = ""  # 原文引句，如 "报名时间自即日起，至2026年11月19日24时"
    confidence: str = ""      # A=主办方官网原文 / B=高校教务处转发 / C=聚合站线索
    catalog_id: str = ""      # 权威目录里的赛事 id（用于把子赛道折叠到父赛事）
    verified_at: str = ""     # 核验日期 YYYY-MM-DD
    detected_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Competition":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)

    def __str__(self) -> str:
        dl = self.deadline or "未知"
        if self.deadline_kind:
            dl = f"{dl}({self.deadline_kind})"
        return f"[{self.platform}] {self.title} ({self.organizer}) 截止:{dl}"
