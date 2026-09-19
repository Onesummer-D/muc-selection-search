"""导出服务：当前查询结果 → CSV / XLSX（固定四个工作表）。

规则（接口字典 6.1 + 附录 G G9）：
- 只导出当前角色可见的记录；游客导出不含姓名、头像、原图、二维码、联系方式、
  会议入口、本机路径和需要 CAS 登录的来源 URL。
- CSV 为扁平公开字段；XLSX 固定四个工作表：搜索结果、字段证据、来源文章、导出说明。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from ..domain.models import Evidence
from ..domain.presenter import role_label

RESULT_COLUMNS = (
    "记录编号", "届别", "年级", "学历", "学院", "专业", "城市", "岗位/单位",
    "复核状态", "发布状态", "来源标题", "发布日期",
)

PRIVATE_MARK = "（内部字段不导出）"


def _rows(records: list[dict], include_url: bool) -> tuple[tuple[str, ...], list[tuple]]:
    columns = RESULT_COLUMNS + ("来源链接",) if include_url else RESULT_COLUMNS
    rows = []
    for item in records:
        fields = item["fields"]
        source = item.get("source") or {}
        row = [
            item["record_key"],
            fields.get("cohort"), fields.get("grade"), fields.get("education"),
            fields.get("college"), fields.get("major"), fields.get("city"),
            fields.get("position_or_unit"),
            item["review_status"], item["visibility"],
            source.get("title"),
            (source.get("published_at") or "")[:10],
        ]
        if include_url:
            row.append(source.get("url"))
        rows.append(tuple(row))
    return columns, rows


def to_csv(records: list[dict], role: str) -> tuple[bytes, str]:
    columns, rows = _rows(records, include_url=(role != "guest"))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    data = b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")  # BOM 便于 Excel 识别
    return data, "text/csv"  # Flask 会自动补 charset=utf-8


def to_xlsx(records: list[dict], evidence_map: dict[str, list[Evidence]],
            role: str, query_plan: dict) -> tuple[bytes, str]:
    from openpyxl import Workbook

    include_url = role != "guest"
    columns, rows = _rows(records, include_url=include_url)
    wb = Workbook()

    ws = wb.active
    ws.title = "搜索结果"
    ws.append(list(columns))
    for row in rows:
        ws.append(list(row))

    ws2 = wb.create_sheet("字段证据")
    ws2.append(["记录编号", "字段", "字段值", "证据文本", "抽取方式", "证据位置bbox"])
    for item in records:
        fields = item["fields"]
        for ev in evidence_map.get(item["record_key"], []):
            ws2.append([
                item["record_key"], ev.field, fields.get(ev.field), ev.text,
                ev.method,
                ",".join(str(c) for c in ev.bbox) if ev.bbox else None,
            ])

    ws3 = wb.create_sheet("来源文章")
    article_columns = ["notice_id", "标题", "发布日期", "内容类型"]
    if include_url:
        article_columns.append("来源链接")
    ws3.append(article_columns)
    seen: set[str] = set()
    for item in records:
        source = item.get("source") or {}
        notice_id = item["notice_id"]
        if notice_id in seen:
            continue
        seen.add(notice_id)
        row = [notice_id, source.get("title"),
               (source.get("published_at") or "")[:10], source.get("content_type")]
        if include_url:
            row.append(source.get("url"))
        ws3.append(row)

    ws4 = wb.create_sheet("导出说明")
    notes = [
        ["导出时间", datetime.now().astimezone().isoformat(timespec="seconds")],
        ["导出角色", role_label(role)],
        ["查询条件", str(query_plan)],
        ["记录行数", len(records)],
        ["来源文章数", len(seen)],
        ["脱敏声明", "本导出仅含当前角色可见的公开扁平字段，不含姓名、头像、二维码、"
                    "联系方式、会议入口、原始海报与本机路径；受限来源链接仅对登录角色导出。"],
        ["字段级证据", "见「字段证据」工作表；证据缺失字段显示为空（未提供），不推测补全。"],
    ]
    for row in notes:
        ws4.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def filename(ext: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"xuandiaoyan_export_{stamp}.{ext}"
