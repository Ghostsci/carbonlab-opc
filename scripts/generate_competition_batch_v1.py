#!/usr/bin/env python3
"""Generate a deterministic, explicitly synthetic electricity-bill batch.

The files model one billing document per facility and month.  They are not
copies of customer documents and must never be represented as real invoices.
"""

from __future__ import annotations

import csv
from decimal import Decimal
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "validation" / "competition_batch_v1"
POSITIVE_DIR = DATASET_DIR / "positive"
NEGATIVE_DIR = DATASET_DIR / "negative"
PUBLIC_ZIP = ROOT / "frontend" / "public" / "demo" / "carbonlab-competition-batch-v1.zip"
DEMO_FACTOR = Decimal("0.5")  # kgCO2e / kWh, synthetic and non-regulatory.


FACILITIES = (
    {
        "code": "HR",
        "name": "一号热轧生产装置（合成）",
        "customer_number": "DEMO-HR-2601",
        "opening": Decimal("184200000"),
        "monthly_kwh": (Decimal("2480000"), Decimal("2360000"), Decimal("2610000")),
        "prices": (Decimal("0.7180"), Decimal("0.7040"), Decimal("0.7310")),
    },
    {
        "code": "CR",
        "name": "二号冷轧生产装置（合成）",
        "customer_number": "DEMO-CR-2601",
        "opening": Decimal("96200000"),
        "monthly_kwh": (Decimal("1520000"), Decimal("1450000"), Decimal("1630000")),
        "prices": (Decimal("0.7220"), Decimal("0.7090"), Decimal("0.7360")),
    },
    {
        "code": "PA",
        "name": "公辅动力中心（合成）",
        "customer_number": "DEMO-PA-2601",
        "opening": Decimal("43800000"),
        "monthly_kwh": (Decimal("830000"), Decimal("790000"), Decimal("910000")),
        "prices": (Decimal("0.7160"), Decimal("0.7010"), Decimal("0.7280")),
    },
    {
        "code": "AS",
        "name": "空压站（合成）",
        "customer_number": "DEMO-AS-2601",
        "opening": Decimal("21600000"),
        "monthly_kwh": (Decimal("310000"), Decimal("295000"), Decimal("328000")),
        "prices": (Decimal("0.7190"), Decimal("0.7060"), Decimal("0.7330")),
    },
)


HEADER_VARIANTS = (
    (
        "供电公司",
        "户名",
        "户号",
        "账单月份",
        "本期用电量(kWh)",
        "电价",
        "电费合计",
        "上期读数",
        "本期读数",
        "所属工厂",
        "数据标识",
    ),
    (
        "供电单位",
        "用户名称",
        "用户编号",
        "账期",
        "有功电量",
        "单价",
        "应收电费",
        "期初读数",
        "期末读数",
        "工厂",
        "数据标识",
    ),
    (
        "电力公司",
        "客户名称",
        "客户编号",
        "用电期间",
        "总电量",
        "电价",
        "合计金额",
        "上次读数",
        "本次读数",
        "用电地址",
        "数据标识",
    ),
)


def _decimal_text(value: Decimal, places: str = "0.01") -> str:
    return format(value.quantize(Decimal(places)), "f")


def _period_text(month: int, variant: int) -> str:
    if variant == 0:
        return f"2026年{month:02d}月"
    if variant == 1:
        return f"2026-{month:02d}"
    month_ends = {1: 31, 2: 28, 3: 31}
    return f"2026-{month:02d}-01 至 2026-{month:02d}-{month_ends[month]}"


