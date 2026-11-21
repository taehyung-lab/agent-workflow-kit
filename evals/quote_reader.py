"""사례 판정의 별도 독자: 에이전트의 마지막 글에서 항목마다 문장을 글자 그대로 옮기게 하고, 옮긴 문장이 글에 실제로 있는지 본다.

  read(prompt, reply, keys, log, done) -> {항목: 문장 또는 None}

독자는 evals/pins.json 의 mock_user 모델을 고정 CLI 로 부른다. 표본 시험은 독자의 답을 EVALS_READER_REPLY 로 넣어
모델 없이 판정 경로를 확인한다. 독자가 답을 고쳐 여러 번 내면 비어 있는 항목이 모두 같을 때만 같은 판정으로 보고
원문에서 확인되는 답을 쓴다. 판정할 수 없으면 done("REVIEW …")로 사람에게 넘긴다.
"""
import json, os, re, subprocess, tempfile
from pathlib import Path

import pins


def plain(text):
    return re.sub(r"[\s*`_>\-•\"'“”‘’]+", "", text)


def _ask(prompt, log, done):
    record = Path(log).with_suffix(".reader")
    record.mkdir(parents=True, exist_ok=True)
    (record / "prompt.txt").write_text(prompt, encoding="utf-8")
    # 독자도 고정한 CLI 에서만 읽는다. 버전이 다르면 에이전트의 실패가 아니므로 사람이 보게 넘긴다.
    (record / "cli-version.txt").write_text(pins.cli_version("claude") + "\n", encoding="utf-8")
    mismatch = pins.check("claude")
    if mismatch:
        done("REVIEW 독자를 고정 조건에서 실행하지 못했다: " + mismatch)
    command = ["claude", "-p", prompt, "--model", pins.mock_user_model(), "--safe-mode", "--max-turns", "1"]
    with tempfile.TemporaryDirectory() as directory:
        if os.environ.get("EVALS_BUDGET_FILE"):
            from session import classify
            r = classify(command, directory)
        else:
            r = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    (record / "stdout.txt").write_text(r.stdout, encoding="utf-8")
    (record / "stderr.txt").write_text(r.stderr, encoding="utf-8")
    if r.returncode:
        done("REVIEW 독자 실행 실패: " + (r.stdout + r.stderr)[-300:])
    return r.stdout


def read(prompt, reply, keys, log, done):
    raw = os.environ.get("EVALS_READER_REPLY")
    if raw is None:
        raw = _ask(prompt, log, done)
    answers, decoder = [], json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        try:
            value, _ = decoder.raw_decode(raw, m.start())
        except ValueError:
            continue
        if isinstance(value, dict) and set(value) == set(keys):
            answers.append(value)
    if not answers:
        done("REVIEW 독자 답 형식 오류: " + raw[-300:])
    empty = lambda a: {k for k, q in a.items() if q is None}
    if any(empty(a) != empty(answers[0]) for a in answers[1:]):
        done("REVIEW 독자가 서로 다른 답을 여러 개 냈다: " + raw[-300:])
    body = plain(reply)

    def bad(quotes):
        return [k for k, q in quotes.items() if q is not None and (not isinstance(q, str) or len(plain(q)) < 4 or plain(q) not in body)]
    for quotes in answers:
        if not bad(quotes):
            return quotes
    done("REVIEW 독자가 옮긴 문장이 답에 없다: " + ", ".join(bad(answers[0])))
