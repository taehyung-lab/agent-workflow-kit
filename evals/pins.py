"""평가 실행의 고정값(pins.json): 하네스마다 CLI 버전과 모델, 모의 사용자가 주제를 고르는 모델.

같은 조건에서 돈 결과끼리만 비교할 수 있게 한다. 실제 CLI 버전이 고정값과 다르면 실행을 시작하지 않는다(check).
CLI 를 올렸으면 pins.json 을 고친 커밋으로 다시 재고, 그 전 결과와는 비교 불가로 다룬다(report.py).
"""
import json, os, subprocess
from pathlib import Path

# EVALS_PINS: 다른 고정 파일(자체 시험의 가짜 하네스용). 없으면 evals/pins.json.
PINS = json.loads(Path(os.environ.get("EVALS_PINS") or Path(__file__).resolve().parent / "pins.json").read_text(encoding="utf-8"))


def model(harness):
    return PINS[harness]["model"]


def mock_user_model():
    return PINS["mock_user"]


def flags(harness):
    """하네스에 모델을 넘기는 옵션."""
    return ["--model", model(harness)] if harness == "claude" else ["-m", model(harness)]


def cli_version(harness):
    try:
        out = subprocess.run([harness, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    except OSError:
        return ""
    return out.split("\n")[0].strip()


def check(harness):
    """실제 CLI 버전이 고정값과 다르면 사유 문자열, 같으면 None."""
    got, want = cli_version(harness), PINS[harness]["cli"]
    return None if got == want else f"{harness} CLI 버전 {got or '(없음)'} 이 고정값 {want} 과 다르다(evals/pins.json)"
