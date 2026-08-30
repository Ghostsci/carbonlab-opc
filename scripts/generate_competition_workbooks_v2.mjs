#!/usr/bin/env node

/**
 * Generate deterministic, explicitly synthetic electricity workbooks.
 *
 * Each workbook represents one facility-month evidence document. It contains
 * one auditable billing summary plus exactly 50 sub-meter detail records. The
 * detail rows reconcile exactly to the summary quantity. No real customer
 * identity, meter number, tariff, invoice, or personal data is used.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "..");
const DATASET_DIR = path.join(ROOT, "validation", "competition_batch_v2");
const POSITIVE_DIR = path.join(DATASET_DIR, "positive");
const PREVIEW_DIR = "/tmp/carbonlab-competition-batch-v2-previews";

const FACILITIES = [
  {
    code: "HR",
    name: "一号热轧生产装置（合成）",
    customerNumber: "DEMO-HR-2601",
    opening: 184200000,
    monthlyKwh: [2480000, 2360000, 2610000],
    prices: [0.7180, 0.7040, 0.7310],
  },
  {
    code: "CR",
    name: "二号冷轧生产装置（合成）",
    customerNumber: "DEMO-CR-2601",
    opening: 96200000,
    monthlyKwh: [1520000, 1450000, 1630000],
    prices: [0.7220, 0.7090, 0.7360],
  },
  {
    code: "PA",
    name: "公辅动力中心（合成）",
    customerNumber: "DEMO-PA-2601",
    opening: 43800000,
    monthlyKwh: [830000, 790000, 910000],
    prices: [0.7160, 0.7010, 0.7280],
  },
  {
    code: "AS",
    name: "空压站（合成）",
    customerNumber: "DEMO-AS-2601",
    opening: 21600000,
    monthlyKwh: [310000, 295000, 328000],
    prices: [0.7190, 0.7060, 0.7330],
  },
];

const COLORS = {
  navy: "#12345B",
  blue: "#2563EB",
  cyan: "#16B7A7",
  paleBlue: "#EAF2FF",
  paleGreen: "#E9F8F2",
  paleAmber: "#FFF7E7",
  text: "#17233B",
  muted: "#64748B",
  border: "#D9E2F0",
  white: "#FFFFFF",
};

function daysInMonth(month) {
  return new Date(2026, month, 0).getDate();
}

function periodText(month) {
  const end = String(daysInMonth(month)).padStart(2, "0");
  return `2026-${String(month).padStart(2, "0")}-01 至 2026-${String(month).padStart(2, "0")}-${end}`;
}

function allocateIntegerTotal(total, count, seed) {
  const weights = Array.from({ length: count }, (_, index) =>
    80 + ((index * 17 + seed * 13) % 41),
  );
  const weightTotal = weights.reduce((sum, value) => sum + value, 0);
  const allocations = weights.map((weight) => Math.floor((total * weight) / weightTotal));
  let remainder = total - allocations.reduce((sum, value) => sum + value, 0);
  for (let index = 0; remainder > 0; index = (index + 1) % count) {
    allocations[index] += 1;
    remainder -= 1;
  }
  return allocations;
}

function makeDetailRows({ facility, facilityIndex, month, quantity, meterStart }) {
  const allocations = allocateIntegerTotal(quantity, 50, facilityIndex * 10 + month);
  const rows = [];
  let reading = meterStart;
  for (let index = 0; index < allocations.length; index += 1) {
    const usage = allocations[index];
    const nextReading = reading + usage;
    const day = 1 + ((index * 7 + facilityIndex * 3 + month) % daysInMonth(month));
    const date = new Date(Date.UTC(2026, month - 1, day));
    rows.push([
      index + 1,
      `${facility.code}-${String(month).padStart(2, "0")}-P${String(index + 1).padStart(3, "0")}`,
      date,
      ["白班", "中班", "夜班"][index % 3],
      facility.name,
      reading,
      nextReading,
      1,
      null,
      index % 17 === 0 ? "复核通过" : "正常",
      "智能电表导出（合成）",
      "DEMO ONLY / SYNTHETIC",
    ]);
    reading = nextReading;
  }
  return rows;
}

function styleTitle(sheet, rangeAddress, title, subtitleAddress, subtitle) {
  sheet.mergeCells(rangeAddress);
  const titleRange = sheet.getRange(rangeAddress);
  titleRange.values = [[title]];
  titleRange.format.fill = COLORS.navy;
  titleRange.format.font = { bold: true, color: COLORS.white, size: 18 };
  titleRange.format.rowHeight = 34;
  titleRange.format.verticalAlignment = "center";

  sheet.mergeCells(subtitleAddress);
  const subtitleRange = sheet.getRange(subtitleAddress);
  subtitleRange.values = [[subtitle]];
  subtitleRange.format.fill = COLORS.paleBlue;
  subtitleRange.format.font = { color: COLORS.muted, italic: true, size: 10 };
  subtitleRange.format.wrapText = true;
  subtitleRange.format.rowHeight = 28;
  subtitleRange.format.verticalAlignment = "center";
}

function styleHeader(range) {
  range.format.fill = COLORS.blue;
  range.format.font = { bold: true, color: COLORS.white, size: 10 };
  range.format.horizontalAlignment = "center";
  range.format.verticalAlignment = "center";
  range.format.wrapText = true;
  range.format.rowHeight = 28;
  range.format.borders = { preset: "all", style: "thin", color: COLORS.border };
}

function createWorkbook({ facility, facilityIndex, month, quantity, price, meterStart }) {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("账单摘要");
  const detail = workbook.worksheets.add("50条用电明细");
  const notes = workbook.worksheets.add("数据说明");
  const period = periodText(month);
  const amount = Math.round(quantity * price * 100) / 100;
  const meterEnd = meterStart + quantity;
  const detailRows = makeDetailRows({
    facility,
    facilityIndex,
    month,
    quantity,
    meterStart,
  });
  const detailQuantity = detailRows.reduce(
    (sum, row) => sum + (Number(row[6]) - Number(row[5])) * Number(row[7]),
    0,
  );
  if (
    detailRows.length !== 50
    || detailQuantity !== quantity
    || Number(detailRows.at(-1)[6]) !== meterEnd
  ) {
    throw new Error(`${facility.code}-${month}: generated detail rows do not reconcile`);
  }

  summary.showGridLines = false;
  styleTitle(
    summary,
    "A1:K1",
    "DEMO ONLY｜合成工商业电费账单",
    "A2:K2",
    "用于零碳云受控演示：本页是一条月度汇总，第二页包含50条可追溯用电明细；不代表真实客户或监管数据。",
  );
  const summaryHeaders = [[
    "供电公司",
    "户名",
    "户号",
    "账单月份",
    "本期用电量(kWh)",
    "电价(元/kWh)",
    "电费合计(元)",
    "上期读数(kWh)",
    "本期读数(kWh)",
    "所属工厂",
    "数据标识",
  ]];
  summary.getRange("A4:K4").values = summaryHeaders;
  styleHeader(summary.getRange("A4:K4"));
  summary.getRange("A5:K5").values = [[
    "DEMO ONLY｜合成供电公司（非真实主体）",
    "DEMO ONLY｜华盛钢铁演示企业（非真实客户）",
    facility.customerNumber,
    period,
    quantity,
    price,
    amount,
    meterStart,
    meterEnd,
    facility.name,
    "DEMO ONLY / SYNTHETIC / NOT FOR REPORTING",
  ]];
  summary.getRange("A5:K5").format.fill = COLORS.white;
  summary.getRange("A5:K5").format.font = { color: COLORS.text, size: 10 };
  summary.getRange("A5:K5").format.wrapText = true;
  summary.getRange("A5:K5").format.verticalAlignment = "center";
  summary.getRange("A5:K5").format.rowHeight = 42;
  summary.getRange("A5:K5").format.borders = {
    preset: "all",
    style: "thin",
    color: COLORS.border,
  };
  summary.getRange("E5").format.numberFormat = "#,##0";
  summary.getRange("F5").format.numberFormat = "0.0000";
  summary.getRange("G5:I5").format.numberFormat = "#,##0.00";

  summary.getRange("A8:B8").values = [["核对项目", "结果"]];
  styleHeader(summary.getRange("A8:B8"));
  summary.getRange("A9:A12").values = [["摘要电量(kWh)"], ["50条明细合计(kWh)"], ["差额(kWh)"], ["一致性校验"]];
  summary.getRange("B9").values = [[quantity]];
  summary.getRange("B10").formulas = [["=SUM('50条用电明细'!I5:I54)"]];
  summary.getRange("B11").formulas = [["=B9-B10"]];
  summary.getRange("B12").formulas = [["=IF(B11=0,\"通过\",\"异常\")"]];
  summary.getRange("A9:B12").format.borders = {
    preset: "all",
    style: "thin",
    color: COLORS.border,
  };
  summary.getRange("A9:A12").format.fill = COLORS.paleBlue;
  summary.getRange("A9:A12").format.font = { bold: true, color: COLORS.text };
  summary.getRange("B9:B11").format.numberFormat = "#,##0";
  summary.getRange("B12").format.fill = COLORS.paleGreen;
  summary.getRange("B12").format.font = { bold: true, color: "#087A5B" };

  summary.mergeCells("A15:K17");
  summary.getRange("A15:K17").values = [[
    "真实性边界：字段结构与数值关系按常见工商业电费资料模拟；所有主体、户号、读数、电价和金额均为合成值。月度汇总与50条明细严格勾稽，但未使用任何真实企业账单，不得用于申报、核查、报价或业务决策。",
  ]];
  summary.getRange("A15:K17").format.fill = COLORS.paleAmber;
  summary.getRange("A15:K17").format.font = { color: "#8A5A00", size: 10 };
  summary.getRange("A15:K17").format.wrapText = true;
  summary.getRange("A15:K17").format.verticalAlignment = "center";
  summary.getRange("A15:K17").format.borders = {
    preset: "outside",
    style: "thin",
    color: "#F2C46D",
  };
  summary.freezePanes.freezeRows(4);
  summary.getRange("A:K").format.columnWidth = 15;
  summary.getRange("A:A").format.columnWidth = 23;
  summary.getRange("B:B").format.columnWidth = 25;
  summary.getRange("D:D").format.columnWidth = 24;
  summary.getRange("J:J").format.columnWidth = 24;
  summary.getRange("K:K").format.columnWidth = 32;

  detail.showGridLines = false;
  styleTitle(
    detail,
    "A1:L1",
    `${facility.name}｜${period}｜50条用电明细`,
    "A2:L2",
    "每行代表一个合成计量点/班次读数；第55行合计必须与账单摘要完全一致。",
  );
  const detailHeaders = [[
    "序号",
    "计量点编号",
    "采集日期",
    "班次",
    "生产区域",
    "起始读数(kWh)",
    "结束读数(kWh)",
    "倍率",
    "用电量(kWh)",
    "数据状态",
    "数据来源",
    "数据标识",
  ]];
  detail.getRange("A4:L4").values = detailHeaders;
  styleHeader(detail.getRange("A4:L4"));
  detail.getRange("A5:L54").values = detailRows;
  detail.getRange("I5").formulas = [["=(G5-F5)*H5"]];
  detail.getRange("I5:I54").fillDown();
  detail.getRange("A5:L54").format.font = { color: COLORS.text, size: 9 };
  detail.getRange("A5:L54").format.borders = {
    insideHorizontal: { style: "thin", color: "#E8EEF7" },
  };
  detail.getRange("A5:A54").format.horizontalAlignment = "center";
  detail.getRange("C5:D54").format.horizontalAlignment = "center";
  detail.getRange("H5:H54").format.horizontalAlignment = "center";
  detail.getRange("J5:J54").format.horizontalAlignment = "center";
  detail.getRange("C5:C54").format.numberFormat = "yyyy-mm-dd";
  detail.getRange("F5:I54").format.numberFormat = "#,##0";
  detail.getRange("A55:H55").merge();
  detail.getRange("A55:H55").values = [["50条明细合计"]];
  detail.getRange("I55").formulas = [["=SUM(I5:I54)"]];
  detail.getRange("J55:L55").merge();
  detail.getRange("J55:L55").values = [["应与账单摘要一致"]];
  detail.getRange("A55:L55").format.fill = COLORS.paleGreen;
  detail.getRange("A55:L55").format.font = { bold: true, color: "#087A5B" };
  detail.getRange("A55:L55").format.borders = {
    preset: "outside",
    style: "medium",
    color: COLORS.cyan,
  };
  detail.getRange("I55").format.numberFormat = "#,##0";
  detail.freezePanes.freezeRows(4);
  detail.getRange("A:A").format.columnWidth = 8;
  detail.getRange("B:B").format.columnWidth = 20;
  detail.getRange("C:C").format.columnWidth = 13;
  detail.getRange("D:D").format.columnWidth = 10;
  detail.getRange("E:E").format.columnWidth = 25;
  detail.getRange("F:I").format.columnWidth = 17;
  detail.getRange("J:J").format.columnWidth = 13;
  detail.getRange("K:K").format.columnWidth = 20;
  detail.getRange("L:L").format.columnWidth = 25;

  notes.showGridLines = false;
  styleTitle(
    notes,
    "A1:B1",
    "数据说明与使用边界",
    "A2:B2",
    "本工作簿仅用于软件验证与比赛演示，不是客户账单、发票或监管凭证。",
  );
  notes.getRange("A4:B4").values = [["项目", "说明"]];
  styleHeader(notes.getRange("A4:B4"));
  notes.getRange("A5:B12").values = [
    ["数据性质", "完全合成；不含真实企业、户号、合同、账单或个人信息"],
    ["记录结构", "1条月度账单摘要 + 50条计量点/班次用电明细"],
    ["勾稽关系", "结束读数－起始读数＝明细用电量；50条明细合计＝月度摘要电量"],
    ["数值边界", "数量级用于工程压力测试，不代表某座真实工厂的统计分布"],
    ["排放因子", "系统演示统一使用0.5 kgCO2e/kWh的合成因子"],
    ["禁止用途", "不得用于申报、核查、报价、交易或真实业务决策"],
    ["公开背景1", "https://www.nea.gov.cn/20260821/f227e3fb9f05422285e354f4c27aec07/c.html"],
    ["公开背景2", "https://www.95598.cn/omg-static/omg-static/99302261906123669376800423273245.pdf"],
  ];
  notes.getRange("A5:A12").format.fill = COLORS.paleBlue;
  notes.getRange("A5:A12").format.font = { bold: true, color: COLORS.text };
  notes.getRange("A5:B12").format.wrapText = true;
  notes.getRange("A5:B12").format.verticalAlignment = "center";
  notes.getRange("A5:B12").format.rowHeight = 32;
  notes.getRange("A5:B12").format.borders = {
    preset: "all",
    style: "thin",
    color: COLORS.border,
  };
  notes.getRange("A:A").format.columnWidth = 18;
  notes.getRange("B:B").format.columnWidth = 78;

  return { workbook, period, amount, meterEnd };
}

async function verifyAndRender(workbook, caseId) {
  const summary = await workbook.inspect({
    kind: "table",
    sheetId: "账单摘要",
    range: "A4:K5",
    include: "values,formulas",
    tableMaxRows: 4,
    tableMaxCols: 12,
    maxChars: 5000,
  });
  if (!summary.ndjson.includes("本期用电量")) {
    throw new Error(`${caseId}: summary inspection did not find the expected header`);
  }
  const detailTop = await workbook.inspect({
    kind: "table",
    sheetId: "50条用电明细",
    range: "A4:L10",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 12,
    maxChars: 8000,
  });
  const detailTail = await workbook.inspect({
    kind: "table",
    sheetId: "50条用电明细",
    range: "A49:L55",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 12,
    maxChars: 8000,
  });
  if (
    !detailTop.ndjson.includes("P001")
    || !detailTail.ndjson.includes("P050")
    || !detailTail.ndjson.includes("50条明细合计")
  ) {
    throw new Error(`${caseId}: detail inspection did not expose the first, 50th, and total rows`);
  }
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: `${caseId} formula error scan`,
    maxChars: 5000,
  });
  if (/#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/.test(errors.ndjson)) {
    throw new Error(`${caseId}: formula error detected`);
  }

  for (const [sheetName, range] of [
    ["账单摘要", "A1:K17"],
    ["50条用电明细", "A1:L55"],
    ["数据说明", "A1:B12"],
  ]) {
    const preview = await workbook.render({
      sheetName,
      range,
      scale: 1,
      format: "png",
    });
    const safeSheet = sheetName.replaceAll("/", "-");
    await fs.writeFile(
      path.join(PREVIEW_DIR, `${caseId}_${safeSheet}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

async function main() {
  await fs.mkdir(POSITIVE_DIR, { recursive: true });
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  const cases = [];

  for (let facilityIndex = 0; facilityIndex < FACILITIES.length; facilityIndex += 1) {
    const facility = FACILITIES[facilityIndex];
    let meterStart = facility.opening;
    for (let monthIndex = 0; monthIndex < 3; monthIndex += 1) {
      const month = monthIndex + 1;
      const quantity = facility.monthlyKwh[monthIndex];
      const price = facility.prices[monthIndex];
      const caseId = `DEMO_ONLY_2026${String(month).padStart(2, "0")}_${facility.code}_50rows`;
      const { workbook, period, amount, meterEnd } = createWorkbook({
        facility,
        facilityIndex,
        month,
        quantity,
        price,
        meterStart,
      });
      await verifyAndRender(workbook, caseId);
      const outputPath = path.join(POSITIVE_DIR, `${caseId}.xlsx`);
      const output = await SpreadsheetFile.exportXlsx(workbook);
      await output.save(outputPath);
      await fs.unlink(`${outputPath}.inspect.ndjson`).catch(() => undefined);
      cases.push({
        filename: `positive/${caseId}.xlsx`,
        facility: facility.name,
        period,
        detail_row_count: 50,
        electricity_kwh: String(quantity),
        unit_price_cny_per_kwh: price.toFixed(4),
        total_amount_cny: amount.toFixed(2),
        meter_reading_start_kwh: String(meterStart),
        meter_reading_end_kwh: String(meterEnd),
        expected_tco2e_at_demo_factor: (quantity * 0.5 / 1000).toFixed(12),
      });
      meterStart = meterEnd;
    }
  }

  const manifest = {
    dataset_id: "carbonlab-competition-batch-v2-50-row-workbooks",
    generated_for: "OPC competition controlled product validation",
    synthetic: true,
    contains_real_customer_data: false,
    workbook_model: "one facility-month summary plus exactly 50 auditable detail rows",
    workbook_count: cases.length,
    total_detail_records: cases.length * 50,
    demo_factor: { value: "0.5", unit: "kgCO2e/kWh" },
    positive_cases: cases,
  };
  await fs.writeFile(
    path.join(DATASET_DIR, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(manifest, null, 2));
}

await main();
