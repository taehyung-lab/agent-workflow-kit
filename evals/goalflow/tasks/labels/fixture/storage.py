"""자료의 읽기와 저장."""
import json
import os
from pathlib import Path


def path():
    return Path(os.environ.get("LABELS_DATA") or Path(__file__).with_name("data.json"))


def load():
    return json.loads(path().read_text(encoding="utf-8"))


def save(data):
    target = path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
