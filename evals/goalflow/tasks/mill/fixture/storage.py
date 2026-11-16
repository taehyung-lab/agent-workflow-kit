import json
import os
from pathlib import Path


def path():
    return Path(os.environ.get("MILL_DATA", Path(__file__).with_name("data.json")))


def load():
    return json.loads(path().read_text(encoding="utf-8"))


def save(data):
    path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
