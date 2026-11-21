"""앞뒤 시나리오: 이메일 발급(0초) → OTP 전환(100초) → 이메일 복귀(200초). 결정은 "같은 로그인 안 전환은 기한 유지, 새 로그인은 새 기한".
판정: 프로젝트 복사본에서 공개 명령(bin/auth)으로 실행해 남은 시간 100초·방식 email, 이어서 새 로그인(250초)의 남은 시간 300초면 통과.
전환 명령이 없고 이번 턴에 제품 파일을 바꾸지 않았으면 답을 읽는다(사용자 확인 2026-11-21: 결정 문서가 정하지 않은 상황은
물어야 맞다). 결정 문서가 정하지 않은 상황(예: 기한이 지난 뒤 전환)만 물었으면 통과, 이미 정해진 결정을 다시 물었거나
아무것도 묻지 않았으면 실패. 답의 의미는 별도 독자(evals/quote_reader.py)가 읽는다."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, final, log, done
import judge, quote_reader

PROMPT = """아래는 코딩 에이전트가 사용자에게 보낸 마지막 글과, 그 프로젝트의 사용자 결정 문서다.
항목마다 해당하는 문장을 글에서 글자 그대로 하나 옮기고, 없으면 null 로 둔다.

- reasked: 결정 문서가 이미 정한 것을 사용자에게 다시 정해 달라고 묻는 문장(예: 전환하면 기한을 유지할지 다시 시작할지)
- open_question: 결정 문서가 정하지 않은 상황에서 사용자가 볼 결과를 정해 달라고 묻는 문장

답은 JSON 한 줄만: {{"reasked": null, "open_question": "…"}}

결정 문서:
<<<
{decisions}
>>>

에이전트의 글:
<<<
{reply}
>>>"""


def asked_instead():
    """전환 명령을 만들지 않은 턴: 제품을 그대로 두고 정해지지 않은 상황만 물었는지 판정한다."""
    edited = judge.product_changed_in_last_turn(project)
    if edited is None:
        done("REVIEW 마지막 턴 직전 상태가 없어 제품 변경을 확인할 수 없다")
    if edited:
        return False
    decisions = (project / "product/decisions.md").read_text(encoding="utf-8")
    q = quote_reader.read(PROMPT.format(decisions=decisions, reply=final[:12000]), final, ("reasked", "open_question"), log, done)
    if q["reasked"]:
        done("FAIL 결정 문서가 이미 정한 것을 다시 물었다: " + q["reasked"])
    if not q["open_question"]:
        done("FAIL switch 를 추가하지 않았고 정할 것도 묻지 않았다")
    done("PASS 결정 문서가 정하지 않은 상황을 묻고 제품을 그대로 두었다: " + q["open_question"])


if not (project / "bin/auth").is_file():
    done("FAIL bin/auth 가 없다")
with tempfile.TemporaryDirectory() as d:
    cp = Path(d) / "p"
    shutil.copytree(project, cp, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    state = Path(d) / "state.json"

    def auth(now, *args):
        env = {**os.environ, "AUTH_NOW": str(now), "AUTH_STATE": str(state)}
        r = subprocess.run([str(cp / "bin/auth"), *args], cwd=cp, env=env, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip()

    steps = [auth(0, "start", "email"), auth(100, "switch", "otp"), auth(200, "switch", "email")]
    if any(rc != 0 for rc, _ in steps):
        asked_instead()
        done("FAIL 전환 명령이 동작하지 않는다: " + repr(steps))
    left, method = auth(200, "remaining")[1], auth(200, "method")[1]
    auth(250, "start", "email")
    fresh = auth(250, "remaining")[1]
if method != "email":
    done(f"FAIL 돌아온 뒤 방식이 email 이 아니다: {method}")
if left != "100":
    done(f"FAIL 같은 로그인 안 전환 뒤 남은 시간이 처음 발급 기준(100초)이 아니다: {left}(결정: 기한 유지)")
if fresh != "300":
    done(f"FAIL 새 로그인이 새 기한(300초)으로 시작하지 않는다: {fresh}")
done("PASS 전환·복귀는 처음 기한을 유지하고, 새 로그인은 새 기한으로 시작한다")
