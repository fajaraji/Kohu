"""Kohu eval (C3). Writes eval/results.json and eval/results.md.

  python eval/run_eval.py            # full run (QA asks call Muse Spark)
  python eval/run_eval.py --no-qa    # everything except the live asks

Runs against a fresh database (kohu_eval) seeded from the committed
corpus and the model cache, so the demo database is not touched and the
seed makes no model calls. Sections:

  qa         20 frozen questions (eval/questions.json), live agent
  leak       every persona x every tool and route against every source
             the persona may not see (no model needed)
  conflicts  3 planted conflicts and 3 controls (eval/conflicts.json),
             plus what full detection flagged
  steps      video step start times vs the recording's ground truth
  marks      SAM marks vs the true element boxes
  reading    Spark's reading of the chart page vs World Bank values
"""

import argparse
import csv
import json
import os
import pathlib
import statistics
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "api"))
os.environ.setdefault("KOHU_SESSION_SECRET", "eval-secret")
EVAL_DB = os.environ.get("KOHU_EVAL_DATABASE_URL",
                         "postgresql://postgres@localhost:5432/kohu_eval")

import agent  # noqa: E402
import conflict  # noqa: E402
import corpus  # noqa: E402
import db  # noqa: E402
import ingest  # noqa: E402
import meta_client  # noqa: E402
import migrate  # noqa: E402
import policy  # noqa: E402
import regions  # noqa: E402
import retrieval  # noqa: E402
import video  # noqa: E402


