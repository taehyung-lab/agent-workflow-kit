import json,sys,glob
for f in sorted(glob.glob(sys.argv[1]+"/*.json")):
    if f.endswith(".oracle.json"): continue
    s=json.load(open(f)); t=s["turns"]
    print(f'{s["name"]:16} valid={s["automated_valid"]!s:5} fail={len(s["failed"]):2}/{s["n_cases"]} unobs={len(s["unobserved"])} pub={s["public_tests_rc"]} map={s["map"]!s:5} sec={s["seconds"]:5} | '
          + " ".join(f't{r["turn"]}:ans{r.get("answered_now","")},rc{r["rc"]},{r["seconds"]}s,edit{len(r["product_changes"])},?{r["question_marks"]},rec{r["record_runs"]},rev{r["review_runs"]}' for r in t) + f' | init={s["init"]} err={str(s["oracle_error"])[:80] if s["oracle_error"] else ""}')
    if "-v" in sys.argv: print("    failed:", s["failed"])
