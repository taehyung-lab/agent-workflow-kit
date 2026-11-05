"""일반 설치 흐름 시험(모델 없음). selftest.sh 가 부른다.

지금 작업 트리의 키트를 임시 커밋으로 만들어 실제 install.sh 로 새 프로젝트에 설치하고, 설치된 독립 검토 실행기(verify.py)를
가짜 검토 하네스로 실제 실행한다. 승인 관문은 없다(v3.1): 검토 입력은 작업 지도 `## 기준`(요청 원문 포함)이나 사용자가 준 요청 원문 파일이다.
확인하는 것: 반환 → 교정 → 새 버전 재검토, 재검토 한도 = 미완료, 미확인(빈 답·하네스 없음·검토자 수정·요청 원문 없음·빈 기준·근거 불완전),
검토자 입력의 독립성(요청 원문·지도 기준, 기준 커밋부터의 변경만, 자기평가 제외), 검토 중 원본·기준 변경 = 무효, 증거 폴더 보존.
가짜 하네스는 정답을 받지 않고, 시험이 정한 판정 줄을 차례로 낸다.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "flow: " + name)


def sh(*cmd, cwd=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, capture_output=True, text=True)


G = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "-c", "commit.gpgsign=false"]
OK = {"verdict": "OK", "conditions": [{"id": "B1", "result": "충족", "evidence": "bin/test 실행 결과: 로그인하기"},
                                      {"id": "E1", "result": "충족", "evidence": "영어 화면 Login 그대로"}], "out_of_scope": []}
RET = {"verdict": "RETURN", "conditions": [{"id": "B1", "result": "미충족", "evidence": "버튼 글자가 아직 로그인"}],
       "return_reason": "B1 미충족. 진행해 주세요."}
REQ = "로그인 버튼 글자를 '로그인하기'로 바꿔 주세요"
CRIT = (f"- 요청 원문:\n  > {REQ} REQ-MARKER\n"
        "| B1 | 한국어 화면 버튼이 '로그인하기' | bin/test |\n| [기존] E1 | 영어 버튼 Login 그대로 | 대조 |")

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    # 1) 지금 작업 트리의 키트를 커밋으로 만든다(설치기는 커밋된 키트만 설치한다)
    kit = t / "kit"
    for rel in ["install.sh", "AGENTS.md", "CLAUDE.md"]:
        (kit / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(KIT / rel, kit / rel)
    shutil.copytree(KIT / ".agents" / "skills", kit / ".agents" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    sh(*G, "init", "-q", cwd=kit); sh(*G, "add", "-A", cwd=kit); sh(*G, "commit", "-qm", "kit", cwd=kit)
    # 2) 제품 프로젝트(언어와 무관한 셸 검사 하나)와 실제 설치
    proj = t / "proj"; proj.mkdir()
    (proj / "README.md").write_text("# 앱\n검사: bin/test\n")
    (proj / "ui.txt").write_text("button=로그인\nbutton_en=Login\n")
    (proj / "bin").mkdir(); (proj / "bin" / "test").write_text("#!/bin/sh\ngrep -q 'button=로그인하기' ui.txt\n"); (proj / "bin" / "test").chmod(0o755)
    (proj / "notes.txt").write_text("사용자 메모\n")
    sh(*G, "init", "-q", cwd=proj); sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "app", cwd=proj)
    r = sh("bash", str(kit / "install.sh"), str(proj))
    check("실제 install.sh 설치가 성공하고 검토 실행기가 설치된다", r.returncode == 0 and (proj / ".agents/skills/wf-verify/verify.py").is_file())
    def kit_hooks(path):
        d = json.loads(path.read_text()) if path.is_file() else {}
        return {ev: [h.get("command", "") for g in gs for h in g.get("hooks", [])] for ev, gs in d.get("hooks", {}).items()}
    hc, hx = kit_hooks(proj / ".claude/settings.json"), kit_hooks(proj / ".codex/hooks.json")
    check("설치는 승인 관문을 두지 않고, 훅은 세션 시작 정보 훅(wf-context) 하나뿐이다", not (proj / ".agents/skills/wf-design").exists()
          and list(hc) == ["SessionStart"] and list(hx) == ["SessionStart"] and len(hc["SessionStart"]) == 1 and len(hx["SessionStart"]) == 1
          and "wf-context/context.py" in hc["SessionStart"][0] and "wf-context/context.py" in hx["SessionStart"][0])
    sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "kit", cwd=proj)
    verifier = proj / ".agents/skills/wf-verify/verify.py"

    def write_map(name, crit, evidence=""):
        mp = proj / "work" / name / "work.md"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(f"# {name}\n\n## 기준\n\n{crit}\n\n## 증거\n\n{evidence}\n")
        return f"work/{name}/work.md"

    def req_file(text):
        f = Path(tempfile.mkstemp(dir=t, suffix=".txt")[1]); f.write_text(text); return str(f)

    # 3) 가짜 하네스: 검토자 프롬프트를 남기고, 시험이 정한 판정 줄을 차례로 낸다
    fake = t / "bin"; fake.mkdir()
    for name, fmt in (("claude", '{"type": "result", "result": %s}'), ("codex", '{"type": "item.completed", "item": {"type": "agent_message", "text": %s}}')):
        (fake / name).write_text(f"""#!/bin/sh