def iou(a, b):
    ix = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    iy = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter = ix * iy
    union = ((a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
             + (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) - inter)
    return inter / union if union else 0.0


# ------------------------------------------------------------------ seed

def fresh_db(url):
    import psycopg
    from urllib.parse import urlparse
    name = urlparse(url).path.lstrip("/")
    assert name == "kohu_eval", "eval only drops its own database"
    db.check_url(url)
    maint = url.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(maint, autocommit=True) as c:
        c.execute('DROP DATABASE IF EXISTS "kohu_eval"')
    migrate.cmd_up(url)
    ingest.ingest(REPO / "corpus", url)
    video.seed(url)
    regions.run(url)
    stats = conflict.detect(None, url)
    return stats


# -------------------------------------------------------------------- qa

def check_question(q, r):
    text = r["text"]
    blob = json.dumps(r).lower()
    cited = {c["source_id"] for c in r["citations"]}
    fails = []
    if q.get("cite_any") and not cited & set(q["cite_any"]):
        fails.append("no citation from %s" % q["cite_any"])
    for s in q.get("cite_all", []):
        if s not in cited:
            fails.append("missing citation from %s" % s)
    for s in q.get("contains_all", []):
        if s.lower() not in text.lower():
            fails.append("answer lacks %r" % s)
    if q.get("contains_any") and not any(s.lower() in text.lower()
                                         for s in q["contains_any"]):
        fails.append("answer has none of %s" % q["contains_any"])
    for s in q.get("not_contains", []):
        if s.lower() in blob:
            fails.append("response contains %r" % s)
    for s in q.get("never_cite", []):
        if s in blob:
            fails.append("response mentions %s" % s)
    if q.get("type_in") and r["answer_type"] not in q["type_in"]:
        fails.append("answer_type %s not in %s" % (r["answer_type"],
                                                  q["type_in"]))
    return fails


def run_qa(url):
    qs = json.loads((REPO / "eval" / "questions.json").read_text())
    out = []
    client = meta_client.MetaClient()
    for q in qs["questions"]:
        t0 = time.time()
        try:
            r = agent.run(q["question"], q["persona"], "eval-" + q["persona"],
                          url, client=client)
        except Exception as e:  # noqa: BLE001
            out.append({"id": q["id"], "pass": False,
                        "fails": ["error %s" % e]})
            continue
        fails = check_question(q, r)
        out.append({"id": q["id"], "persona": q["persona"],
                    "question": q["question"], "pass": not fails,
                    "fails": fails, "answer_type": r["answer_type"],
                    "text": r["text"],
                    "cited": sorted({(c["source_id"], c["pointer"])
                                     for c in r["citations"]}),
                    "degraded": r["degraded"], "dropped": len(r["dropped"]),
                    "seconds": round(time.time() - t0, 1),
                    "usage": r["usage"]})
        print("%s %s %s" % (q["id"], "PASS" if not fails else "FAIL", fails))
    return out


# ------------------------------------------------------------------ leak

def run_leak(url):
    import psycopg
    from fastapi.testclient import TestClient

    import app as kohu

    os.environ["DATABASE_URL"] = url
    entries = corpus.load_manifest()["entries"]
    all_ids = [e["id"] for e in entries]
    with psycopg.connect(url) as c:
        chunks = c.execute("SELECT id, source_id, text FROM chunks").fetchall()
    checks, failures = 0, []

    def check(ok, what):
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(what)

    with TestClient(kohu.app) as http:
        for p in policy.PERSONAS:
            visible = set(policy.visible_sources(p))
            denied = [s for s in all_ids if s not in visible]
            tok = {"Authorization": "Bearer " + http.post(
                "/login", json={"persona": p}).json()["token"]}
            for sid in denied:
                e = corpus.entry(sid)
                # search_knowledge with the denied source's own words
                for cid, csid, text in [c for c in chunks if c[1] == sid]:
                    words = retrieval.query_terms(text)[:12]
                    hits = retrieval.search(" ".join(words), p, url,
                                            limit=50, min_score=0)
                    check(all(h["source_id"] in visible for h in hits),
                          "%s search leaked %s" % (p, sid))
                    check(retrieval.read_section(str(cid), p, 2, url) == [],
                          "%s read_section leaked %s" % (p, sid))
                    out, logged = agent.run_tool(
                        "read_section", {"chunk_id": str(cid)}, p,
                        agent.Evidence(), url, corpus.DEFAULT_CORPUS)
                    check(out == "Not found." and not logged,
                          "%s tool read_section leaked %s" % (p, sid))
                if e["citation_anchors"]["type"] == "cell-range":
                    rng = e["citation_anchors"]["sheet"] + "!A1:J41"
                    check(retrieval.read_cells(sid, rng, p) is None,
                          "%s read_cells leaked %s" % (p, sid))
                    out, _ = agent.run_tool("read_cells", {
                        "source_id": sid, "range": rng}, p, agent.Evidence(),
                        url, corpus.DEFAULT_CORPUS)
                    check(out == "Not found.", "%s tool read_cells leaked %s"
                          % (p, sid))
                    r = http.get("/cells/%s" % sid, params={"range": rng},
                                 headers=tok)
                    check(r.status_code == 403, "%s /cells %s -> %d"
                          % (p, sid, r.status_code))
                for path in ("/files/%s" % sid,
                             "/files/%s/page/1.png" % sid,
                             "/files/%s/assets/page-01.png" % sid,
                             "/regions/%s/1" % sid):
                    r = http.get(path, headers=tok)
                    check(r.status_code == 403, "%s %s -> %d"
                          % (p, path, r.status_code))
            for route in ("/sources", "/conflicts", "/licenses"):
                body = http.get(route, headers=tok).text
                for sid in denied:
                    check(sid not in body, "%s %s mentions %s"
                          % (p, route, sid))
            # A Steward run's trace, read by this persona.
            srun = agent.run("Viet Nam GDP growth 2023 dataset", "steward",
                             "eval", url, client=meta_client.MetaClient(
                                 key=""))
            trace = json.dumps(agent.run_steps(srun["run_id"], p, url))
            for sid in denied:
                check(sid not in trace, "%s trace mentions %s" % (p, sid))
    return {"checks": checks, "failures": failures}


# ------------------------------------------------------------- conflicts

def run_conflicts(url, detect_stats):
    import psycopg

    spec = json.loads((REPO / "eval" / "conflicts.json").read_text())
    out = {"planted": [], "controls": []}
    for kind in ("conflicts", "controls"):
        for item in spec[kind]:
            pid = conflict.pair_id(tuple(item["a"]), tuple(item["b"]))
            with psycopg.connect(url) as c:
                in_detect = c.execute(
                    "SELECT is_conflict FROM conflict_judgments WHERE "
                    "pair_id = %s", (pid,)).fetchone()
            direct = conflict.judge_pair(tuple(item["a"]), tuple(item["b"]),
                                         url, store=False)
            out["planted" if kind == "conflicts" else "controls"].append({
                "id": item["id"], "pair_id": pid,
                "candidate_in_detection": in_detect is not None,
                "flagged_by_detection": bool(in_detect and in_detect[0]),
                "flagged_when_judged_directly": bool(direct["is_conflict"]),
                "summary": direct.get("summary")})
    labeled = {x["pair_id"] for x in out["planted"] + out["controls"]}
    with psycopg.connect(url) as c:
        flagged = c.execute(
            "SELECT conflict_id, a_source, a_pointer, b_source, b_pointer, "
            "summary FROM conflicts").fetchall()
    out["detection"] = dict(detect_stats, flagged=[
        {"conflict_id": f[0], "a": [f[1], f[2]], "b": [f[3], f[4]],
         "summary": f[5], "labeled": f[0] in labeled} for f in flagged])
    return out


# ----------------------------------------------------------- video/marks

def run_steps_and_marks(url):
    truth = json.loads((REPO / "corpus" / "demo-app" /
                        "clip-truth.json").read_text())
    return score_clip(truth, video.steps("refund-process-video", url))


def run_heldout_clip(url):
    """Second clip, recorded after the step prompt and the marking rule
    were fixed. Processed through the same pipeline in a temp corpus."""
    import shutil
    import tempfile

    src = REPO / "video" / "assets" / "stock-check.mp4"
    truth = json.loads((REPO / "video" / "assets" /
                        "stock-check.truth.json").read_text())
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        (tmp / "clips").mkdir()
        shutil.copy(src, tmp / "clips" / "stock-check.mp4")
        entry = {"id": "heldout-stock-check", "kind": "video",
                 "filename": "clips/stock-check.mp4",
                 "title": "How to check stock for a returned item",
                 "license_class": "open-internal",
                 "visible_to": list(policy.PERSONAS),
                 "citation_anchors": {"type": "timestamp"}}
        (tmp / "manifest.json").write_text(json.dumps(
            {"entries": [entry], "chunking": {"sheet_windows": {}}}))
        out = video.process("heldout-stock-check", url, tmp)
        scored = score_clip(truth, video.steps("heldout-stock-check", url))
        scored["timing_s"] = out["timing"]
        return scored
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def score_clip(truth, steps):
    acts = [s for s in truth["steps"] if s.get("action")]
    errs, rows = [], []
    for s in steps:
        t = min(acts, key=lambda a: abs(a["start"] - s["t_start"]))
        err = abs(s["t_start"] - t["start"])
        errs.append(err)
        b = s["box"] or {}
        ov = iou(b, t["box"]) if "x1" in b else 0.0
        rows.append({"n": s["n"], "t_start": s["t_start"],
                     "truth_start": t["start"], "abs_error_s": round(err, 2),
                     "reason_given": s["reason"] is not None,
                     "reason_in_script": t.get("reason") is not None,
                     "mark_status": s["mark_status"],
                     "drawn": b.get("drawn"), "iou": round(ov, 3),
                     "target": s["target_phrase"], "truth_target": t["target"],
                     "origin": s["origin"]})
    matched = {min(acts, key=lambda a: abs(a["start"] - s["t_start"]))["n"]
               for s in steps}
    ious = [r["iou"] for r in rows]
    return {
        "truth_steps": len(acts), "model_steps": len(steps),
        "truth_steps_matched": len(matched),
        "start_error_s": {"median": round(statistics.median(errs), 2),
                          "mean": round(statistics.mean(errs), 2),
                          "max": round(max(errs), 2)},
        "reasons": {
            "given_and_in_script": sum(r["reason_given"] and
                                       r["reason_in_script"] for r in rows),
            "given_not_in_script": sum(r["reason_given"] and not
                                       r["reason_in_script"] for r in rows),
            "missed": sum(not r["reason_given"] and r["reason_in_script"]
                          for r in rows)},
        "marks": {
            "marked_share": round(sum(r["mark_status"] != "failed"
                                      for r in rows) / len(rows), 3),
            "iou_at_least_0_5_share": round(sum(i >= 0.5 for i in ious)
                                            / len(ious), 3),
            "iou_median": round(statistics.median(ious), 3),
            "drawn_as_sam_mask_share": round(sum(r["drawn"] == "mask"
                                                 for r in rows) / len(rows),
                                             3),
            "status_counts": {k: sum(r["mark_status"] == k for r in rows)
                              for k in ("phrase", "box", "spark_box",
                                        "failed")}},
        "rows": rows}


def run_reading(url):
    import psycopg

    with open(REPO / "corpus" / "public" /
              "worldbank-asean-2019-2024.csv") as f:
        wb = {r["country"]: float(r["value"]) for r in csv.DictReader(f)
              if r["indicator_code"] == "NY.GDP.MKTP.KD.ZG"
              and r["year"] == "2024"}
    wb["Brunei"] = wb.pop("Brunei Darussalam")
    with psycopg.connect(url) as c:
        text, origin = c.execute(
            "SELECT text, text_origin FROM chunks WHERE source_id = "
            "'asean-outlook-report' AND page = 4").fetchone()
    got = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.rsplit(":", 1)
            try:
                got[k.strip()] = float(v.strip())
            except ValueError:
                pass
    right = sum(1 for k, v in wb.items()
                if k in got and abs(got[k] - round(v, 1)) < 1e-9)
    reg = regions.regions("asean-outlook-report", 4, url)
    return {"page": "asean-outlook-report p.4", "text_origin": origin,
            "values_expected": len(wb), "values_correct": right,
            "sam_regions_on_chart_page": len(reg)}


def write_markdown(res):
    qa = res.get("qa") or []
    lines = ["# Kohu eval results", "",
             "Generated by `python eval/run_eval.py` on %s against a fresh "
             "`kohu_eval` database seeded from the committed corpus and model "
             "cache. Live Meta API calls: the 20 QA asks and anything not "
             "cached. Raw numbers: `eval/results.json`." % res["run_at"], ""]
    if qa:
        n = sum(1 for q in qa if q["pass"])
        lines += ["## Questions (20, frozen before the first run)", "",
                  "Passed %d of %d. Median time per ask %.1f s." % (
                      n, len(qa), statistics.median(
                          [q.get("seconds", 0) for q in qa])), "",
                  "| id | role | pass | type | cited | why it failed |",
                  "|---|---|---|---|---|---|"]
        for q in qa:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                q["id"], q.get("persona", ""), "yes" if q["pass"] else "no",
                q.get("answer_type", ""), ", ".join(
                    "%s %s" % tuple(c) for c in q.get("cited", [])),
                "; ".join(q["fails"]) or ""))
        lines.append("")
    lk = res["leak"]
    lines += ["## Leak test", "",
              "%d checks across all four roles: search with the denied "
              "source's own words, read_section on every denied chunk (direct "
              "and as an agent tool), read_cells, and the file, page, asset, "
              "region, cell, source, conflict and license routes, plus a "
              "Steward run's trace read by each role. Failures: %d." % (
                  lk["checks"], len(lk["failures"])), ""]
    lines += ["\n".join("- " + f for f in lk["failures"][:20])] if \
        lk["failures"] else []
    cf = res["conflicts"]
    tp = sum(x["flagged_by_detection"] for x in cf["planted"])
    tpd = sum(x["flagged_when_judged_directly"] for x in cf["planted"])
    fp = sum(x["flagged_by_detection"] for x in cf["controls"])
    fpd = sum(x["flagged_when_judged_directly"] for x in cf["controls"])
    det = cf["detection"]
    unl = [f for f in det["flagged"] if not f["labeled"]]
    lines += ["## Conflicts", "",
              "Planted conflicts caught by full detection: %d of 3 (judged "
              "directly: %d of 3). Controls flagged by detection: %d of 3 "
              "(judged directly: %d of 3)." % (tp, tpd, fp, fpd), "",
              "| item | candidate pair found | flagged |", "|---|---|---|"]
    for x in cf["planted"] + cf["controls"]:
        lines.append("| %s | %s | %s |" % (
            x["id"], "yes" if x["candidate_in_detection"] else "no",
            "yes" if x["flagged_by_detection"] else "no"))
    lines += ["", "Full detection judged %d pairs and flagged %d. Flags "
              "outside the labeled set (not scored as right or wrong):" % (
                  det["judged"], det["conflicts"]), ""]
    lines += ["- %s %s vs %s %s: %s" % (f["a"][0], f["a"][1], f["b"][0],
                                        f["b"][1], f["summary"])
              for f in unl] or ["- none"]
    st = res["steps"]
    mk = st["marks"]
    lines += ["", "## Video steps", "",
              "Demo clip: %d true steps, %d model steps, %d true steps "
              "matched. Start time error: median %.2f s, mean %.2f s, max "
              "%.2f s. Reasons: %d given where the script states one, %d "
              "given where the script does not, %d missed." % (
                  st["truth_steps"], st["model_steps"],
                  st["truth_steps_matched"], st["start_error_s"]["median"],
                  st["start_error_s"]["mean"], st["start_error_s"]["max"],
                  st["reasons"]["given_and_in_script"],
                  st["reasons"]["given_not_in_script"],
                  st["reasons"]["missed"]), "",
              "## SAM marks", "",
              "Steps with a mark: %.0f%%. Marks with IoU of at least 0.5 "
              "against the true element: %.0f%% (median IoU %.2f). Marks "
              "drawn from a decoded SAM mask: %.0f%%; the rest are SAM boxes "
              "(see limitations). Status counts: %s." % (
                  100 * mk["marked_share"], 100 * mk["iou_at_least_0_5_share"],
                  mk["iou_median"], 100 * mk["drawn_as_sam_mask_share"],
                  mk["status_counts"]), ""]
    ho = res.get("heldout_clip")
    if ho:
        hm = ho["marks"]
        lines += ["## Held-out clip", "",
                  "A second recording (stock check, different narrator "
                  "voice) was made after the step prompt and the marking "
                  "rule were fixed. %d true steps, %d model steps, %d "
                  "matched. Start time error median %.2f s, max %.2f s. "
                  "Marks with IoU of at least 0.5: %.0f%% (median IoU "
                  "%.2f). Status counts: %s." % (
                      ho["truth_steps"], ho["model_steps"],
                      ho["truth_steps_matched"],
                      ho["start_error_s"]["median"],
                      ho["start_error_s"]["max"],
                      100 * hm["iou_at_least_0_5_share"], hm["iou_median"],
                      hm["status_counts"]), ""]
    rep = res.get("qa_repeated")
    if rep and len(rep["passed_per_run"]) > 1:
        lines += ["## Variance over repeated runs", "",
                  "Passed per run: %s. Questions that did not pass every "
                  "run: %s." % (", ".join(map(str, rep["passed_per_run"])),
                                ", ".join("%s (%s)" % (k, v) for k, v in
                                          rep["passes_per_question"].items()
                                          if v.split("/")[0] !=
                                          v.split("/")[1]) or "none"), ""]
    rd = res["reading"]
    lines += ["## Chart reading", "",
              "Report chart page (no text layer for the figures), read by "
              "Muse Spark: %d of %d values correct (text origin %s). SAM "
              "regions found on the page: %d." % (
                  rd["values_correct"], rd["values_expected"],
                  rd["text_origin"], rd["sam_regions_on_chart_page"]), ""]
    return "\n".join(lines) + "\n"


