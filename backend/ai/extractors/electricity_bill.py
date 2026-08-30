"""Electricity bill field extractor."""

from __future__ import annotations

import csv
import re


class MultipleElectricityRecordsError(ValueError):
    """Raised when one upload contains several independent billing periods."""


class ElectricityBillExtractor:
    FIELD_KEYS = (
        "supplier_name",
        "customer_name",
        "customer_number",
        "period",
        "electricity_kwh",
        "unit_price",
        "total_amount",
        "meter_reading_start",
        "meter_reading_end",
        "facility",
    )

    HEADER_ALIASES = {
        "供应商": "supplier_name",
        "供电单位": "supplier_name",
        "供电公司": "supplier_name",
        "电力公司": "supplier_name",
        "用户名称": "customer_name",
        "客户名称": "customer_name",
        "户名": "customer_name",
        "户号": "customer_number",
        "用户编号": "customer_number",
        "客户编号": "customer_number",
        "账单月份": "period",
        "账单月": "period",
        "账期": "period",
        "用电期": "period",
        "用电期间": "period",
        "计费时段": "period",
        "计费周期": "period",
        "抄表周期": "period",
        "用电量": "electricity_kwh",
        "本期用电量": "electricity_kwh",
        "有功电量": "electricity_kwh",
        "总电量": "electricity_kwh",
        "电价": "unit_price",
        "单价": "unit_price",
        "金额": "total_amount",
        "电费合计": "total_amount",
        "应收电费": "total_amount",
        "合计金额": "total_amount",
        "应付金额": "total_amount",
        "上期读数": "meter_reading_start",
        "上次读数": "meter_reading_start",
        "上期示数": "meter_reading_start",
        "期初读数": "meter_reading_start",
        "本期读数": "meter_reading_end",
        "本次读数": "meter_reading_end",
        "本期示数": "meter_reading_end",
        "期末读数": "meter_reading_end",
        "所属工厂": "facility",
        "工厂": "facility",
        "用电地址": "facility",
    }

    LABELS = frozenset(HEADER_ALIASES)

    PATTERNS = {
        "supplier_name": r"(?m)^[ \t]*(?:供电单位|供电公司|电力公司|供应商)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n]+)",
        "customer_name": r"(?m)^[ \t]*(?:户名|用户名称|客户名称)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n]+)",
        "customer_number": r"(?m)^[ \t]*(?:户号|用户编号|客户编号)[ \t]*(?:[：:][ \t]*|[ \t]+)([A-Za-z0-9-]{6,30})",
        "period": r"(?m)^[ \t]*(?:账单月份|账单月|账期|用电期间?|计费时段|计费周期|抄表周期)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n,，]+)",
        "electricity_kwh": r"(?mi)^[ \t]*(?:本期用电量|用电量|有功电量|总电量)[ \t]*(?:[：:][ \t]*|[ \t]+)([¥￥]?[ \t]*[+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:kwh|kw·h|千瓦时))?)",
        "unit_price": r"(?mi)^[ \t]*(?:电价|单价)[ \t]*(?:[：:][ \t]*|[ \t]+)([¥￥]?[ \t]*[+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:元/(?:kwh|kw·h)|元))?)",
        "total_amount": r"(?mi)^[ \t]*(?:电费合计|应收电费|合计金额|应付金额|金额)[ \t]*(?:[：:][ \t]*|[ \t]+)([¥￥]?[ \t]*[+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:元|cny))?)",
        "meter_reading_start": r"(?mi)^[ \t]*(?:上次读数|上期读数|上期示数|期初读数)[ \t]*(?:[：:][ \t]*|[ \t]+)([+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:kwh|kw·h|千瓦时))?)",
        "meter_reading_end": r"(?mi)^[ \t]*(?:本次读数|本期读数|本期示数|期末读数)[ \t]*(?:[：:][ \t]*|[ \t]+)([+-]?[\d,]+(?:\.\d+)?(?:[ \t]*(?:kwh|kw·h|千瓦时))?)",
        "facility": r"(?m)^[ \t]*(?:所属工厂|用电地址|工厂)[ \t]*(?:[：:][ \t]*|[ \t]+)([^\n,，]+)",
    }

    NUMERIC_FIELDS = frozenset(
        {
            "electricity_kwh",
            "unit_price",
            "total_amount",
            "meter_reading_start",
            "meter_reading_end",
        }
    )

    _NUMBER_WITH_GROUPING = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    _NUMERIC_PATTERNS = {
        "electricity_kwh": re.compile(
            rf"^[ \t]*({_NUMBER_WITH_GROUPING})[ \t]*(?:kwh|kw·h|千瓦时)?[ \t]*$",
            flags=re.IGNORECASE,
        ),
        "unit_price": re.compile(
            rf"^[ \t]*[¥￥]?[ \t]*({_NUMBER_WITH_GROUPING})[ \t]*(?:元/(?:kwh|kw·h)|元)?[ \t]*$",
            flags=re.IGNORECASE,
        ),
        "total_amount": re.compile(
            rf"^[ \t]*[¥￥]?[ \t]*({_NUMBER_WITH_GROUPING})[ \t]*(?:元|cny)?[ \t]*$",
            flags=re.IGNORECASE,
        ),
        "meter_reading_start": re.compile(
            rf"^[ \t]*({_NUMBER_WITH_GROUPING})[ \t]*(?:kwh|kw·h|千瓦时)?[ \t]*$",
            flags=re.IGNORECASE,
        ),
        "meter_reading_end": re.compile(
            rf"^[ \t]*({_NUMBER_WITH_GROUPING})[ \t]*(?:kwh|kw·h|千瓦时)?[ \t]*$",
            flags=re.IGNORECASE,
        ),
    }

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
            fields[key] = (
                self._normalize_numeric_value(key, value)
                if key in self.NUMERIC_FIELDS
                else value
            )

        if not fields["supplier_name"]:
            supplier = re.search(
                r"(?m)^[ \t]*([^\n]{2,60}(?:电力公司|供电公司|供电局)[^\n]*)$",
                normalized_text,
            )
            if supplier:
                fields["supplier_name"] = supplier.group(1).strip()
        return fields

    def _extract_delimited_row(self, text: str) -> dict[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index in range(len(lines) - 1):
            header_line = lines[index]
            for delimiter in (",", "\t", "，"):
                if delimiter not in header_line:
                    continue
                headers = self._split_row(header_line, delimiter)
                header_keys = [
                    self.HEADER_ALIASES.get(self._normalize_header(header))
                    for header in headers
                ]
                if len(headers) < 2 or sum(key is not None for key in header_keys) < 2:
                    continue

                record_rows: list[list[str]] = []
                for value_line in lines[index + 1 :]:
                    if delimiter not in value_line:
                        break
                    values = self._split_row(value_line, delimiter)
                    if len(values) != len(headers):
                        break
                    populated_recognized = sum(
                        bool(value.strip())
                        for key, value in zip(header_keys, values)
                        if key is not None
                    )
                    if populated_recognized < 2:
                        break
                    record_rows.append(values)

                if len(record_rows) > 1:
                    raise MultipleElectricityRecordsError(
                        "Multiple billing records detected; upload one billing period per document."
                    )
                if not record_rows:
                    continue
                values = record_rows[0]

                row_fields: dict[str, str] = {}
                for key, value in zip(header_keys, values):
                    value = value.strip()
                    if not key or not value:
                        continue
                    if key in self.NUMERIC_FIELDS:
                        if not self._normalize_numeric_value(key, value):
                            continue
                    row_fields[key] = value
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

    def _normalize_numeric_value(self, key: str, value: str) -> str:
        match = self._NUMERIC_PATTERNS[key].fullmatch(value)
        return match.group(1).replace(",", "") if match else ""