for a in "$@"; do case "$a" in *"당신은 별도 검증자다"*) p="$a";; esac; done
[ -n "$p" ] || exit 1
n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/n"
printf '%s' "$p" > "$FAKE_DIR/vprompt.$n"
[ -z "${{FAKE_VWRITE:-}}" ] || echo changed >> ui.txt
[ -z "${{FAKE_TOUCH_ORIG:-}}" ] || echo changed-while-verifying >> "$FAKE_TOUCH_ORIG"
line=$(sed -n "${{n}}p" "$FAKE_DIR/verdicts")
printf '{fmt}\\n' "$line"
exit 0
""")
        (fake / name).chmod(0o755)
    base_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}

    def verify(mp, verdicts, harness="claude", path=True, extra=(), **env):
        d = Path(tempfile.mkdtemp(dir=t)); (d / "verdicts").write_text("".join(json.dumps(json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v, ensure_ascii=False) + "\n" for v in verdicts))
        e = {**base_env, "FAKE_DIR": str(d), "PATH": (f"{fake}:" if path else "") + "/usr/bin:/bin", **env}
        r = sh(sys.executable, "-I", str(KIT / "evals/verdict.py"), "session", "--tool", str(verifier), "--harness", harness, *(("--map", mp) if mp else ()), *extra, cwd=proj, env=e)
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        prompt = (d / "vprompt.1").read_text() if (d / "vprompt.1").is_file() else ""
        return r.returncode, out, prompt

    prep = lambda *a: json.loads(sh(sys.executable, "-I", str(verifier), "prepare", *a, cwd=proj, env=base_env).stdout.strip().splitlines()[-1])
    fin = lambda kept, ans: sh(sys.executable, "-I", str(verifier), "finish", "--round", kept, cwd=proj, env=base_env, input=ans)

    # 4) 지도(요청 원문 포함) → 구현 → 검토. 작업 전 사용자 변경은 커밋해 두었으므로(기준 커밋 HEAD) diff 에 섞이지 않는다
    (proj / "notes.txt").write_text("사용자 메모(작업 전 변경)\n"); sh(*G, "commit", "-qam", "user", cwd=proj)
    mp = write_map("login", CRIT, "SELF-ASSESS-MARKER 전부 충족")
    (proj / "ui.txt").write_text("button=로그인 버튼\nbutton_en=Login\n")  # 첫 구현(틀림)
    rc, out, prompt = verify(mp, [RET])
    check("1회차: 검토자가 돌려보내면 returned(종료 3), 완료가 아님", rc == 3 and out.get("state") == "returned" and out.get("completion") == "returned" and out.get("round") == 1)
    check("검토자 입력: 지도에 옮긴 요청 원문과 지도 기준(B1·E1)이 들어가고 B1 이 필수 조건",
          "REQ-MARKER" in prompt and "작업 지도 `## 기준` 에 옮겨 둔 요청 원문" in prompt and "| B1 |" in prompt and "B1" in out.get("required", []))
    check("검토자 입력: 지도의 증거(자기평가)는 넣지 않는다", "SELF-ASSESS-MARKER" not in prompt)
    check("검토자 입력의 diff: 기준 커밋부터의 변경만(커밋해 둔 작업 전 변경 제외)", "로그인 버튼" in prompt and "사용자 메모" not in prompt)
    check("회차 기록은 지도 옆 verify/ 에 남는다", json.loads((proj / "work/login/verify/state.json").read_text())["rounds"][0]["state"] == "returned")
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")  # 교정
    (proj / "extra.txt").write_text("새 파일\n"); (proj / "README.md").unlink()
    rc, out, prompt = verify(mp, [OK])
    check("교정 뒤 2회차: 새 버전을 다시 판정해 ok(종료 0), 완료=verified", rc == 0 and out.get("state") == "ok" and out.get("round") == 2 and out.get("completion") == "verified")
    check("2회차 diff 에 교정 내용·새 파일·지운 파일이 보인다", "button=로그인하기" in prompt and "extra.txt" in prompt and "README.md" in prompt)
    (proj / "README.md").write_text("# 앱\n검사: bin/test\n"); (proj / "extra.txt").unlink()
    rc, out, prompt = verify(mp, [OK], harness="codex")
    check("한도에 닿은 뒤에는 새 검토자를 띄우지 않는다(제품이 바뀌었으면 incomplete)", out.get("state") == "incomplete" and prompt == "")
    # 새 시도(요청 원문이 다르면 1회차부터). 한도 2 는 그 시도의 첫 회차에 정해진다
    r2 = req_file("영어 문구는 그대로 두세요 AFTER-MARKER")
    a = verify(mp, [RET], extra=("--request", r2)); b = verify(mp, [RET], extra=("--request", r2)); rc, out, prompt = verify(mp, [OK], extra=("--request", r2, "--rounds", "5"))
    check("새 요청 원문은 새 시도(1회차부터); RETURN·RETURN(한도 2) 뒤에는 --rounds 를 올려도 검토자를 띄우지 않고 incomplete",
          a[1].get("round") == 1 and [a[1].get("state"), b[1].get("state"), out.get("state")] == ["returned", "incomplete", "incomplete"] and prompt == "")
    check("--request 로 준 뒤 메시지도 사용자 원문으로 들어간다", "AFTER-MARKER" in a[2] and "REQ-MARKER" in a[2])
    rc, out, prompt = verify(mp, [OK], harness="codex", extra=("--request", req_file("codex 시도")))
    check("Codex 검토 하네스도 같은 실행기·형식으로 판정한다", rc == 0 and out.get("state") == "ok" and "| B1 |" in prompt)
    # 미확인
    rc, out, _ = verify(mp, [""], extra=("--request", req_file("빈 답 시도")))
    check("빈 답은 unverified(종료 5), 완료가 아님", rc == 5 and out.get("state") == "unverified" and out.get("completion") == "unverified")
    rc, out, _ = verify(mp, [OK], path=False, extra=("--request", req_file("하네스 없음 시도")))
    check("검토 하네스가 없으면 성공처럼 넘기지 않고 unverified", rc == 5 and "찾지 못했다" in out.get("reason", ""))
    rc, out, _ = verify(mp, [OK], FAKE_VWRITE="1", extra=("--request", req_file("검토자 수정 시도")))
    check("검토자가 판정 대상 파일을 바꾸면 그 판정은 unverified", rc == 5 and "추적 파일" in out.get("reason", ""))
    rc, out, _ = verify(mp, [OK], FAKE_TOUCH_ORIG=str(proj / "ui.txt"), extra=("--request", req_file("원본 변경 시도")))
    check("검토 중 원본 파일이 바뀌면 unverified(고정 대상 판정은 target_state 로 보존)", out.get("state") == "unverified" and out.get("target_state") == "ok")
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")
    mpm = write_map("m6", f"- 요청 원문: {REQ}\n| B1 | 한국어 화면 버튼이 '로그인하기' |")
    (proj / mpm).write_text((proj / mpm).read_text().split("## 증거")[0].rstrip() + "\n")  # 기준이 마지막 절(가짜 하네스가 끝에 덧붙이면 기준이 바뀐다)
    rc, out, _ = verify(mpm, [OK], FAKE_TOUCH_ORIG=str(proj / mpm))
    check("검토 중 원본 지도의 기준이 바뀌면 unverified", out.get("state") == "unverified" and "지도 기준" in out.get("reason", ""))
    # 입력 부족: 요청 원문이 없으면 요약한 계획으로 대신하지 않는다
    mpn = write_map("no-req", "| B1 | 한국어 화면 버튼이 '로그인하기' |")
    rc, out, prompt = verify(mpn, [OK])
    check("지도 기준에 요청 원문이 없고 --request 도 없으면 입력 부족으로 unverified(검토자를 띄우지 않음)",
          rc == 5 and "요청 원문을 확보하지 못했다" in out.get("reason", "") and prompt == "")
    rc, out, prompt = verify(mpn, [OK], extra=("--request", req_file(REQ + " FILE-REQ")))
    check("같은 지도라도 사용자가 준 요청 원문 파일(--request)이 있으면 그 원문으로 판정한다", out.get("state") == "ok" and "FILE-REQ" in prompt and "| B1 |" in prompt)
    rq = prep("--request", req_file(REQ + " CONV-REQ"))
    pq = Path(rq.get("prompt_file", "/x")).read_text() if rq.get("state") == "ready" else ""
    check("지도 없는 작업도 요청 원문 파일과 기준 커밋부터의 변경으로 검토 입력을 만든다", "CONV-REQ" in pq and "기준 커밋 HEAD" in pq)
    rn = prep()
    check("지도도 요청 원문도 없으면 입력 부족으로 unverified", rn.get("state") == "unverified" and "입력 부족" in rn.get("reason", ""))
    mpe = proj / "work" / "empty" / "work.md"; mpe.parent.mkdir(parents=True, exist_ok=True); mpe.write_text("# 작업\n## 기준\n\n## 설계\n나중에\n")
    re_ = prep("--map", "work/empty/work.md", "--request", req_file(REQ))
    check("지도의 기준 본문이 비면 입력 부족으로 unverified", re_.get("state") == "unverified" and "기준` 이 비었다" in re_.get("reason", ""))
    shutil.rmtree(mpe.parent)
    rb = prep("--request", req_file(REQ), "--base", "no-such-ref")
    check("기준 커밋을 찾지 못하면 unverified", rb.get("state") == "unverified" and "기준 커밋" in rb.get("reason", ""))
    # 일반 작업 경로: 하네스 하위 에이전트가 검토자. prepare 가 입력을 묶고, 구현자가 검토자의 마지막 답을 finish 에 넘긴다(모델 세션을 띄우지 않음).
    mpp = write_map("sub", CRIT)
    rdy = prep("--map", mpp)
    check("prepare: 모델을 띄우지 않고 검토 입력(prompt_file)과 판정 대상 폴더를 낸다",
          rdy.get("state") == "ready" and "| B1 |" in Path(rdy["prompt_file"]).read_text() and Path(rdy["target_dir"]).is_dir()
          and str(rdy["target_dir"]) in Path(rdy["prompt_file"]).read_text())
    r = fin(rdy["kept"], "검토 결과입니다.\n" + json.dumps(OK, ensure_ascii=False))
    o = json.loads(r.stdout.strip().splitlines()[-1])
    check("finish: 검토자의 마지막 답(표준 입력)을 형식대로 판정해 ok, completion=verified", r.returncode == 0 and o.get("state") == "ok" and o.get("completion") == "verified")
    r2_ = fin(rdy["kept"], json.dumps(RET, ensure_ascii=False))
    check("같은 회차를 다시 finish 해도 판정을 바꾸지 않는다(새 회차는 prepare 로)", json.loads(r2_.stdout.strip().splitlines()[-1]).get("state") == "ok")
    rdy = prep("--map", mpp); (Path(rdy["target_dir"]) / "ui.txt").write_text("changed\n")
    o = json.loads(fin(rdy["kept"], json.dumps(OK, ensure_ascii=False)).stdout.strip().splitlines()[-1])
    check("검토자가 판정 대상을 바꾸면 그 OK 는 unverified", o.get("state") == "unverified" and "추적 파일" in o.get("reason", ""))
    rdy = prep("--map", mpp, "--request", req_file("세 번째 시도")); (proj / "ui.txt").write_text("button=검토 중 바뀜\nbutton_en=Login\n")
    o = json.loads(fin(rdy["kept"], json.dumps(OK, ensure_ascii=False)).stdout.strip().splitlines()[-1])
    check("검토하는 동안 원본이 바뀌면 과거 대상의 OK 는 무효(unverified)", o.get("state") == "unverified" and o.get("target_state") == "ok")
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")
    src = verifier.read_text(encoding="utf-8")
    check("설치되는 검토 실행기는 모델 세션을 띄우지 않고 관문에 기대지 않는다",
          "subprocess.run(cmd, cwd=vdir" not in src and "def call_harness" not in src and "approval-gate" not in src)
    # 1회차 뒤 기준이 바뀌면: 검토자에게 1회차 기준과 함께 알리고 원문과 대조하게 한다
    mpg = write_map("g", f"- 요청 원문: {REQ}\n| B1 | 원래 기준 |")
    a = verify(mpg, [RET]); write_map("g", f"- 요청 원문: {REQ}\n| B1 | 바뀐 기준 |"); rc, out, prompt = verify(mpg, [OK])
    check("1회차 뒤 지도 기준이 바뀌면 2회차 검토자에게 1회차 기준과 바뀐 사실을 알린다(baseline_changed)",
          out.get("round") == 2 and "1회차 검토 뒤 작업 지도의 기준이 바뀌었다" in prompt and "원래 기준" in prompt and "바뀐 기준" in prompt
          and "1회차 검토 뒤" not in a[2] and out.get("baseline_changed_after_approval") is True)
    # 맥락 봉투: 지도의 `## 맥락`과 맥락 도구가 관찰한 대상 저장소 정보가 검토 입력에 들어간다(증거·자기평가는 여전히 제외)
    mpc = proj / "work" / "ctx" / "work.md"; mpc.parent.mkdir(parents=True, exist_ok=True)
    mpc.write_text(f"# ctx\n\n## 기준\n\n- 요청 원문: {REQ}\n| B1 | 한국어 화면 버튼이 '로그인하기' |\n\n## 맥락\n\n- 대상: 이 저장소 ENVELOPE-MARKER\n- 근거: ../old-app (과거 비교만)\n\n## 증거\n\nSELF-ASSESS-MARKER\n")
    rdy = prep("--map", "work/ctx/work.md")
    pc = Path(rdy.get("prompt_file", "/x")).read_text() if rdy.get("state") == "ready" else ""
    check("검토 입력: 지도 `## 맥락`(봉투)과 맥락 도구의 관찰(실경로·브랜치)이 들어가고 증거는 빠진다",
          "ENVELOPE-MARKER" in pc and "과거 비교만" in pc and f"실경로: {os.path.realpath(proj)}" in pc and "브랜치:" in pc and "SELF-ASSESS-MARKER" not in pc)
    check("검토자 지침: 다른 대상·과거 자료를 현재 사실로 전제했거나 결정·시나리오와 어긋나면 RETURN", "다른 저장소·버전·과거 자료를 현재 사실로 전제" in pc)
    # 분석만 한 작업: 바뀐 파일이 없으면 --output 산출물이 판정 대상. 둘 다 없으면 입력 부족
    sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "clean", cwd=proj)
    rnone = prep("--request", req_file("로그인 흐름을 분석해 주세요"))
    check("바뀐 파일도 산출물도 없으면 입력 부족으로 unverified", rnone.get("state") == "unverified" and "검토할 것이 없다" in rnone.get("reason", ""))
    outf = req_file("분석: 이 저장소 ui.txt 의 button=로그인하기 ANALYSIS-MARKER")
    rana = prep("--request", req_file("로그인 흐름을 분석해 주세요"), "--output", outf)
    pa = Path(rana.get("prompt_file", "/x")).read_text() if rana.get("state") == "ready" else ""
    check("분석만 한 작업: --output 산출물로 검토 입력을 만들고(diff 없음 표시), 산출물이 원문·맥락에 맞는지 보라고 지시한다",
          "ANALYSIS-MARKER" in pa and "(바뀐 파일 없음)" in pa and "검토할 산출물" in pa and "산출물의 대상·전제·인용·권고" in pa)
    o = json.loads(fin(rana["kept"], json.dumps(OK, ensure_ascii=False)).stdout.strip().splitlines()[-1]) if rana.get("state") == "ready" else {}
    check("분석만 한 작업도 같은 형식으로 finish 판정(ok)", o.get("state") == "ok")
    rempty = prep("--request", req_file("분석"), "--output", req_file("   "))
    check("빈 산출물은 입력 부족으로 unverified", rempty.get("state") == "unverified" and "비었다" in rempty.get("reason", ""))
    # 근거 불완전
    (proj / "big.txt").write_text("x" * 70000 + "\n")
    rc, out, prompt = verify(mp, [OK], extra=("--request", req_file("큰 diff")))
    check("diff 가 잘리면 근거 불완전으로 unverified(검토자를 띄우지 않음)", out.get("state") == "unverified" and "diff" in out.get("reason", "") and prompt == "")
    (proj / "big.txt").unlink()
    hooks = t / "fail-hooks"; hooks.mkdir(); (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n"); (hooks / "pre-commit").chmod(0o755)
    rc, out, prompt = verify(mp, [OK], GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0=str(hooks), extra=("--request", req_file("고정 실패")))
    check("판정 대상 고정(git commit)이 실패하면 unverified(검토자를 띄우지 않음)", rc == 5 and "고정 실패" in out.get("reason", "") and prompt == "")
    # 증거 보존
    rq1 = req_file("증거 시도 1")
    rc, out1, _ = verify(mp, [RET], extra=("--request", rq1))
    k1 = Path(out1.get("kept", "/nonexistent")); r1 = (k1 / "result.json").read_text() if (k1 / "result.json").is_file() else None
    rc, out2, _ = verify(mp, [OK], extra=("--request", req_file("증거 시도 2")))
    k2 = Path(out2.get("kept", "/nonexistent"))
    check("새 시도의 검토는 다른 증거 폴더에 남고, 앞선 시도의 target·diff·result 는 그대로다",
          out2.get("round") == 1 and k2 != k1 and k2.is_dir() and r1 is not None and (k1 / "result.json").read_text() == r1
          and (k1 / "diff.txt").is_file() and sh("git", "cat-file", "-e", f"{out1.get('target')}^{{commit}}", cwd=k1 / "target").returncode == 0)
    check("증거 폴더는 제품 파일 목록에 섞이지 않는다(work/ 아래)", Path(os.path.realpath(proj / "work")) in Path(os.path.realpath(k1)).parents)
    user_dir = t / "my-keep"; user_dir.mkdir(); (user_dir / "note.txt").write_text("사용자 파일\n")
    rc, out3, _ = verify(mp, [OK], extra=("--keep", str(user_dir), "--request", req_file("keep 시도")))
    check("--keep 에 준 기존 폴더의 파일은 지우지 않고 그 안에 새 하위 폴더를 만든다",
          (user_dir / "note.txt").read_text() == "사용자 파일\n" and Path(out3.get("kept", "/x")).parent == user_dir)
    # 평가 실행기 방식(--request·--base-dir·--log): --log 옆 .round 폴더의 기존 내용도 보존한다
    req = t / "req.txt"; req.write_text("로그인 버튼 글자를 바꿔 주세요\n"); basedir = t / "base-dir"; basedir.mkdir()
    logp = t / "ev" / "x.verify1.jsonl"; (t / "ev" / "x.verify1.round").mkdir(parents=True); (t / "ev" / "x.verify1.round" / "old.txt").write_text("앞 실행\n")
    outs = []
    for i in range(2):
        d = Path(tempfile.mkdtemp(dir=t)); (d / "verdicts").write_text(json.dumps(json.dumps(OK, ensure_ascii=False), ensure_ascii=False) + "\n")
        r = sh(sys.executable, "-I", str(KIT / "evals/verdict.py"), "session", "--tool", str(verifier), "--harness", "claude", "--request", str(req), "--base-dir", str(basedir),
               "--state", str(t / f"ev-state-{i}.json"), "--log", str(logp), cwd=proj, env={**base_env, "FAKE_DIR": str(d), "PATH": f"{fake}:/usr/bin:/bin"})
        outs.append(json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {})
    first_raw = Path(outs[0].get("kept", "/x")) / "verify.jsonl"
    check("같은 --log 를 두 번 써도 첫 회차의 원시 기록은 그 회차의 고유 폴더에 그대로 있다(--log 는 최신 복사본)",
          first_raw.is_file() and "verdict" in first_raw.read_text() and Path(outs[1].get("kept", "/x"), "verify.jsonl").is_file()
          and logp.read_text() == Path(outs[1]["kept"], "verify.jsonl").read_text())
    check("--log 방식도 같은 보장: 기존 .round 내용 보존, 실행마다 다른 새 폴더",
          (t / "ev" / "x.verify1.round" / "old.txt").read_text() == "앞 실행\n" and len({o.get("kept") for o in outs}) == 2
          and all(Path(o.get("kept", "/x")).is_dir() and Path(o["kept"]).parent == t / "ev" / "x.verify1.round" for o in outs))

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
