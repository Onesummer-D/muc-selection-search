import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outDir = fileURLToPath(new URL("../docs/week2/", import.meta.url));
const outputPath = `${outDir}05_第二周验收台账.xlsx`;
const wb = Workbook.create();
const names = ["总览", "A验收", "B验收", "C验收", "协作交接", "用户功能验收", "20样本复评", "证据索引"];
const sheets = Object.fromEntries(names.map(n => [n, wb.worksheets.add(n)]));

const header = ["编号", "角色/模块", "验收项", "实际值", "证据路径", "Commit/PR", "接收确认", "指标达到目标", "状态", "备注"];
const statusFormula = (r) => `=IF(AND(D${r}<>"",E${r}<>"",F${r}<>"",G${r}<>"",H${r}=TRUE),"通过",IF(D${r}="","待填写",IF(E${r}="","缺证据",IF(OR(F${r}="",G${r}=""),"待接收","未达标"))))`;

function styleSheet(sheet, widths = [12, 14, 34, 24, 34, 24, 24, 14, 14, 30]) {
  sheet.showGridLines = false;
  sheet.getRange("A1:J1").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
  sheet.getRange("A1:J1").format.rowHeight = 30;
  widths.forEach((w, i) => sheet.getRangeByIndexes(0, i, 1, 1).format.columnWidth = w);
  sheet.getRange("A:J").format.wrapText = true;
  sheet.getRange("A1:J30").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  sheet.freezePanes.freezeRows(1);
}

function writeTracker(name, rows) {
  const sheet = sheets[name];
  sheet.getRange("A1:J1").values = [header];
  sheet.getRange(`A2:H${rows.length + 1}`).values = rows.map(r => r.slice(0, 8));
  sheet.getRange(`I2:I${rows.length + 1}`).formulas = rows.map((_, idx) => [statusFormula(idx + 2)]);
  sheet.getRange(`J2:J${rows.length + 1}`).values = rows.map(r => [r[9] || ""]);
  styleSheet(sheet);
}

writeTracker("总览", [
  ["W2-01", "总体", "第一周四元组台账缺口清零", "待补实际值", "docs/week1/05_本周验收台账.xlsx", "", "", false, "", "A/C 实际值、证据、Commit/接收仍需现场填写"],
  ["W2-02", "总体", "9/26 18:00 P0 冻结", "日期已冻结", "docs/week2/00_第二周总体目标与协作执行手册.docx", "", "", true, "", "仅修阻断、安全、权限、移动端和演示"],
  ["W2-03", "总体", "B 归一化评测作为主口径", "已载入旧报告，待复评", "reports/extraction/evaluation_report.json", "", "", false, "", "严格逐样本报告保留为附件"],
]);

writeTracker("A验收", [
  ["A-01", "A", "LAN 另一设备首页/healthz/搜索/详情", "首页/搜索/healthz 三张截图已收；访问设备：ASUS Vivobook S Flip（TN3604YA，Windows 11，192.168.43.110→组长机 192.168.43.50:5000）；访问时间 2026-09-19 20:36；详情页截图待补", "evidence/week2/A/lan-home.png; lan-search.png; lan-healthz.png", "", "", false, "设备/时间已于 2026-09-21 补记（lan-verification.md）；详情页与 C 接收确认待补"],
  ["A-02", "A", "开发角色开关关闭时 /api/dev/role=404", "pytest 30/30 + 真实 HTTP 活体验证 4 场景全 PASS（开关关闭 404 / 6 种伪造 header 提权失败 / 开关显式开启才可用）", "evidence/week2/A/role-isolation-live.txt; role-isolation-test-output.txt; auth-contract.md; scripts/run_role_isolation.py", "", "", true, "接收确认待 C 填写；契约文档已落地"],
  ["A-03", "A", "SQLite 备份恢复后三类行数一致", "", "evidence/week2/A/backup-restore.json", "", "", false, ""],
  ["A-04", "A", "HTTPS/CAS 条件式结论", "未提供服务器/域名/CAS", "progress/week2/A/deployment-blocker.md", "", "", true, "不得伪造公网 URL"],
]);
sheets["A验收"].getRange("D:D").format.columnWidth = 36;
sheets["A验收"].getRange("E:E").format.columnWidth = 46;
sheets["A验收"].getRange("J:J").format.columnWidth = 40;

writeTracker("B验收", [
  ["B-01", "B", "固定 5 篇 bundle/evidence pack 可导入 C SQLite", "待烟测", "evidence/week2/B/bundle-import-smoke.json", "", "", false, ""],
  ["B-02", "B", "20 样本归一化字段评测可重算", "待复评", "reports/extraction/evaluation_report.json", "", "", false, ""],
  ["B-03", "B", "专业/城市/岗位低于 90% 进入复核队列", "已记录旧报告", "reports/extraction/evaluation_report.json", "", "", true, "不把报告存在误报为准确率达标"],
  ["B-04", "B", "多模态启用差值门槛", "归一化完整记录差值=-21.06pp", "reports/extraction/evaluation_report.json", "", "", true, "结论保持不启用"],
]);

writeTracker("C验收", [
  ["C-01", "C", "保存搜索创建/读取/提醒修改/删除", "已实现接口与测试", "app/web/api.py; tests/core/test_week2_profile.py", "", "", true, ""],
  ["C-02", "C", "隐私默认关闭、开启后保留90天", "已实现接口与测试", "app/repository/sqlite_repository.py", "", "", true, ""],
  ["C-03", "C", "无痕搜索不写历史", "已实现接口与测试", "tests/core/test_week2_profile.py", "", "", true, ""],
  ["C-04", "C", "游客脱敏与 review_required 不公开", "第一周代码已有，Network 证据待补", "evidence/week2/C/guest-network.json", "", "", false, ""],
]);

