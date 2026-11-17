"""모의 사용자의 판단: 에이전트의 글이 과제의 주제(<과제>/topics.txt) 가운데 무엇을 구현 전에 사용자에게 드러냈는가.

드러냈다는 것은 그 주제에 대해 아직 구현하지 않은 동작을 말한 것이다: 결정을 물었거나, 추천을 붙여 승인을 구했거나,
"이렇게 두고 진행하겠다"고 선언했거나, 미정으로 남겼다. 실제 사용자라면 그 글을 보고 자기 정책과 다르면 고쳐 준다.
이미 구현했다고만 보고한 주제와 언급하지 않은 주제는 답 전 발견으로 세지 않는다. 정책 전체의 전달은 conversation.py가 맡는다.
모델은 주제마다 그 문장을 글에서 그대로 옮기고, 옮긴 문장이 실제 글에 있는지 확인한다. 인용이 다르거나 주제별 판정이 빠졌으면 분류 실패로 남겨 REVIEW로 보낸다. 모델은 evals/pins.json 의 mock_user 로 고정한다. 저장된 답으로 분류를 확인하는 표본은 asked-samples/ 에 있다(asked_samples.py).
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pins  # noqa: E402

PROMPT = """아래는 코딩 에이전트가 사용자에게 보낸 글이다. 주제마다, 에이전트가 그 주제의 동작을 아직 구현하지 않은 채 사용자에게 드러낸 문장을 글에서 글자 그대로 하나 옮긴다.
드러냈다는 것: 결정을 물었다, 추천을 붙여 승인을 구했다, "이렇게 두고 진행하겠다"처럼 정한 값을 확인받으려고 적었다, 미정으로 남겼다. 질문 문장이 아니어도 된다.
옮기지 않는 것(null): 이미 구현했다고만 보고한 주제, 언급하지 않은 주제, "위 질문에 답해 달라"처럼 내용 없이 가리키기만 한 글. 주제 목록 아래의 덧붙임이 있으면 그 구분을 따른다.

주제:
{topics}

답은 JSON 한 줄만. 주제 번호마다 옮긴 문장 또는 null: {{"quotes": {{"1": "…", "2": null}}}}

에이전트의 글:
<<<
{reply}
>>>"""


def _plain(text):
    """인용 대조용: 꾸밈 기호와 공백 차이를 없앤다."""
    return re.sub(r"[\s*`_>\-•]+", "", text)


def surfaced(reply, topics, record_dir=None):
    """주제별 실제 인용을 반환한다. 실행·형식 오류는 대화가 REVIEW로 보존할 수 있게 알린다."""
    reply = reply[:12000]
    numbers = {int(n) for n in re.findall(r"^(\d+)\.", topics, re.M)}
    prompt = PROMPT.format(topics=topics, reply=reply)
    evidence = None
    if record_dir is not None:
        Path(record_dir).mkdir(parents=True, exist_ok=True)
        evidence = Path(tempfile.mkdtemp(prefix='call-', dir=record_dir))
        (evidence / 'prompt.txt').write_text(prompt, encoding='utf-8')
    try:
        with tempfile.TemporaryDirectory() as directory:
            r = subprocess.run(["claude", "-p", prompt, "--model", pins.mock_user_model(), "--safe-mode", "--max-turns", "1"],
                               cwd=directory, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        if evidence:
            (evidence / 'error.txt').write_text(str(e), encoding='utf-8')
            for name in ('stdout', 'stderr'):
                raw = getattr(e, name, None) or b''
                (evidence / (name + '.txt')).write_bytes(raw.encode('utf-8') if isinstance(raw, str) else raw)
            (evidence / 'execution.json').write_text(json.dumps({'model': pins.mock_user_model(), 'exit_code': None,
                'status': 'timeout' if isinstance(e, subprocess.TimeoutExpired) else 'execution-error'}))
        raise RuntimeError('모의 사용자 실행 실패: ' + str(e)) from e
    if evidence:
        (evidence / 'stdout.txt').write_text(r.stdout, encoding='utf-8')
        (evidence / 'stderr.txt').write_text(r.stderr, encoding='utf-8')
        (evidence / 'execution.json').write_text(json.dumps({'model': pins.mock_user_model(), 'exit_code': r.returncode}))
    m = re.search(r'\{\s*"quotes"\s*:\s*\{.*\}\s*\}', r.stdout, re.S)
    if r.returncode or not m:
        raise RuntimeError("모의 사용자 판단 실패: " + (r.stdout + r.stderr)[-300:])
    try:
        quotes = json.loads(m.group(0))["quotes"]
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError('모의 사용자 답 형식 오류: ' + str(e)) from e
    expected = {str(n) for n in numbers}
    reason = None
    if not isinstance(quotes, dict) or set(quotes) != expected:
        reason = '모든 주제에 인용문 또는 null이 필요하다'
    else:
        body = _plain(reply)
        invalid = [key for key, quote in quotes.items()
                   if quote is not None and
                   (not isinstance(quote, str) or len(_plain(quote)) < 4 or _plain(quote) not in body)]
        if invalid:
            reason = '원문과 대조할 수 없는 인용: 주제 ' + ', '.join(sorted(invalid))
    if reason:
        if evidence:
            (evidence / 'validation-error.txt').write_text(reason, encoding='utf-8')
        raise RuntimeError('모의 사용자 판단 근거 오류: ' + reason)
    return {int(key): quote for key, quote in sorted(quotes.items()) if quote is not None}

def asked(reply, topics):
    """드러낸 주제 번호 목록(surfaced 의 주제만)."""
    return sorted(surfaced(reply, topics))


if __name__ == "__main__":
    import glob
    topics = (Path(sys.argv[2]) / "topics.txt").read_text(encoding="utf-8")  # 사용: asked.py <결과 폴더> <과제 폴더>
    for f in sorted(glob.glob(sys.argv[1] + "/*-1.json")):
        s = json.load(open(f))
        print(s["name"], [asked(t["reply"], topics) for t in s["turns"][:2]])
