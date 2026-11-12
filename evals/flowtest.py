"""일반 설치 흐름 시험(모델 없음). selftest.sh 가 부른다.

지금 작업 트리의 키트를 임시 커밋으로 만들어 실제 install.sh 로 새 프로젝트에 설치하고, 설치된 독립 검토 실행기(verify.py)를
가짜 검토 하네스로 실제 실행한다. 승인 관문은 없다(v3.1): 검토 입력은 작업 지도 `## 기준`(요청 원문 포함)이나 사용자가 준 요청 원문 파일이다.
확인하는 것: 반환 → 교정 → 새 버전 재검토, 재검토 한도 = 미완료, 미확인(빈 답·하네스 없음·검토자 수정·요청 원문 없음·빈 기준·근거 불완전),
검토자 입력의 독립성(요청 원문·지도 기준, 기준 커밋부터의 변경만, 자기평가 제외), 검토 중 원본·기준·전달한 근거 파일 변경 = 무효, 파이썬 캐시는 제품 아님, 증거 폴더 보존.
가짜 하네스는 정답을 받지 않고, 시험이 정한 판정 줄을 차례로 낸다.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "evals"))
from session import ProjectError, build_project, worktree_kit  # 키트 커밋·프로젝트 만들기·설치는 평가 실행기와 같은 절차를 쓴다
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
    worktree_kit(kit)
    # 2) 제품 프로젝트(언어와 무관한 셸 검사 하나)와 실제 설치(설치 결과는 커밋해 둔다)
    proj = t / "proj"

    def app(proj):
        (proj / "README.md").write_text("# 앱\n검사: bin/test\n")
        (proj / "ui.txt").write_text("button=로그인\nbutton_en=Login\n")
        (proj / "bin").mkdir(); (proj / "bin" / "test").write_text("#!/bin/sh\ngrep -q 'button=로그인하기' ui.txt\n"); (proj / "bin" / "test").chmod(0o755)
        (proj / "notes.txt").write_text("사용자 메모\n")

    try:
        build_project(proj, kit, prepare=app)
        installed = True
    except ProjectError as e:
        installed = False; print(e)
    check("실제 install.sh 설치가 성공하고 검토 실행기가 설치된다", installed and (proj / ".agents/skills/wf-verify/verify.py").is_file())
    def kit_hooks(path):
        d = json.loads(path.read_text()) if path.is_file() else {}
        return {ev: [h.get("command", "") for g in gs for h in g.get("hooks", [])] for ev, gs in d.get("hooks", {}).items()}
    hc, hx = kit_hooks(proj / ".claude/settings.json"), kit_hooks(proj / ".codex/hooks.json")
    check("설치는 승인 관문을 두지 않고, 훅은 Claude 세션 시작 정보 훅(wf-context) 하나뿐이다(Codex 에는 키트 훅 없음)", not (proj / ".agents/skills/wf-design").exists()
          and list(hc) == ["SessionStart"] and len(hc["SessionStart"]) == 1 and "wf-context/context.py" in hc["SessionStart"][0]
          and hx == {} and not (proj / ".codex/hooks.json").exists())
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
    fin = lambda kept, ans, *extra: sh(sys.executable, "-I", str(verifier), "finish", "--round", kept, *extra, cwd=proj, env=base_env, input=ans)

    # 검토에 실제 사용한 원문은 work/ 아래에 있어도 현재성 확인 대상이다.
    source = proj / "work/request.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(REQ)
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")
    pending = prep("--request", str(source))
    source.write_text("로그인 버튼 글자를 '시작하기'로 바꿔 주세요")
    changed = json.loads(fin(pending["kept"], json.dumps(OK, ensure_ascii=False), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("work/ 원문이 검토 중 바뀌면 이전 판정은 현재 완료가 아니다",
          changed.get("state") == "unverified" and changed.get("target_state") == "ok" and changed.get("completion") != "verified")
    (proj / "ui.txt").write_text("button=로그인\nbutton_en=Login\n")

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
    check("교정 뒤 2회차: 새 버전을 다시 판정해 ok. 직접 검사 결과를 받지 않았으면 전체 완료는 가정하지 않는다(unverified, 종료 6)",
          rc == 6 and out.get("state") == "ok" and out.get("round") == 2 and out.get("completion") == "unverified" and out.get("direct_check") is None)
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
    check("Codex 검토 하네스도 같은 실행기·형식으로 판정한다", rc == 6 and out.get("state") == "ok" and out.get("completion") == "unverified" and "| B1 |" in prompt)
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
    r = fin(rdy["kept"], "검토 결과입니다.\n" + json.dumps(OK, ensure_ascii=False), "--check", "PASS")
    o = json.loads(r.stdout.strip().splitlines()[-1])
    check("finish: 검토자의 마지막 답(표준 입력)을 형식대로 판정해 ok, 직접 검사 PASS 와 합쳐 completion=verified",
          r.returncode == 0 and o.get("state") == "ok" and o.get("completion") == "verified" and o.get("direct_check") == "PASS")
    for chk, want in (("FAIL", "check-failed"), ("REVIEW", "needs-review")):
        rd = prep("--map", mpp, "--request", req_file(f"직접 검사 {chk} 시도"))
        r = fin(rd["kept"], json.dumps(OK, ensure_ascii=False), "--check", chk)
        o = json.loads(r.stdout.strip().splitlines()[-1])
        check(f"검토 ok 여도 직접 검사 {chk} 면 completion={want}(완료가 아님, 종료 6)", r.returncode == 6 and o.get("state") == "ok" and o.get("completion") == want)
    rd = prep("--map", mpp, "--request", req_file("직접 검사 없는 finish"))
    r = fin(rd["kept"], json.dumps(OK, ensure_ascii=False))
    o = json.loads(r.stdout.strip().splitlines()[-1])
    check("finish: 검토 ok 여도 --check 가 없으면 종료 6(completion=unverified), 같은 회차를 다시 조회해도 6",
          r.returncode == 6 and o.get("state") == "ok" and o.get("completion") == "unverified" and fin(rd["kept"], "").returncode == 6)
    check("finish --check 에 정해진 값 밖은 사용 오류(종료 2)", fin(prep("--map", mpp, "--request", req_file("잘못된 check"))["kept"], json.dumps(OK), "--check", "maybe").returncode == 2)
    # 요구 기록 표: 미정(사용자 답)·미확인(조사) 행이 남으면 완료가 아니고, 형식이 틀리면 검토자를 띄우지 않고 돌려보낸다
    HEAD = "| ID | 요구(입력→관찰 장소→기대) | 출처·위치 | 의존 | 확인 방법 | 상태 |\n|---|---|---|---|---|---|\n"
    def rec_map(name, rows):
        return write_map(name, f"- 요청 원문: {REQ}\n\n" + HEAD + rows)
    ok_r1 = {"verdict": "OK", "conditions": [{"id": "R1", "result": "충족", "evidence": "bin/test 통과"}], "out_of_scope": []}
    m_open = rec_map("rec-open", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | - | bin/test | 확정 |\n| Q1 | 영어 버튼 문구 | 원문이 정하지 않음 | - | 답 뒤 | 미정 |\n")
    rd = prep("--map", m_open)
    o = json.loads(fin(rd["kept"], json.dumps(ok_r1, ensure_ascii=False), "--check", "PASS").stdout.strip().splitlines()[-1]) if rd.get("state") == "ready" else rd
    check("요구 기록에 미정 행이 남으면 검토 ok·직접 검사 PASS 여도 completion=waiting-user, 미정 행은 검토 필수 조건에서 빠진다",
          o.get("state") == "ok" and o.get("completion") == "waiting-user" and o.get("open_decisions") == ["Q1"] and "Q1" not in o.get("required", []) and "R1" in o.get("required", []))
    rd = prep("--map", m_open, "--request", req_file("미정+실패"))
    o = json.loads(fin(rd["kept"], json.dumps(ok_r1, ensure_ascii=False), "--check", "FAIL").stdout.strip().splitlines()[-1])
    check("미정이 남아도 직접 검사 실패는 감추지 않는다(check-failed)", o.get("completion") == "check-failed")
    m_unk = rec_map("rec-unk", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | - | bin/test | 확정 |\n| F1 | 서버가 문구를 덮어쓰는지 | 조사 필요 | - | 서버 확인 | 미확인 |\n")
    rd = prep("--map", m_unk)
    o = json.loads(fin(rd["kept"], json.dumps(ok_r1, ensure_ascii=False), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("미확인 행이 남으면 completion=unverified", o.get("completion") == "unverified" and o.get("unconfirmed") == ["F1"])
    for name, rows, word in (
        ("rec-dep", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | Q1 | bin/test | 확정 |\n| Q1 | 영어 버튼 문구 | 원문이 정하지 않음 | - | 답 뒤 | 미정 |\n", "의존"),
        ("rec-src", "| R1 | 한국어 버튼 → 화면 → 로그인하기 |  | - | bin/test | 확정 |\n", "출처"),
        ("rec-state", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | - | bin/test | 아마 |\n", "확정·미정·미확인"),
        ("rec-ghost", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | Z9 | bin/test | 확정 |\n", "없다")):
        rd = prep("--map", rec_map(name, rows))
        check(f"요구 기록 형식 문제({name})는 검토자를 띄우지 않고 returned, 사유에 '{word}'",
              rd.get("state") == "returned" and word in rd.get("reason", "") and "prompt_file" not in rd and rd.get("completion") == "returned")
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
    check("1회차 뒤 지도 기준이 바뀌면 2회차 검토자에게 1회차 기준과 바뀐 사실을 알린다(criteria_changed)",
          out.get("round") == 2 and "1회차 검토 뒤 작업 지도의 기준이 바뀌었다" in prompt and "원래 기준" in prompt and "바뀐 기준" in prompt
          and "1회차 검토 뒤" not in a[2] and out.get("criteria_changed") is True)
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
    # 구현자의 실행·보고를 묻는 조건: 보고는 --output 으로 판정 대상에 들어가고, 없으면 검토자가 자기 실행으로 대신 충족시키지 않는다
    check("검토자 지침: 구현자의 행동·보고를 묻는 조건은 기록이 없으면 미확인, 조건 일부를 빼고 충족을 내지 않는다",
          "대신 충족시키지 않고 미확인" in pa and "조건의 일부를 판정 범위에서 빼고" in pa and "완료 보고·실행 기록이면 그 주장이 실행 기록·현재 동작과 맞는지" in pa)
    check("검토자 지침: 기존 보장을 깨는 반례와 목표를 깨는 입력·사건 순서를 모두 미충족 근거로 본다",
          "연결된 기존 보장을 깨는 반례" in pa and "목표가 깨지는 입력·사건 순서" in pa)
    # 구현 diff와 완료 보고를 함께 전달해도 둘 다 검토 입력에 남고, 보고는 판정 대상으로 구분된다.
    report_target = proj / "report-target.txt"; report_target.write_text("REPORT-DIFF-MARKER\n")
    report_request = req_file("변경과 완료 보고를 원문에 맞게 검토해 주세요")
    report_file = req_file("REPORT-OUTPUT-MARKER: 실행 명령과 실제 출력, 확인한 것과 미확인 사항")
    rreport = prep("--request", report_request, "--output", report_file)
    pr = Path(rreport.get("prompt_file", "/x")).read_text() if rreport.get("state") == "ready" else ""
    check("구현 diff와 --output 보고를 함께 전달하고 보고를 판정 대상으로 표시한다",
          rreport.get("state") == "ready" and "REPORT-DIFF-MARKER" in pr and "REPORT-OUTPUT-MARKER" in pr
          and "구현의 완료 보고·실행 기록. 판정 대상이며" in pr and "(바뀐 파일 없음)" not in pr)
    rbare = prep("--request", report_request)
    pb = Path(rbare.get("prompt_file", "/x")).read_text() if rbare.get("state") == "ready" else ""
    check("보고를 안 주면 diff는 남고 보고 산출물 구간은 생기지 않는다",
          rbare.get("state") == "ready" and "REPORT-DIFF-MARKER" in pb and "REPORT-OUTPUT-MARKER" not in pb
          and "## 검토할 산출물(" not in pb)
    report_target.unlink()
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
    # 평가 실행기의 검토 세션(verdict.py session --log): 회차의 원시 기록은 회차 폴더에, --log 는 최신 복사본
    logp = t / "ev" / "x.verify1.jsonl"
    lreq = req_file("기록 위치 시도")
    (proj / "log-change.txt").write_text("검토할 변경\n")
    outs = [verify(mp, [OK], extra=("--request", lreq, "--log", str(logp)))[1] for _ in range(2)]
    first_raw = Path(outs[0].get("kept", "/x")) / "verify.jsonl"
    check("같은 --log 를 두 번 써도 첫 회차의 원시 기록은 그 회차의 고유 폴더에 그대로 있다(--log 는 최신 복사본)",
          first_raw.is_file() and "verdict" in first_raw.read_text() and outs[0].get("kept") != outs[1].get("kept")
          and logp.read_text() == Path(outs[1].get("kept", "/x"), "verify.jsonl").read_text())
    (proj / "log-change.txt").unlink()

    # 두 입력 방식 회귀: 지도 `## 기준` 의 요청 원문 인용, --request 파일, 둘 다.
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\nextra=changed\n")
    quoted_only = write_map("quoted-only", CRIT)
    rd = prep("--map", quoted_only)
    qp = Path(rd.get("prompt_file", "/nonexistent")).read_text() if rd.get("prompt_file") else ""
    check("지도 인용만으로 준비: 원문 인용이 검토 입력에 '옮겨 둔 요청 원문'으로 들어간다",
          rd.get("state") == "ready" and "REQ-MARKER" in qp and "작업 지도 `## 기준` 에 옮겨 둔 요청 원문" in qp)
    path = proj / quoted_only
    path.write_text(path.read_text().replace("REQ-MARKER", "REQ-CHANGED"))
    got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("지도에 옮긴 요청 원문이 검토 중 바뀌면 미확인", got.get("state") == "unverified" and got.get("target_state") == "ok")
    both = write_map("quoted-and-file", CRIT)
    rd = prep("--map", both, "--request", req_file(REQ + " FOLLOWUP-MARKER"))
    bp = Path(rd["prompt_file"]).read_text()
    check("지도 인용과 --request 를 함께 주면 둘 다 원문으로 넘어간다", "REQ-MARKER" in bp and "FOLLOWUP-MARKER" in bp)
    check("지도 자체를 --request 로 주면 원문으로 받지 않는다",
          sh(sys.executable, "-I", str(verifier), "prepare", "--map", both, "--request", str(proj / both), cwd=proj, env=base_env).returncode != 0)

    # 완료한 회차를 다시 읽는 명령도 현재 결과로 오인하게 해서는 안 된다.
    current_source = req_file(REQ + " replay")
    replay = prep("--request", current_source)
    fin(replay["kept"], json.dumps(OK, ensure_ascii=False), "--check", "PASS")
    saved = Path(replay["kept"], "result.json").read_bytes()
    unchanged = json.loads(fin(replay["kept"], json.dumps(RET), "--check", "FAIL").stdout.strip().splitlines()[-1])
    check("완료 회차 재조회는 원래 완료와 직접 검사 결과를 그대로 보존",
          unchanged.get("completion") == "verified" and unchanged.get("direct_check") == "PASS"
          and Path(replay["kept"], "result.json").read_bytes() == saved)
    Path(current_source).write_text("요청이 바뀌었습니다")
    stale = json.loads(fin(replay["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("완료 회차 재조회는 원문 변경을 미확인으로 알리고 과거 기록은 보존",
          stale.get("state") == "unverified" and stale.get("completion") != "verified"
          and Path(replay["kept"], "result.json").read_bytes() == saved)

    for role in ("conditions", "output"):
        evidence = req_file("B1 INPUT-BEFORE")  # 저장소 밖 파일도 실제 입력이면 같은 보장
        args = ("--request", req_file(REQ + role), "--" + role, evidence)
        rd = prep(*args)
        Path(evidence).write_text("B1 INPUT-AFTER")
        got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
        check(f"별도 {role} 입력 변경은 이전 검토를 현재 완료로 만들지 않는다",
              got.get("state") == "unverified" and got.get("target_state") == "ok")

    for section in ("설계", "맥락", "증거"):
        definition = write_map("change-" + section, CRIT)
        path = proj / definition
        path.write_text(f"# 정의\n## 기준\n{CRIT}\n## 설계\nDESIGN-BEFORE\n## 맥락\nCONTEXT-BEFORE\n## 증거\nEVIDENCE-BEFORE\n")
        rd = prep("--map", definition)
        prompt = Path(rd["prompt_file"]).read_text()
        before = {"설계": "DESIGN", "맥락": "CONTEXT", "증거": "EVIDENCE"}[section]
        path.write_text(path.read_text().replace(before + "-BEFORE", before + "-AFTER"))
        got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
        check(f"지도 {section} 변경은 " + ("검토 입력(맥락)이라 현재 검토를 무효화" if section == "맥락" else "검토자에게 넘기지 않은 절이라 판정을 유지"),
              got.get("state") == ("unverified" if section == "맥락" else "ok")
              and "CONTEXT-BEFORE" in prompt and "DESIGN-BEFORE" not in prompt and "EVIDENCE-BEFORE" not in prompt)

    # 검토 후 보고서를 바꾼 경우, 한도에서 예전 OK를 재사용하지 않는다.
    output = req_file("보고: 직접 확인")
    reuse_args = ("--request", req_file(REQ + " reuse"), "--output", output, "--rounds", "1")
    rd = prep(*reuse_args)
    fin(rd["kept"], json.dumps(OK), "--check", "PASS")
    check("한도에서 입력이 같으면 검토 OK만 재사용하고 직접 검사 PASS는 추정하지 않는다",
          (reused := prep(*reuse_args)).get("state") == "ok" and reused.get("completion") == "unverified")
    check("한도에서 재사용한 검토 OK 도 완료가 아니므로 prepare 는 0 으로 끝나지 않는다(종료 6)",
          sh(sys.executable, "-I", str(verifier), "prepare", *reuse_args, cwd=proj, env=base_env).returncode == 6)
    Path(output).write_text("다른 보고서")
    check("한도에서 산출물이 달라지면 이전 OK를 재사용하지 않는다", prep(*reuse_args).get("state") == "incomplete")

    # 구 pending은 현재성 근거가 없으므로 통과로 변환하지 않는다.
    rd = prep("--request", req_file(REQ + " legacy"))
    pending_path = Path(rd["kept"], "pending.json")
    old = json.loads(pending_path.read_text()); old.pop("inputs")
    pending_path.write_text(json.dumps(old))
    got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("입력 지문 없는 구 회차는 미확인", got.get("state") == "unverified")

    request = req_file(REQ + " deleted")
    rd = prep("--request", request)
    Path(request).unlink()
    got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("검토 중 원문 삭제도 미확인", got.get("state") == "unverified")

    # 요구 기록 검사(record): 검토 없이 지도의 요청 원문·표 형식을 보고 전체 완료를 판정한다
    def rec(mp_, *extra):
        r = sh(sys.executable, "-I", str(verifier), "record", "--map", mp_, *extra, cwd=proj, env=base_env)
        return r.returncode, (json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {})
    m_done = rec_map("rec-done", "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | - | bin/test | 확정 |\n")
    before = sorted(str(f) for f in (proj / "work").rglob("*"))
    rc, o = rec(m_done, "--check", "PASS")
    check("record: 요청 원문·표 형식이 맞고 미정·미확인이 없고 직접 검사 PASS 면 검토 없이 completion=verified(종료 0)",
          rc == 0 and o.get("state") == "recorded" and o.get("completion") == "verified" and o.get("direct_check") == "PASS")
    check("record 는 파일을 만들거나 바꾸지 않는다(회차·증거 폴더 없음)", sorted(str(f) for f in (proj / "work").rglob("*")) == before)
    rc, o = rec(m_done)
    check("record: 직접 검사 결과를 받지 않으면 통과로 가정하지 않는다(unverified, 종료 6)", rc == 6 and o.get("state") == "recorded" and o.get("completion") == "unverified")
    for chk, want in (("FAIL", "check-failed"), ("REVIEW", "needs-review")):
        rc, o = rec(m_done, "--check", chk)
        check(f"record: 직접 검사 {chk} 면 completion={want}(종료 6)", rc == 6 and o.get("completion") == want)
    rc, o = rec(m_open, "--check", "PASS")
    check("record: 미정 행이 남으면 직접 검사 PASS 여도 waiting-user(종료 6)", rc == 6 and o.get("state") == "recorded" and o.get("completion") == "waiting-user" and o.get("open_decisions") == ["Q1"])
    check("record: 미정이 남아도 직접 검사 실패는 감추지 않는다", rec(m_open, "--check", "FAIL")[1].get("completion") == "check-failed")
    rc, o = rec(m_unk, "--check", "PASS")
    check("record: 미확인 행이 남으면 unverified(종료 6)", rc == 6 and o.get("completion") == "unverified" and o.get("unconfirmed") == ["F1"])
    rc, o = rec("work/rec-dep/work.md", "--check", "PASS")
    check("record: 표 형식 문제는 returned(종료 3), 미정 목록을 믿지 않는다",
          rc == 3 and o.get("state") == "returned" and o.get("completion") == "returned" and "의존" in o.get("reason", "") and o.get("open_decisions") == [])
    rc, o = rec(write_map("rec-noreq", HEAD + "| R1 | 한국어 버튼 → 화면 → 로그인하기 | 원문 | - | bin/test | 확정 |\n"), "--check", "PASS")
    check("record: 지도에 요청 원문이 없으면 returned", rc == 3 and "요청 원문" in o.get("reason", ""))
    rc, o = rec(write_map("rec-notable", f"- 요청 원문: {REQ}\n\n버튼 문구를 바꾼다\n"), "--check", "PASS")
    check("record: 요구 기록 표가 없으면 returned", rc == 3 and "요구 기록 표" in o.get("reason", ""))
    rc, o = rec("work/no-such/work.md", "--check", "PASS")
    check("record: 지도가 없으면 unverified(종료 5), 완료가 아님", rc == 5 and o.get("completion") == "unverified")
    rc, o = rec(write_map("rec-empty", f"- 요청 원문: {REQ}\n\n" + HEAD), "--check", "PASS")
    check("record: 행이 없는 표는 완료로 세지 않는다(returned)", rc == 3 and o.get("completion") == "returned")
    rc, o = rec(m_done, "--check", "PASS", "--review-required")
    check("record --review-required: 필수 검토 없이는 직접 검사 PASS 여도 완료가 아니다(review-missing, 종료 6)",
          rc == 6 and o.get("state") == "recorded" and o.get("completion") == "review-missing")
    check("record 결과에는 review=off 가 붙어 검토 결과와 구별된다", rec(m_done, "--check", "PASS")[1].get("review") == "off")
    # 평가 관찰: 세션이 record 만 실행했으면 독립 검토를 한 것으로 세지 않는다
    sys.path.insert(0, str(KIT / "evals"))
    import observe, verdict
    def seen(result, rc_):
        log = t / "obs.jsonl"
        log.write_text(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "python3 .agents/skills/wf-verify/verify.py x",
                                                                      "aggregated_output": json.dumps(result, ensure_ascii=False), "exit_code": rc_}}, ensure_ascii=False) + "\n")
        return observe.verify_run(str(log))[0]
    check("평가 관찰: record 의 recorded 는 검토 통과로 읽지 않고, finish 의 ok 는 읽는다",
          seen(rec(m_done, "--check", "PASS")[1], 0) == "none" and seen({"state": "ok", "completion": "verified"}, 0) == "ok")
    check("평가 관찰: 예전 기록의 record 결과(state ok, review off)와 완료가 아닌 record(종료 6)도 검토로 읽지 않는다",
          seen({"state": "ok", "review": "off", "completion": "verified"}, 0) == "none" and seen(rec(m_open, "--check", "PASS")[1], 6) == "none")
    check("평가 관찰: 완료가 아닌 finish ok 는 종료 6(예전 기록은 0)으로 읽고, 맞지 않는 종료 코드는 판정으로 쓰지 않는다",
          seen({"state": "ok", "completion": "unverified"}, 6) == "ok" and seen({"state": "ok", "completion": "unverified"}, 0) == "ok"
          and seen({"state": "ok", "completion": "verified"}, 6) == "unknown" and seen({"state": "returned", "completion": "returned"}, 6) == "unknown")
    ghost = prep("--map", "work/ghost/work.md", "--request", req_file(REQ))
    check("prepare: 없는 지도는 미확인이고 그 옆에 증거 폴더를 만들지 않는다", ghost.get("state") == "unverified" and not (proj / "work/ghost").exists())
    # 평가 실행기의 보조: 작업 시작 상태 커밋은 가지·index·작업 트리를 바꾸지 않고, 지도가 여러 개면 고르지 않는다
    (proj / "untracked-start.txt").write_text("시작 상태\n")
    head_before, status_before = sh(*G, "rev-parse", "HEAD", cwd=proj).stdout, sh(*G, "status", "--porcelain", cwd=proj).stdout
    snap = verdict.snapshot(str(proj))
    check("snapshot: 추적하지 않는 새 파일까지 커밋 하나로 남기고 가지·index 는 그대로다",
          "untracked-start.txt" in sh(*G, "ls-tree", "-r", "--name-only", snap, cwd=proj).stdout
          and sh(*G, "rev-parse", "HEAD", cwd=proj).stdout == head_before and sh(*G, "status", "--porcelain", cwd=proj).stdout == status_before)
    (proj / "untracked-start.txt").unlink()
    rc, out, prompt = verify(None, [OK], extra=("--request", req_file("여러 지도")))
    check("평가 검토 세션: 기준이 있는 지도가 여러 개면 고르지 않고 미확인(검토자를 띄우지 않음)", rc == 5 and "여러 개" in out.get("reason", "") and prompt == "")
    hp = sh(sys.executable, "-I", str(verifier), "record", "--help", cwd=proj, env=base_env)
    check("사용법을 물으면(--help) 사용법을 내고 오류로 끝나지 않는다", hp.returncode == 0 and "record --map" in hp.stderr)
    check("record: --map 이 없거나 --check 값이 틀리면 사용 오류(종료 2)",
          sh(sys.executable, "-I", str(verifier), "record", cwd=proj, env=base_env).returncode == 2 and rec(m_done, "--check", "maybe")[0] == 2)
    check("없어진 평가 전용 옵션은 받지 않는다(--criteria·--base-dir 는 무시되지 않고 쓰이지도 않음: 도구에 흔적이 없다)",
          all(w not in src for w in ("--criteria", "--base-dir", "--plan", "--state", "--keep", "--reviewer", "--answer", "--exit-code", "def final_answer", "def run_result", "def baseline")))

    # 실행이 저절로 만드는 파이썬 캐시(__pycache__·.pyc)는 제품이 아니다. 무시 목록이 없는 프로젝트에서도
    # 구현자·검토자가 검사를 돌려 캐시가 바뀐 것을 대상·원본 변경으로 세지 않는다. 새 소스 파일은 그대로 대상이다.
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")
    cache = proj / "__pycache__"; cache.mkdir(exist_ok=True)
    (cache / "m.cpython-314.pyc").write_bytes(b"\x00cache-before")
    (proj / "extra.pyc").write_bytes(b"\x00loose")
    (proj / "new_source.py").write_text("print('new')\n")
    rd = prep("--request", req_file(REQ + " cache"))
    target = Path(rd["target_dir"])
    check("고정 대상에 파이썬 캐시는 복사하지 않고 새 소스 파일은 복사한다",
          not (target / "__pycache__").exists() and not (target / "extra.pyc").exists() and (target / "new_source.py").is_file())
    (target / "__pycache__").mkdir(exist_ok=True); (target / "__pycache__" / "m.cpython-314.pyc").write_bytes(b"\x00reviewer-run")
    (cache / "m.cpython-314.pyc").write_bytes(b"\x00implementer-run")
    got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("검토자·구현자의 검사 실행이 만든 캐시 변경은 판정을 무효로 만들지 않는다",
          got.get("state") == "ok" and got.get("completion") == "verified")
    rd = prep("--request", req_file(REQ + " source"))
    (Path(rd["target_dir"]) / "new_source.py").write_text("print('reviewer edit')\n")
    got = json.loads(fin(rd["kept"], json.dumps(OK), "--check", "PASS").stdout.strip().splitlines()[-1])
    check("검토자가 새 소스 파일을 바꾸면 여전히 unverified", got.get("state") == "unverified" and "추적 파일" in got.get("reason", ""))
    shutil.rmtree(cache); (proj / "extra.pyc").unlink(); (proj / "new_source.py").unlink()

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