def _write_csv(path: Path, headers: tuple[str, ...], row: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow(row)


def generate() -> dict[str, object]:
    POSITIVE_DIR.mkdir(parents=True, exist_ok=True)
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    positive_cases: list[dict[str, object]] = []

    for facility_index, facility in enumerate(FACILITIES):
        meter_start = facility["opening"]
        for month_index, (quantity, price) in enumerate(
            zip(facility["monthly_kwh"], facility["prices"]),
            start=1,
        ):
            variant = (facility_index + month_index - 1) % len(HEADER_VARIANTS)
            headers = HEADER_VARIANTS[variant]
            period = _period_text(month_index, variant)
            meter_end = meter_start + quantity
            amount = quantity * price
            filename = f"DEMO_ONLY_2026{month_index:02d}_{facility['code']}_electricity_bill.csv"
            row = [
                "DEMO ONLY｜合成供电公司（非真实主体）",
                "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
                str(facility["customer_number"]),
                period,
                f"{quantity:,.0f} kWh",
                f"{price:.4f} 元/kWh",
                f"{amount:,.2f} 元",
                f"{meter_start:,.0f} kWh",
                f"{meter_end:,.0f} kWh",
                str(facility["name"]),
                "DEMO ONLY / SYNTHETIC / NOT FOR REPORTING",
            ]
            _write_csv(POSITIVE_DIR / filename, headers, row)
            positive_cases.append(
                {
                    "filename": f"positive/{filename}",
                    "facility": facility["name"],
                    "period": period,
                    "electricity_kwh": format(quantity, "f"),
                    "unit_price_cny_per_kwh": format(price, "f"),
                    "total_amount_cny": _decimal_text(amount),
                    "meter_reading_start_kwh": format(meter_start, "f"),
                    "meter_reading_end_kwh": format(meter_end, "f"),
                    "expected_tco2e_at_demo_factor": _decimal_text(
                        quantity * DEMO_FACTOR / Decimal("1000"),
                        "0.000000000001",
                    ),
                }
            )
            meter_start = meter_end

    _write_csv(
        NEGATIVE_DIR / "NEG_01_missing_quantity.csv",
        HEADER_VARIANTS[0],
        [
            "DEMO ONLY｜合成供电公司（非真实主体）",
            "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
            "DEMO-NEG-01",
            "2026年01月",
            "",
            "0.7180 元/kWh",
            "0.00 元",
            "100000 kWh",
            "100000 kWh",
            "缺失用电量测试工厂（合成）",
            "DEMO ONLY / NEGATIVE TEST",
        ],
    )
    _write_csv(
        NEGATIVE_DIR / "NEG_02_negative_quantity.csv",
        HEADER_VARIANTS[1],
        [
            "DEMO ONLY｜合成供电公司（非真实主体）",
            "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
            "DEMO-NEG-02",
            "2026-02",
            "-5000 kWh",
            "0.7090 元/kWh",
            "-3545.00 元",
            "100000 kWh",
            "95000 kWh",
            "负数测试工厂（合成）",
            "DEMO ONLY / NEGATIVE TEST",
        ],
    )
    _write_csv(
        NEGATIVE_DIR / "NEG_03_wrong_unit_mwh.csv",
        HEADER_VARIANTS[2],
        [
            "DEMO ONLY｜合成供电公司（非真实主体）",
            "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
            "DEMO-NEG-03",
            "2026-03-01 至 2026-03-31",
            "2500 MWh",
            "0.7310 元/kWh",
            "1827500.00 元",
            "100000 kWh",
            "2600000 kWh",
            "错误单位测试工厂（合成）",
            "DEMO ONLY / NEGATIVE TEST",
        ],
    )

    multi_path = NEGATIVE_DIR / "NEG_04_multiple_billing_records.csv"
    with multi_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER_VARIANTS[0])
        for month, quantity in ((1, 100000), (2, 110000), (3, 120000)):
            writer.writerow(
                [
                    "DEMO ONLY｜合成供电公司（非真实主体）",
                    "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
                    "DEMO-NEG-04",
                    f"2026年{month:02d}月",
                    f"{quantity} kWh",
                    "0.7200 元/kWh",
                    f"{quantity * Decimal('0.72'):.2f} 元",
                    "0 kWh",
                    f"{quantity} kWh",
                    "多记录台账测试工厂（合成）",
                    "DEMO ONLY / MULTI-RECORD NEGATIVE TEST",
                ]
            )

    manifest: dict[str, object] = {
        "dataset_id": "carbonlab-competition-batch-v1",
        "generated_for": "OPC competition controlled product validation",
        "synthetic": True,
        "contains_real_customer_data": False,
        "record_model": "one billing document per facility per month",
        "demo_factor": {"value": "0.5", "unit": "kgCO2e/kWh"},
        "positive_cases": positive_cases,
        "negative_cases": [
            {
                "filename": "negative/NEG_01_missing_quantity.csv",
                "expected": "quality gate rejects missing electricity quantity",
            },
            {
                "filename": "negative/NEG_02_negative_quantity.csv",
                "expected": "quality gate rejects non-positive electricity quantity",
            },
            {
                "filename": "negative/NEG_03_wrong_unit_mwh.csv",
                "expected": "extractor abstains because MWh conversion is not approved in this path",
            },
            {
                "filename": "negative/NEG_04_multiple_billing_records.csv",
                "expected": "extractor rejects multiple billing records instead of silently taking row one",
            },
        ],
    }
    manifest_path = DATASET_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PUBLIC_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PUBLIC_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DATASET_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DATASET_DIR))
    return manifest


if __name__ == "__main__":
    generated = generate()
    print(
        f"generated {len(generated['positive_cases'])} positive and "
        f"{len(generated['negative_cases'])} negative cases under {DATASET_DIR}"
    )
