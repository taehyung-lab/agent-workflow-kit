"""모의 사용자의 판단: 에이전트의 답이 과제의 주제(<과제>/topics.txt) 가운데 무엇을 사용자에게 물었는가(또는 미정으로 남겼는가)."""
import json, re, subprocess, sys, tempfile
PROMPT = """아래는 코딩 에이전트가 사용자에게 보낸 답이다. 다음 주제 각각에 대해, 에이전트가 사용자에게 결정을 물었거나(추천을 붙였어도 됨) 사용자 답이 필요한 미정으로 남겼으면 그 번호를 고른다.
에이전트가 스스로 정해서 이미 구현했다고만 보고한 주제, 언급하지 않은 주제는 고르지 않는다. 주제 목록 아래의 덧붙임이 있으면 그 구분을 따른다.

주제:
{topics}

답은 JSON 한 줄만: {{"asked": [번호들]}}

에이전트의 답:
<<<
{reply}
>>>"""

def asked(reply, topics):
    d = tempfile.mkdtemp()
    r = subprocess.run(["claude", "-p", PROMPT.format(topics=topics, reply=reply[:12000]), "--model", "haiku", "--safe-mode", "--max-turns", "1"],
                       cwd=d, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    m = re.search(r'\{\s*"asked"\s*:\s*\[([^\]]*)\]\s*\}', r.stdout)
    if not m:
        raise RuntimeError("모의 사용자 판단 실패: " + (r.stdout + r.stderr)[-300:])
    return sorted({int(x) for x in re.findall(r"\d+", m.group(1))})

if __name__ == "__main__":
    import glob
    from pathlib import Path
    topics = (Path(sys.argv[2]) / "topics.txt").read_text(encoding="utf-8")  # 사용: asked.py <결과 폴더> <과제 폴더>
    for f in sorted(glob.glob(sys.argv[1] + "/*-1.json")):
        s = json.load(open(f))
        print(s["name"], [asked(t["reply"], topics) for t in s["turns"][:2]])
