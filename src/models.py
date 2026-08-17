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
        return f"[{self.platform}] {self.title} ({self.organizer}) 截止:{self.deadline or '未知'}"
