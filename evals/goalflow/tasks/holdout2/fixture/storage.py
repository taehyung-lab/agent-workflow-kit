"""의류 자료 읽기와 저장."""
import json
import os
from pathlib import Path

def path():
    return Path(os.environ.get('SUSEON_DATA', Path(__file__).with_name('data.json')))

def read():
    return json.loads(path().read_text(encoding='utf-8'))

def write(data):
    path().write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
