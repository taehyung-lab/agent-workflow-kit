"""모의 사용자의 판단: 에이전트의 답이 세 정책 가운데 무엇을 사용자에게 물었는가(또는 미정으로 남겼는가)."""
import json, re, subprocess, sys, tempfile
TOPICS = """1. 옛 신청 기록: 이미 저장돼 있는 중복·충돌·정원 초과 기록을 어떻게 다룰지(같은 요청 ID 에 행이 여럿일 때 무엇을 확정으로 안내할지, 재시도·정원 계산을 어떻게 할지)
2. 같은 회원의 재신청: 이미 확정된 회원이 같은 회차를 '다른(새) 요청 ID' 로 다시 신청하면 어떻게 할지
3. 새 요청 ID 연결: 2번처럼 새 요청 ID 로 기존 확정을 안내했을 때 그 새 ID 를 기존 확정에 연결해 저장할지(그 ID 로 조회·다른 회원이 그 ID 를 쓸 때)"""
PROMPT = """아래는 코딩 에이전트가 사용자에게 보낸 답이다. 다음 세 주제 각각에 대해, 에이전트가 사용자에게 결정을 물었거나(추천을 붙였어도 됨) 사용자 답이 필요한 미정으로 남겼으면 그 번호를 고른다.
에이전트가 스스로 정해서 이미 구현했다고만 보고한 주제, 언급하지 않은 주제는 고르지 않는다. 같은 요청 ID 의 '같은 회원·회차 재시도'나 '같은 ID 를 다른 회원이 쓰는 경우'는 2번이 아니다(2번은 같은 회원이 새 ID 로 다시 신청하는 경우만).

주제:
{topics}

답은 JSON 한 줄만: {{"asked": [번호들]}}

에이전트의 답:
<<<
{reply}
>>>"""

def asked(reply):
    d = tempfile.mkdtemp()
    r = subprocess.run(["claude", "-p", PROMPT.format(topics=TOPICS, reply=reply[:12000]), "--model", "haiku", "--safe-mode", "--max-turns", "1"],
                       cwd=d, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    m = re.search(r'\{\s*"asked"\s*:\s*\[([^\]]*)\]\s*\}', r.stdout)
    if not m:
        raise RuntimeError("모의 사용자 판단 실패: " + (r.stdout + r.stderr)[-300:])
    return sorted({int(x) for x in re.findall(r"[123]", m.group(1))})

if __name__ == "__main__":
    import glob
    for f in sorted(glob.glob(sys.argv[1] + "/*-1.json")):
        s = json.load(open(f))
        print(s["name"], [asked(t["reply"]) for t in s["turns"][:2]])
