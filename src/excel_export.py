# -*- coding: utf-8 -*-
"""Excel 台账导出（纯标准库生成 .xlsx，无需 openpyxl）。

工作簿两张表：
  1. 比赛总览：类别/赛名/主办方/类型/开始/截止/阶段/奖金/来源/链接
     今日新增行红底红字，官方A类行"类别"单元格黄底
  2. 数据来源：各平台来源地址 + 更新说明
"""
from __future__ import annotations

import os
import zipfile
from datetime import datetime
from typing import Dict, Iterable, List, Set
from xml.sax.saxutils import escape

from .official import categorize, clean_text, normalize_comp_type, prestige
from .platforms import PLATFORM_NAMES, SOURCE_INFO

_HEADERS = ["类别", "含金量", "赛名", "主办方", "类型", "开始日期", "截止日期", "阶段", "奖金", "来源", "链接"]
_COL_WIDTHS = [12, 10, 42, 30, 14, 16, 16, 10, 14, 14, 48]

# 样式下标
_S_DEFAULT = 0
_S_HEADER = 1
_S_NEW = 2
_S_NEW_BOLD = 3
_S_OFFICIAL = 4
_S_RATING_RED = 5
_S_RATING_ORANGE = 6
_S_RATING_GREEN = 7

_RATING_STYLE = {"高": _S_RATING_RED, "中": _S_RATING_ORANGE, "低": _S_RATING_GREEN}


def export_excel(
    comps: List,
    new_keys: Set[str],
    path: str = "data/competitions.xlsx",
) -> str:
    """把比赛列表写成 xlsx。返回文件路径。"""
    rows = [
        [
            categorize(c.title, c.organizer, c.platform),
            prestige(c.title, c.organizer, c.platform, c.rating),
            clean_text(c.title),
            clean_text(c.organizer),
            normalize_comp_type(c.comp_type),
            c.enabled_date,
            c.deadline,
            c.status,
            c.reward,
            PLATFORM_NAMES.get(c.platform, c.platform),
            c.url,
        ]
        for c in comps
    ]
    new_rows: Set[int] = {i + 2 for i, c in enumerate(comps) if c.key in new_keys}
    official_rows: Set[int] = {
        i + 2 for i, c in enumerate(comps) if categorize(c.title, c.organizer, c.platform) == "官方A类"
    }
    meta = {
        "更新日期": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "总场次": len(comps),
        "今日新增": len(new_keys),
        "教育部A类": len(official_rows),
    }
    _write_xlsx(path, _HEADERS, rows, new_rows, official_rows, meta)
    return path


# --------------------------------------------------------------------------
# 纯标准库 xlsx 写入
# --------------------------------------------------------------------------

_XMLNS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XMLNS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XMLNS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _write_xlsx(path, headers, rows, new_rows, official_rows, meta) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    n_rows = len(rows) + 1
    sheet1 = _sheet1(headers, rows, new_rows, official_rows, n_rows)
    sheet2 = _sheet2(meta)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", _WORKBOOK)
        z.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml", sheet1)
        z.writestr("xl/worksheets/sheet2.xml", sheet2)


def _cell(ref: str, value: str, style: int) -> str:
    if style == _S_DEFAULT:
        s_attr = ""
    else:
        s_attr = f' s="{style}"'
    return (
        f'<c r="{ref}" t="inlineStr"{s_attr}><is><t>{escape(str(value))}</t></is></c>'
    )


def _sheet1(headers, rows, new_rows, official_rows, n_rows) -> str:
    col_defs = "".join(
        f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
        for i, w in enumerate(_COL_WIDTHS, start=1)
    )
    cols = f"<cols>{col_defs}</cols>"
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{_XMLNS_MAIN}" xmlns:r="{_XMLNS_REL}">',
        '<sheetViews><sheetView tabSelected="1" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>",
        cols,
        "<sheetData>",
    ]
    # 表头
    header_cells = "".join(
        _cell(f"{_col_name(i)}1", h, _S_HEADER) for i, h in enumerate(headers, start=1)
    )
    lines.append(f'<row r="1">{header_cells}</row>')
    # 数据
    for idx, row in enumerate(rows, start=2):
        cells = []
        for ci, v in enumerate(row, start=1):
            ref = f"{_col_name(ci)}{idx}"
            if idx in new_rows:
                style = _S_NEW_BOLD if ci == 3 else _S_NEW
            elif ci == 2:  # 含金量列：红/橙/绿
                style = _RATING_STYLE.get(str(v), _S_DEFAULT)
            elif idx in official_rows and ci == 1:
                style = _S_OFFICIAL
            else:
                style = _S_DEFAULT
            cells.append(_cell(ref, v, style))
        lines.append(f'<row r="{idx}">{"" .join(cells)}</row>')
    lines.append("</sheetData>")
    lines.append(f'<autoFilter ref="A1:{_col_name(len(headers))}{n_rows}"/>')
    lines.append("</worksheet>")
    return "".join(lines)


def _sheet2(meta) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{_XMLNS_MAIN}" xmlns:r="{_XMLNS_REL}">',
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>',
        "<sheetData>",
    ]
    r = 1
    lines.append(f'<row r="{r}">{_cell("A1", "说明", _S_HEADER)}{_cell("B1", "内容", _S_HEADER)}</row>')
    r += 1
    for k, v in meta.items():
        lines.append(f'<row r="{r}">{_cell(f"A{r}", k, _S_DEFAULT)}{_cell(f"B{r}", v, _S_DEFAULT)}</row>')
        r += 1
    r += 1
    lines.append(
        f'<row r="{r}">{_cell(f"A{r}", "平台", _S_HEADER)}{_cell(f"B{r}", "来源地址", _S_HEADER)}</row>'
    )
    r += 1
    for name, url in SOURCE_INFO.values():
        lines.append(
            f'<row r="{r}">{_cell(f"A{r}", name, _S_DEFAULT)}{_cell(f"B{r}", url, _S_DEFAULT)}</row>'
        )
        r += 1
    lines.append("</sheetData>")
    lines.append("</worksheet>")
    return "".join(lines)


def _col_name(i: int) -> str:
    s = ""
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Types xmlns="{_XMLNS_PKG}">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{_XMLNS_PKG}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<workbook xmlns="{_XMLNS_MAIN}" xmlns:r="{_XMLNS_REL}">'
    "<sheets>"
    '<sheet name="比赛总览" sheetId="1" r:id="rId1"/>'
    '<sheet name="数据来源" sheetId="2" r:id="rId2"/>'
    "</sheets>"
    "</workbook>"
)

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{_XMLNS_PKG}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<styleSheet xmlns="{_XMLNS_MAIN}">'
    '<fonts count="6">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '<font><color rgb="FF9C0006"/><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><color rgb="FF9C0006"/><sz val="11"/><name val="Calibri"/></font>'
    '<font><color rgb="FFE67E22"/><sz val="11"/><name val="Calibri"/></font>'
    '<font><color rgb="FF2ECC40"/><sz val="11"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="5">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFD9D9D9"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>'
    "</fills>"
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="8">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="0" fontId="3" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="0" fontId="0" fillId="4" borderId="0" xfId="0" applyFill="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)
