const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(path.join(__dirname, "../src/features/results/videoList.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const helpers = {};
new Function("exports", compiled)(helpers);
const { rankedVideoList, formatVideoList } = helpers;

test("deduplicates before limiting, retaining ranked order", () => {
  assert.deepEqual(rankedVideoList(["L21_V002", "L21_V002", "L21_V001", "L21_V003"], 2),
    ["L21_V002", "L21_V001"]);
});

test("defaults to 70 unique videos", () => {
  const ids = Array.from({ length: 90 }, (_, i) => `L21_V${String(i + 1).padStart(3, "0")}`);
  assert.equal(helpers.DEFAULT_VIDEO_LIMIT, 70);
  assert.equal(rankedVideoList(ids, Number.NaN).length, 70);
});

test("exports only video IDs separated by commas, with no duplicates or blanks", () => {
  assert.equal(formatVideoList([" L21_V001 ", "", "L21_V001", "L23_V002"], 70),
    "L21_V001, L23_V002");
});

test("handles empty and fewer-than-N results", () => {
  assert.equal(formatVideoList([], 70), "");
  assert.deepEqual(rankedVideoList(["L30_V010"], 70), ["L30_V010"]);
});
