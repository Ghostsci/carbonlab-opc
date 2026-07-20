"""Structured field extraction from production reports."""

from __future__ import annotations

import csv
import re


class ProductionReportExtractor:
    FIELD_KEYS = (
        "product_name",
        "period_start",
        "period_end",
        "production_output",
        "unit",
        "facility",
    )

    HEADER_ALIASES = {
        "产品": "product_name",
        "产品名称": "product_name",
        "品名": "product_name",
        "期间开始": "period_start",
        "开始日期": "period_start",
        "生产开始日期": "period_start",
        "期间结束": "period_end",
        "结束日期": "period_end",
        "生产结束日期": "period_end",
        "合格产量": "production_output",
        "生产产量": "production_output",
        "实际产量": "production_output",
        "产量": "production_output",
        "产出": "production_output",
        "单位": "unit",
        "计量单位": "unit",
        "所属工厂": "facility",
        "工厂": "facility",
        "生产工厂": "facility",
        "生产基地": "facility",
    }

    LABELS = frozenset(HEADER_ALIASES)

    PATTERNS = {
        "product_name": r"(?m)^[ \t]*(?:产品名称|产品|品名)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n,，]+)",
        "period_start": r"(?m)^[ \t]*(?:期间开始|开始日期|生产开始日期)[ \t]*(?:[：:][ \t]*|[ \t]+)(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
        "period_end": r"(?m)^[ \t]*(?:期间结束|结束日期|生产结束日期)[ \t]*(?:[：:][ \t]*|[ \t]+)(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
        "production_output": r"(?mi)^[ \t]*(?:合格产量|生产产量|实际产量|产量|产出)[ \t]*(?:[：:][ \t]*|[ \t]+)([+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:吨|千克|公斤|kg|t))?)",
        "unit": r"(?mi)^[ \t]*(?:单位|计量单位)[ \t]*(?:[：:][ \t]*|[ \t]+)(吨|千克|公斤|kg|t)[ \t]*$",
        "facility": r"(?m)^[ \t]*(?:所属工厂|生产工厂|生产基地|工厂)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n,，]+)",
    }

    _QUANTITY_PATTERN = re.compile(
        r"^[ \t]*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
        r"[ \t]*(吨|千克|公斤|kg|t)?[ \t]*$",
        flags=re.IGNORECASE,
    )

    def extract(self, text: str) -> dict[str, str]:
        normalized_text = self._join_label_value_lines(text)
        fields = {key: "" for key in self.FIELD_KEYS}
        fields.update(self._extract_delimited_row(normalized_text))

        for key, pattern in self.PATTERNS.items():
            if fields[key]:
                continue
            match = re.search(pattern, normalized_text)
            if not match:
                continue
            value = match.group(1).strip()
            if key == "production_output":
                quantity, inferred_unit = self._normalize_quantity(value)
                fields[key] = quantity
                if inferred_unit and not fields["unit"]:
                    fields["unit"] = inferred_unit
            else:
                fields[key] = self._normalize_missing(value)
        return fields

    def _extract_delimited_row(self, text: str) -> dict[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index in range(len(lines) - 1):
            header_line = lines[index]
            value_line = lines[index + 1]
            for delimiter in (",", "\t", "，"):
                if delimiter not in header_line or delimiter not in value_line:
                    continue
                headers = self._split_row(header_line, delimiter)
                values = self._split_row(value_line, delimiter)
                if len(headers) < 2 or len(values) < 2:
                    continue

                row_fields: dict[str, str] = {}
                inferred_unit = ""
                for header, value in zip(headers, values):
                    key = self.HEADER_ALIASES.get(self._normalize_header(header))
                    value = self._normalize_missing(value)
                    if not key or not value:
                        continue
                    if key == "production_output":
                        quantity, quantity_unit = self._normalize_quantity(value)
                        if quantity:
                            row_fields[key] = quantity
                            inferred_unit = quantity_unit
                    else:
                        row_fields[key] = value

                if inferred_unit and not row_fields.get("unit"):
                    row_fields["unit"] = inferred_unit
                if row_fields:
                    return row_fields
        return {}

    def _join_label_value_lines(self, text: str) -> str:
        lines = text.splitlines()
        normalized: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            label = line.strip().rstrip("：:").strip()
            if label in self.LABELS and index + 1 < len(lines):
                value = lines[index + 1].strip()
                next_label = value.rstrip("：:").strip()
                if value and next_label not in self.LABELS:
                    normalized.append(f"{label}：{value}")
                    index += 2
                    continue
            normalized.append(line)
            index += 1
        return "\n".join(normalized)

    def _split_row(self, line: str, delimiter: str) -> list[str]:
        try:
            return [
                cell.strip()
                for cell in next(csv.reader([line], delimiter=delimiter, strict=True))
            ]
        except csv.Error:
            return []

    def _normalize_header(self, header: str) -> str:
        normalized = re.sub(r"\s+", "", header.strip())
        normalized = normalized.replace("（", "(").replace("）", ")")
        return re.sub(r"\([^)]*\)$", "", normalized)

    def _normalize_quantity(self, value: str) -> tuple[str, str]:
        match = self._QUANTITY_PATTERN.fullmatch(value)
        if not match:
            return "", ""
        return match.group(1).replace(",", ""), (match.group(2) or "")

    def _normalize_missing(self, value: str) -> str:
        normalized = value.strip()
        if normalized.casefold() in {"未提供", "无", "n/a", "na", "-", "--"}:
            return ""
        return normalized
