"""대표 작업 기록과 실제 검사. record → check → review; work.md는 읽기용이다.

원문·계획 변경·실행 증거는 journal.jsonl에 추가한다. 파일 잠금은 동시 기록을
직렬화한다. 해시는 손상 탐지용이며 파일 소유자에 대한 보안 장치가 아니다.
"""
import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def append(work, event):
    with (work / 'journal.jsonl').open('ab') as stream:
        stream.write(encoded(event) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def load(work):
    path = work / 'journal.jsonl'
    events = [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []
    for event in events:
        for source in event.get('sources', []):
            if digest((work / source['file']).read_bytes()) != source['sha256']:
                raise ValueError('원문 파일이 기록 뒤 바뀌었다')
    return events


def current(events):
    plans = [e['plan'] for e in events if 'plan' in e]
    return plans[-1] if plans else None


def sources(events):
    return [s for e in events for s in e.get('sources', [])]


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE, text=True).strip()


def validate(plan, count):
    if type(plan.get('review_required', True)) is not bool:
        raise ValueError('review_required는 참·거짓이어야 한다')
    names = set()
    paths = set()
    for target in plan['targets']:
        name = target['name']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or name in names:
            raise ValueError('대상 이름은 중복 없는 영숫자·밑줄·하이픈이어야 한다')
        root = Path(target['path']).expanduser().resolve()
        if str(root) != git(root, 'rev-parse', '--show-toplevel') or str(root) in paths:
            raise ValueError('대상은 서로 다른 Git 작업 폴더 최상위여야 한다')
        target['path'] = str(root)
        target['base'] = git(root, 'rev-parse', '--verify', target['base'] + '^{commit}')
        names.add(name); paths.add(str(root))
    if not names:
        raise ValueError('작업 대상이 없다')
    ids = set()
    for req in plan['requirements']:
        if not re.fullmatch(r'[A-Z]{1,3}[0-9]{1,3}', req['id']) or req['id'] in ids:
            raise ValueError('요구 ID가 잘못되거나 중복됐다')
        if not req['expect'].strip() or req['state'] not in verify.RECORD_STATES:
            raise ValueError('기대값 또는 상태가 잘못됐다')
        if not req['source'] or any(type(s) is not int or s < 1 or s > count for s in req['source']):
            raise ValueError('요구가 존재하는 원문 번호를 가리켜야 한다')
        ids.add(req['id'])
    if not ids:
        raise ValueError('요구가 없다')
    checks = set()
    for check in plan['checks']:
        if check['id'] in checks or not re.fullmatch(r'[A-Za-z0-9_-]+', check['id']):
            raise ValueError('검사 ID가 잘못되거나 중복됐다')
        if check['target'] not in names or not check['requirements'] or not set(check['requirements']) <= ids:
            raise ValueError('검사의 대상·요구 연결이 잘못됐다')
        if not isinstance(check['argv'], list) or not check['argv'] or any(not isinstance(a, str) for a in check['argv']):
            raise ValueError('검사 명령은 문자열 배열이어야 한다')
        if not 0 < check.get('timeout', 300) <= 3600:
            raise ValueError('검사 시간 제한은 0초 초과 3600초 이하다')
        checks.add(check['id'])
    return plan


def render(work, events):
    plan = current(events)
    if not plan:
        return
    cell = lambda text: str(text).replace('|', '&#124;').replace('\n', '<br>')
    lines = ['# 작업 지도 (기록에서 생성)', '', '## 맥락', '', '| 대상 | 경로 | 기준 커밋 |', '| --- | --- | --- |']
    lines += [f"| {t['name']} | {t['path']} | {t['base']} |" for t in plan['targets']]
    lines += ['', '## 기준', '', '요청 원문은 sources/의 번호별 파일. 전체 파일을 검토에 전달한다.', '', '| ID | 요구 | 출처·위치 | 의존 | 확인 방법 | 상태 |', '| --- | --- | --- | --- | --- | --- |']
    for req in plan['requirements']:
        commands = ', '.join(c['id'] for c in plan['checks'] if req['id'] in c['requirements']) or '미확인'
        refs = ', '.join(f'sources/{n:04}.txt' for n in req['source'])
        lines.append(f"| {req['id']} | {cell(req['expect'])} | {refs} | | {commands} | {req['state']} |")
    (work / 'work.md').write_text('\n'.join(lines) + '\n')


def record(work, args, events):
    if not args.request and not args.plan:
        raise ValueError('추가할 원문 또는 계획이 필요하다')
    previous = sources(events)
    incoming = [Path(path).read_bytes() for path in args.request]
    if any(not raw.strip() for raw in incoming):
        raise ValueError('빈 원문은 기록하지 않는다')
    plan = validate(json.loads(Path(args.plan).read_text()), len(previous) + len(incoming)) if args.plan else current(events)
    # 계획을 바꿔도 이전 계획은 남는다. 원문 번호는 해석의 근거이지 승인 자동 판독이 아니다.
    event = {'kind': 'record', 'time': time.time(), 'sources': []}
    for raw in incoming:
        index = len(previous) + len(event['sources']) + 1
        name = f'sources/{index:04}.txt'
        (work / 'sources').mkdir(exist_ok=True)
        with (work / name).open('xb') as stream:
            stream.write(raw)
        event['sources'].append({'file': name, 'sha256': digest(raw)})
    if args.plan:
        event['plan'] = plan
    append(work, event); events.append(event); render(work, events)
    return {'state': 'recorded', 'sources': len(sources(events)), 'map': str(work / 'work.md')}, 0


def fingerprint(plan):
    return {t['name']: {'product': verify.product_print(Path(t['path'])),
                       'head': git(t['path'], 'rev-parse', 'HEAD'),
                       'kit': (Path(t['path']) / verify.KIT_VERSION_FILE).read_text() if (Path(t['path']) / verify.KIT_VERSION_FILE).exists() else None}
            for t in plan['targets']}


def context_key(events):
    return digest(encoded([e for e in events if e['kind'] == 'record']))


def status(plan, check):
    return verify.completion('off', check, any(r['state'] == '미정' for r in plan['requirements']),
                             required=plan.get('review_required', True), unresolved=any(r['state'] == '미확인' for r in plan['requirements']))


def check(work, args, events):
    plan = current(events)
    if not plan:
        raise ValueError('요구와 검사 계획이 없다')
    if any(r['state'] != '확정' for r in plan['requirements']):
        return {'check': 'UNVERIFIED', 'completion': status(plan, 'UNVERIFIED')}, 6
    before = fingerprint(plan)
    run_dir = work / 'checks' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    results = []
    targets = {t['name']: t['path'] for t in plan['targets']}
    for command in plan['checks']:
        output = run_dir / (command['id'] + '.txt')
        item = {'id': command['id'], 'argv': command['argv'], 'cwd': targets[command['target']],
                'output': str(output), 'requirements': command['requirements']}
        with output.open('wb') as stream:
            try:
                process = subprocess.Popen(command['argv'], cwd=item['cwd'], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=command.get('timeout', 300))
                    item.update(code=code, state='PASS' if code == 0 else 'FAIL')
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
                    item.update(state='UNVERIFIED', reason='시간 초과')
            except OSError as exc:
                item.update(state='UNVERIFIED', reason=str(exc))
        item['sha256'] = digest(output.read_bytes())
        results.append(item)
    after = fingerprint(plan)
    covered = {r for c in plan['checks'] for r in c['requirements']}
    outcome = 'FAIL' if any(r['state'] == 'FAIL' for r in results) else 'PASS'
    if before != after or covered != {r['id'] for r in plan['requirements']} or any(r['state'] == 'UNVERIFIED' for r in results):
        outcome = 'UNVERIFIED'
    event = {'kind': 'check', 'context': context_key(events), 'before': before, 'after': after,
             'check': outcome, 'results': results, 'completion': status(plan, outcome)}
    append(work, event)
    return event, 0 if event['completion'] == 'verified' else 6


def checked(events, plan):
    candidates = [e for e in events if e['kind'] == 'check']
    if not candidates:
        raise ValueError('실행한 검사가 없다')
    result = candidates[-1]
    if result['context'] != context_key(events) or result['after'] != fingerprint(plan):
        raise ValueError('검사 뒤 원문·계획·대상이 바뀌었다')
    for item in result['results']:
        if digest(Path(item['output']).read_bytes()) != item['sha256']:
            raise ValueError('검사 출력이 바뀌었다')
    return result


def call_verify(argv, answer=None):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        old = sys.stdin
        try:
            if answer is not None:
                sys.stdin = io.StringIO(answer)
            code = verify.cli(argv)
        finally:
            sys.stdin = old
    return json.loads(output.getvalue().splitlines()[-1]), code


def review(work, args, events):
    plan = current(events)
    if not plan:
        raise ValueError('요구 계획이 없다')
    evidence = checked(events, plan)
    if evidence['check'] != 'PASS':
        return {'completion': status(plan, evidence['check']), 'check': evidence['check']}, 6
    if args.answer:
        prepared = [e for e in events if e['kind'] == 'review']
        if not prepared or prepared[-1]['context'] != context_key(events) or prepared[-1].get('check') != digest(encoded(evidence)):
            raise ValueError('현재 기록으로 준비한 검토가 없다')
        return call_verify(['finish', '--round', prepared[-1]['kept'], '--check', evidence['check']], Path(args.answer).read_text())
    render(work, events)
    bundle = work / 'check-evidence.json'
    frozen = json.loads(json.dumps(evidence))
    for item in frozen['results']:
        item['stdout_stderr'] = Path(item['output']).read_text(encoding='utf-8', errors='replace')
    bundle.write_bytes(encoded(frozen))
    command = ['prepare', '--map', str(work / 'work.md'), '--output', str(bundle)]
    for source in sources(events):
        command += ['--request', str(work / source['file'])]
    result, code = call_verify(command)
    if code == 0:
        append(work, {'kind': 'review', 'context': context_key(events), 'kept': result['kept'], 'check': digest(encoded(evidence))})
    return result, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'check', 'review'])
    parser.add_argument('work', type=Path)
    parser.add_argument('--request', action='append', default=[])
    parser.add_argument('--plan')
    parser.add_argument('--answer')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    with (work / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result, code = {'record': record, 'check': check, 'review': review}[args.command](work, args, load(work))
        except Exception as exc:
            result, code = {'completion': 'unverified', 'reason': str(exc)}, 5
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