def run_qa_repeated(url, n):
    runs = [run_qa(url) for _ in range(n)]
    per = {}
    for run in runs:
        for q in run:
            per.setdefault(q["id"], []).append(q["pass"])
    return {"runs": runs, "passes_per_question": {
        k: "%d/%d" % (sum(v), len(v)) for k, v in per.items()},
        "passed_per_run": [sum(q["pass"] for q in r) for r in runs]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-qa", action="store_true")
    ap.add_argument("--qa-runs", type=int, default=1)
    args = ap.parse_args()
    res = {"run_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "spend_before_usd": round(meta_client.MetaClient().spent(), 4)}
    detect_stats = fresh_db(EVAL_DB)
    if args.no_qa:
        res["qa"] = None
    else:
        rep = run_qa_repeated(EVAL_DB, args.qa_runs)
        res["qa"] = rep["runs"][-1]
        res["qa_repeated"] = {k: v for k, v in rep.items() if k != "runs"}
        res["qa_all_runs"] = rep["runs"]
    res["leak"] = run_leak(EVAL_DB)
    res["conflicts"] = run_conflicts(EVAL_DB, detect_stats)
    res["steps"] = run_steps_and_marks(EVAL_DB)
    res["heldout_clip"] = run_heldout_clip(EVAL_DB)
    res["reading"] = run_reading(EVAL_DB)
    res["spend_after_usd"] = round(meta_client.MetaClient().spent(), 4)
    (REPO / "eval" / "results.json").write_text(json.dumps(res, indent=1))
    md = write_markdown(res)
    # Tables only; docs/eval-result.md adds the hand-written notes.
    (REPO / "eval" / "results.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