writeTracker("协作交接", [
  ["H-01", "B→C", "B 白名单目录与接收 Commit", "已迁移，待接收登记", "git diff --name-status origin/main..origin/feat/week1-extraction-eval", "", "", false, "不得整支合并 B 分支"],
  ["H-02", "A→C", "LAN/备份/CAS 条件式证据", "待 A 提交", "evidence/week2/A/", "", "", false, "至少预留4小时接收窗口"],
  ["H-03", "C→全员", "演示脚本与录屏", "待 9/25 复测", "evidence/week2/C/demo.mp4", "", "", false, ""],
]);

writeTracker("用户功能验收", [
  ["U-01", "C", "跨用户隔离", "测试已覆盖", "tests/core/test_week2_profile.py", "", "", true, ""],
  ["U-02", "C", "提醒仅 off/daily/weekly，默认 weekly", "已实现", "app/web/api.py", "", "", true, ""],
  ["U-03", "C", "删除历史后旧记录不参与推荐", "待端到端证据", "evidence/week2/C/history-delete.json", "", "", false, ""],
  ["U-04", "C", "管理员发布/撤回写审计事件", "已实现接口", "app/web/api.py", "", "", true, ""],
]);

const rep = sheets["20样本复评"];
rep.getRange("A1:H1").values = [["路线", "字段", "正确数", "可判定数", "归一化准确率", "低于90%样本/队列", "证据", "结论"]];
rep.getRange("A2:H11").values = [
  ["OCR", "届别", 20, 20, 1.0, "", "reports/extraction/evaluation_report.json", "达标"],
  ["OCR", "学历", 15, 20, 0.75, "P02 P03 P05 P06 P10 P15", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["OCR", "专业", 10, 20, 0.5, "P01 P03 P04 P05 P07 P08 P11 P13 P14 P16 P19 P20", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["OCR", "城市", 15, 19, 0.7895, "P04 P05 P06 P07 P09 P10 P11 P15", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["OCR", "岗位", 17, 20, 0.85, "P01-P19（详见报告）", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["多模态", "届别", 20, 20, 1.0, "", "reports/extraction/evaluation_report.json", "达标"],
  ["多模态", "学历", 19, 20, 0.95, "P02 P03 P05 P06 P10", "reports/extraction/evaluation_report.json", "达标"],
  ["多模态", "专业", 13, 20, 0.65, "P03 P07 P08 P16", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["多模态", "城市", 16, 19, 0.8421, "P01 P03 P05 P06 P07 P08 P09 P10 P12 P14 P15 P16 P18 P20", "reports/extraction/evaluation_report.json", "未达标，复核"],
  ["多模态", "岗位", 5, 20, 0.25, "P05 P13 P19", "reports/extraction/evaluation_report.json", "未达标，复核"],
];
rep.getRange("E2:E11").format.numberFormat = "0.00%";
rep.getRange("A1:H1").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
rep.getRange("A1:H11").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
rep.getRange("A:H").format.wrapText = true;
rep.getRange("A:H").format.columnWidth = 18;
rep.getRange("F:F").format.columnWidth = 35;
rep.getRange("G:G").format.columnWidth = 38;
rep.getRange("H:H").format.columnWidth = 18;
rep.freezePanes.freezeRows(1);

const idx = sheets["证据索引"];
idx.getRange("A1:G1").values = [["证据ID", "角色", "证据路径", "类型", "提交Commit/PR", "接收人/时间", "状态"]];
idx.getRange("A2:G13").values = [
  ["E-01", "A", "evidence/week2/A/lan-home.png; lan-search.png; lan-healthz.png", "截图", "", "", "设备/时间已补记（2026-09-21，见 lan-verification.md），详情页截图待补"],
  ["E-02", "A", "evidence/week2/A/backup-restore.json", "日志", "", "", "待补"],
  ["E-03", "A", "progress/week2/A/deployment-blocker.md", "阻塞记录", "", "", "待补"],
  ["E-04", "B", "evidence/week2/B/bundle-import-smoke.json", "导入日志", "", "", "待补"],
  ["E-05", "B", "reports/extraction/evaluation_report.json", "评测报告", "", "", "已存在，待复评"],
  ["E-06", "B", "data/gold/gold_20.json", "gold", "", "", "已存在"],
  ["E-07", "C", "tests/core/test_week2_profile.py", "测试", "", "", "已存在"],
  ["E-08", "C", "evidence/week2/C/guest-network.json", "Network", "", "", "待补"],
  ["E-09", "C", "evidence/week2/C/demo.mp4", "录屏", "", "", "待补"],
  ["E-10", "审查", "docs/week2/06_独立审查报告.md", "审查", "", "", "已生成"],
  ["E-11", "文档", "docs/week2/00-03*.docx", "说明书", "", "", "已生成"],
  ["E-12", "分支", "feat/week2-integration", "Git", "", "", "已建立"],
];
idx.getRange("A1:G1").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
idx.getRange("A1:G13").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
idx.getRange("A:G").format.wrapText = true;
idx.getRange("A:G").format.columnWidth = 24;
idx.getRange("C:C").format.columnWidth = 50;
idx.freezePanes.freezeRows(1);

for (const s of Object.values(sheets)) s.getUsedRange()?.format.autofitRows();
await wb.recalculate();
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, sheets: names }));
