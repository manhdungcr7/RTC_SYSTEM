"""Repeatable, answer-blind GPT Explore prompt and RTC retrieval benchmark.

The generation phase reads only query ZIP and prompt files. Ground truth in
submission/ is read only by the separate scoring phase.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "queries" / "SOTUYEN3-bo-de-thi.zip"
OUT = ROOT / "artifacts" / "gpt_explore_eval"
API = "http://localhost:8080"
RE_NUM = re.compile(r"query-p2-(\d+)-(kis|qa|trake)\.txt$")
EXCLUDED_NUMBERS = {5, 6, 9}  # User-specified: do not score these questions.
SIGNALS = {k: {"enabled": True, "weight": v} for k, v in
           {"metaclip2": 1.0, "pecore": .7, "beit3": .4, "capemb": .6}.items()}


def questions():
    with zipfile.ZipFile(ZIP) as z:
        return sorted(((int(m.group(1)), m.group(2), z.read(name).decode("utf-8-sig").strip())
                       for name in z.namelist() if (m := RE_NUM.fullmatch(name))),
                      key=lambda x: x[0])


def dotenv():
    result = {}
    for line in (ROOT / "docker" / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, val = line.split("=", 1)
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def post(url, payload, headers=None, timeout=180):
    req = urllib.request.Request(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def openai_text(model, instructions, query, api_key):
    payload = {"model": model, "instructions": instructions,
               "input": "Phân tích đề bài dưới đây thành kế hoạch truy vấn thị giác và chỉ trả JSON đúng schema đã được cấu hình:\n\n" + query,
               "reasoning": {"effort": "low"}, "max_output_tokens": 5000, "store": False}
    response = post("https://api.openai.com/v1/responses", payload,
                    {"Authorization": "Bearer " + api_key}, timeout=180)
    output = "".join(c.get("text", "") for o in response.get("output", [])
                     for c in o.get("content", []) if c.get("type") == "output_text")
    if response.get("status") != "completed" or not output:
        raise ValueError("response incomplete: " + str(response.get("status")))
    return output, response.get("model"), response.get("usage", {})


def parse_object(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("missing JSON object")
    return json.loads(text[start:end + 1])


def generate_one(item, name, instructions, model, api_key):
    number, kind, query = item
    target = OUT / name / f"{number:02d}.json"
    if target.exists():
        return number, "cached"
    for attempt in range(3):
        try:
            raw, actual_model, usage = openai_text(model, instructions, query, api_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.with_suffix(".raw.txt").write_text(raw, encoding="utf-8")
            plan = parse_object(raw)
            validated = post(API + "/query/plan/validate", {"plan": plan}, timeout=20)
            result = {"number": number, "kind": kind, "model": actual_model,
                      "usage": usage, "raw_plan": plan, "plan": validated["plan"],
                      "warnings": validated["warnings"]}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return number, "ok"
        except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            if attempt == 2:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.with_suffix(".error.txt").write_text(str(exc)[:1000], encoding="utf-8")
                return number, "error: " + str(exc)[:100]
            time.sleep(2 ** attempt)


def generate(name, model, workers):
    folder = ROOT / name
    instructions = (folder / "AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md").read_text(encoding="utf-8")
    knowledge = folder / "AIC_VISUAL_QUERY_EXAMPLES.md"
    if knowledge.exists():
        instructions += "\n\n## Knowledge examples (illustrative, lower priority)\n" + knowledge.read_text(encoding="utf-8")
    api_key = dotenv().get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY missing in docker/.env")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(generate_one, item, name, instructions, model, api_key) for item in questions()]
        for f in concurrent.futures.as_completed(futures):
            print(name, *f.result(), flush=True)


def retrieve_one(item, name):
    number, kind, query = item
    plan_path = OUT / name / f"{number:02d}.json"
    if not plan_path.exists():
        return number, "no plan"
    result_path = OUT / name / f"{number:02d}.retrieval.json"
    if result_path.exists():
        return number, "cached"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))["plan"]
    events = plan["events"]
    if len(events) >= 2:
        payload = {"events": [e["vi"] or e["en"] for e in events],
                   "context": plan["context"]["vi"] or plan["context"]["en"],
                   "split_clauses": False,
                   "ocr_queries": [e["ocr"] for e in events],
                   "asr_queries": [e["asr"] for e in events],
                   "event_translations": [e["en"] for e in events],
                   "anchor_indices": [i for i, e in enumerate(events) if e["anchor"]],
                   "per_event": 1500, "max_gap_s": plan["max_gap_s"], "topk": 50,
                   "alternates_per_event": 0,
                   "signals": {**SIGNALS,
                               "ocr": {"enabled": any(e["ocr"] for e in events), "weight": .25},
                               "asr": {"enabled": any(e["asr"] for e in events), "weight": .15}}}
        endpoint = "/temporal"
    else:
        clauses = plan["search_clauses"] or [events[0]["vi"] or events[0]["en"]]
        en = plan["search_clauses_en"]
        ocr = " ".join(plan["ocr_queries"]).strip()
        asr = " ".join(plan["asr_queries"]).strip()
        payload = {"query": plan["original_query"] or query, "kind": kind, "topk": 200,
                   "split_clauses": False, "use_expansion": True,
                   "signals": {**SIGNALS, "ocr": {"enabled": bool(ocr), "weight": .25},
                               "asr": {"enabled": bool(asr), "weight": .15}},
                   "clauses": [{"text": c, "weight": 1, "enabled": True} for c in clauses],
                   "translations": {i: c for i, c in enumerate(en)},
                   "per_video_cap": 5, "explain": False, "branch_lists": False}
        if ocr:
            payload["ocr"] = {"query": ocr, "mode": "score"}
        if asr:
            payload["asr"] = {"query": asr, "lexical": True, "semantic": True, "mode": "score"}
        endpoint = "/search"
    try:
        response = post(API + endpoint, payload, timeout=240)
        if endpoint == "/search":
            slim = {"mode": "search", "hits": [{k: h.get(k) for k in ("video", "frame_idx", "n", "rank", "score")}
                                                   for h in response["hits"]],
                    "took_ms": response.get("took_ms"), "signals_used": response.get("signals_used")}
        else:
            slim = {"mode": "temporal", "candidates": [
                {"video": c["video"], "rank": i + 1,
                 "hits": [{k: h.get(k) for k in ("video", "frame_idx", "n", "score")}
                          for h in c["hits"]]}
                for i, c in enumerate(response["candidates"])]}
        result_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
        return number, "ok"
    except (urllib.error.URLError, ValueError) as exc:
        result_path.with_suffix(".error.txt").write_text(str(exc)[:1000], encoding="utf-8")
        return number, "error: " + str(exc)[:100]


def retrieve(name, workers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(retrieve_one, item, name) for item in questions()]
        for f in concurrent.futures.as_completed(futures):
            print(name, *f.result(), flush=True)


def score(name):
    rows = []
    for number, kind, _ in questions():
        if number in EXCLUDED_NUMBERS:
            rows.append({"number": number, "kind": kind, "status": "excluded"})
            continue
        ground_path = ROOT / "submission" / f"query-p2-{number}-{kind}.csv"
        plan_path = OUT / name / f"{number:02d}.json"
        result_path = OUT / name / f"{number:02d}.retrieval.json"
        if not ground_path.exists():
            rows.append({"number": number, "kind": kind, "status": "no_ground_truth"})
            continue
        if not plan_path.exists() or not result_path.exists():
            rows.append({"number": number, "kind": kind, "status": "missing_run"})
            continue
        gt = list(csv.reader(ground_path.open(encoding="utf-8-sig", newline="")))
        gt_videos = {r[0] for r in gt}
        gt_frames = {r[0]: [int(x[1]) for x in gt if x[0] == r[0]] for r in gt}
        result = json.loads(result_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))["plan"]
        if result["mode"] == "search":
            hits = result["hits"]
            result_rank = next((i + 1 for i, h in enumerate(hits) if h["video"] in gt_videos), None)
            unique_videos = list(dict.fromkeys(h["video"] for h in hits))
            rank = next((i + 1 for i, v in enumerate(unique_videos) if v in gt_videos), None)
            near = min((abs(h["frame_idx"] - f) for h in hits if h["video"] in gt_videos
                        for f in gt_frames[h["video"]]), default=None)
            top_video = hits[0]["video"] if hits else ""
        else:
            hits = result["candidates"]
            rank = next((i + 1 for i, h in enumerate(hits) if h["video"] in gt_videos), None)
            result_rank = rank
            near = min((abs(h["frame_idx"] - f) for c in hits if c["video"] in gt_videos
                        for h in c["hits"] for f in gt_frames[c["video"]]), default=None)
            top_video = hits[0]["video"] if hits else ""
        trake_deltas = ""
        if kind == "trake" and result["mode"] == "temporal":
            target = next((c for c in result["candidates"] if c["video"] in gt_videos), None)
            reference = next((r for r in gt if r[0] in gt_videos and len(r) >= 5), None)
            if target and reference and len(target["hits"]) == 4:
                trake_deltas = "|".join(str(abs(h["frame_idx"] - int(f)))
                                         for h, f in zip(target["hits"], reference[1:5]))
        rows.append({"number": number, "kind": kind, "status": "ok", "mode": result["mode"],
                     "events": len(plan["events"]), "video_rank": rank,
                     "result_rank": result_rank, "frame_delta_min": near,
                     "trake_deltas": trake_deltas,
                     "top_video": top_video, "gt_video": "|".join(sorted(gt_videos)),
                     "warnings": len(json.loads(plan_path.read_text(encoding="utf-8"))["warnings"])})
    out = OUT / f"{name}_scores.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["number", "kind", "status", "mode", "events",
                                             "video_rank", "result_rank", "frame_delta_min",
                                             "trake_deltas", "top_video", "gt_video", "warnings"])
        writer.writeheader()
        writer.writerows(rows)
    valid = [r for r in rows if r["status"] == "ok"]
    print(name, "evaluated", len(valid), "top1", sum(r["video_rank"] == 1 for r in valid),
          "top10", sum(r["video_rank"] is not None and r["video_rank"] <= 10 for r in valid),
          "top50", sum(r["video_rank"] is not None and r["video_rank"] <= 50 for r in valid))
    print(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["generate", "retrieve", "score"])
    parser.add_argument("name", choices=["gpt_explore", "gpt_explore_v2", "gpt_explore_v3"])
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.phase == "generate":
        generate(args.name, args.model, args.workers)
    elif args.phase == "retrieve":
        retrieve(args.name, args.workers)
    else:
        score(args.name)


if __name__ == "__main__":
    main()
