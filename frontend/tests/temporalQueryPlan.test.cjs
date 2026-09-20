const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/features/search/temporalQueryPlan.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const helpers = {};
new Function("exports", compiled)(helpers);
const { temporalEventsFromPlan } = helpers;

function event(vi, ocr = "", asr = "", anchor = false) {
  return { vi, en: `English: ${vi}`, ocr, asr, anchor, visual_keywords: [] };
}

test("does not assign compact global OCR/ASR lists to an empty first event", () => {
  const plan = {
    events: [event("tách hạt", "", "", true), event("thêm gia vị", "nước tương", "nước tương")],
    ocr_queries: ["nước tương"], asr_queries: ["nước tương"],
  };
  const snapshot = JSON.stringify(plan);
  const rows = temporalEventsFromPlan(plan);
  assert.deepEqual(rows.map((r) => r.ocr), ["", "nước tương"]);
  assert.deepEqual(rows.map((r) => r.asr), ["", "nước tương"]);
  assert.equal(rows[0].text, "tách hạt");
  assert.equal(rows[0].translation, "English: tách hạt");
  assert.equal(rows[0].anchor, true);
  assert.equal(JSON.stringify(plan), snapshot);
});

test("preserves event alignment and repeated keywords after global deduplication", () => {
  const plan = {
    events: [event("đảo"), event("thêm nước", "1,5 lít"), event("nêm", "", "muối"),
      event("nêm tiếp", "1,5 lít", "muối")],
    ocr_queries: ["1,5 lít"], asr_queries: ["muối"],
  };
  const rows = temporalEventsFromPlan(plan);
  assert.deepEqual(rows.map((r) => r.ocr), ["", "1,5 lít", "", "1,5 lít"]);
  assert.deepEqual(rows.map((r) => r.asr), ["", "", "muối", "muối"]);
});

test("global-only keywords stay global and English-only events retain their text", () => {
  const englishOnly = { ...event(""), en: "A glass pot", anchor: true };
  const rows = temporalEventsFromPlan({
    events: [englishOnly, event("chảo")],
    ocr_queries: ["1,5 lít", "2 muỗng"], asr_queries: ["nêm"],
  });
  assert.equal(rows[0].text, "A glass pot");
  assert.ok(rows.every((r) => r.ocr === "" && r.asr === ""));
});
