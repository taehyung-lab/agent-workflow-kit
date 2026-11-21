"""대표 작업 기록과 실제 검사. record → check → review; work.md는 읽기용이다.

원문·계획 변경·실행 증거는 journal.jsonl에 추가한다. 파일 잠금은 동시 기록을
직렬화한다. 해시는 손상 탐지용이며 파일 소유자에 대한 보안 장치가 아니다.
"""
import argparse
import fcntl
import hashlib
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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'wf-ask'))
import verify
import situations


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
        for source in event.get('sources', []) + event.get('evidence', []):
            if digest((work / source['file']).read_bytes()) != source['sha256']:
                raise ValueError('원문 또는 보존한 증거 파일이 기록 뒤 바뀌었다')
    return events


def current(events):
    plan = None
    for event in events:
        if 'plan' in event:
            plan = json.loads(json.dumps(event['plan']))
        if event.get('findings') and plan:
            plan['requirements'].extend(json.loads(json.dumps(event['findings'])))
    return plan


def pending_choices(events):
    """미정이 생긴 당시의 출처를 보존한다. 계획 교체는 사용자 답이 아니다."""
    pending, known, count = {}, set(), 0
    for event in events:
        known.update(source['sha256'] for source in event.get('sources', []))
        count += len(event.get('sources', []))
        for requirement in event.get('plan', {}).get('requirements', []) + event.get('findings', []):
            key = requirement['id']
            if requirement['state'] == '미정':
                pending.setdefault(key, (set(known), count))
            else:
                pending.pop(key, None)
    return pending


def resolution_context(plan):
    lines = ['# 미정으로 남긴 선택의 근거 정정', '',
             '사용자 답이 필요한 선택인지, 기존 원문·계약이 이미 결과를 정하는지 제안 계획과 대조한다.',
             '새 정책을 고르는 승인이 아니다. 기존 근거가 결과를 정할 때만 충족이며 근거 문장을 인용한다.',
             '이번 검토 대상은 요구 해소 계획이며 아직 구현되지 않은 기능의 완료 판정이 아니다.', '']
    lines += [f"{r['id']} {r['expect']}" for r in plan['requirements'] if r['state'] == '미정']
    lines += ['', '현재 요구 원본:', json.dumps(plan, ensure_ascii=False, sort_keys=True)]
    return '\n'.join(lines) + '\n'


def reviewed_choices(work, plan, events, kept):
    if not kept:
        return set()
    keep = Path(kept).resolve()
    pending = json.loads((keep / 'pending.json').read_text())
    result, code = call_verify(['finish', '--round', str(keep), '--check', 'PASS'])
    if code != 0 or result.get('completion') != 'verified':
        raise ValueError('미정 정정의 독립 검토가 현재 근거로 통과하지 않았다')
    files = pending['inputs']['files']
    if not any(f['role'] == 'output' and validate(json.loads(Path(f['path']).read_text()),
                   max(n for r in plan['requirements'] for n in r['source'])) == plan
               for f in files if f['role'] == 'output'):
        raise ValueError('독립 검토가 이번 계획을 대조하지 않았다')
    requests = {digest(Path(f['path']).read_bytes()) for f in files if f['role'] == 'request'}
    if not {s['sha256'] for s in sources(events)} <= requests:
        raise ValueError('독립 검토에 현재 사용자 원문이 모두 없다')
    # 검토 입력 자체에 미정 목록을 포함해야 다른 작업의 통과를 재사용하지 못한다.
    context = work / 'resolution-context.md'
    if not any(Path(f['path']).resolve() == context.resolve() and f['sha256'] == digest(resolution_context(current(events)).encode())
               for f in files):
        raise ValueError('독립 검토가 현재 미정 상태를 대조하지 않았다')
    return {c['id'] for c in result['conditions'] if c['result'] == '충족'}


def preserve_choices(events, plan, source_items, reviewed=()):
    requirements = {r['id']: r for r in plan['requirements']}
    for key, (original_sources, original_count) in pending_choices(events).items():
        if key not in requirements:
            raise ValueError(f'{key}: 미정인 선택을 다음 계획에서 지울 수 없다')
        requirement = requirements[key]
        if requirement['state'] != '미정':
            if key not in reviewed and not any(source_items[n - 1]['sha256'] not in original_sources or
                       (n > original_count and key in source_items[n - 1].get('reply_to', [])) for n in requirement['source']):
                raise ValueError(f'{key}: 미정 해소에는 새 사용자 답의 출처가 필요하다')


def sources(events):
    return [s for e in events for s in e.get('sources', [])]


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE, text=True).strip()


def validate(plan, count):
    if type(plan.get('review_required', True)) is not bool:
        raise ValueError('review_required는 참·거짓이어야 한다')
    targets, problems = verify.review_targets([(t['name'], t['path'], t['base']) for t in plan['targets']], Path.cwd())
    if problems:
        raise ValueError(' / '.join(problems))
    for target, validated in zip(plan['targets'], targets):
        target.update(path=str(validated['root']), base=validated['sha'])
    names = {t['name'] for t in targets}
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
        by = req.get('decided_by')
        if by:
            refs += f" — {by['kind']}{' ' + by['file'] if by.get('file') else ''} “{by['quote']}”"
        lines.append(f"| {req['id']} | {cell(req['expect'])} | {refs} | | {commands} | {req['state']} |")
    (work / 'resolution-context.md').write_text(resolution_context(plan))
    (work / 'work.md').write_text('\n'.join(lines) + '\n')


def record(work, args, events):
    if not args.request and not args.plan and not args.findings and not args.evidence:
        raise ValueError('추가할 원문·계획·독자 발견·증거가 필요하다')
    previous = sources(events)
    incoming = [Path(path).read_bytes() for path in args.request]
    attachments = [(str(Path(path).resolve()), Path(path).read_bytes()) for path in args.evidence]
    if any(not raw.strip() for raw in incoming):
        raise ValueError('빈 원문은 기록하지 않는다')
    plan = validate(json.loads(Path(args.plan).read_text()), len(previous) + len(incoming)) if args.plan else current(events)
    if args.reply_to and (not incoming or not set(args.reply_to) <= set(pending_choices(events))):
        raise ValueError('--reply-to는 새 사용자 원문과 현재 미정 질문 ID가 필요하다')
    if args.resolution_review and incoming:
        raise ValueError('새 원문을 먼저 기록한 뒤 현재 원문 전체로 독립 검토해야 한다')
    if args.plan:
        reviewed = reviewed_choices(work, plan, events, args.resolution_review)
        preserve_choices(events, plan, previous + [{'sha256': digest(raw), 'reply_to': args.reply_to} for raw in incoming], reviewed)
    elif args.resolution_review:
        raise ValueError('독립 검토로 미정을 정정할 계획이 필요하다')
    findings = json.loads(Path(args.findings).read_text()) if args.findings else []
    if not isinstance(findings, (list, dict)):
        raise ValueError('독자 발견은 상황 배열 또는 상태 × 명령 표여야 한다')
    if findings:
        if not plan:
            raise ValueError('독자 발견을 더할 현재 계획이 필요하다')
        # 독자는 찾은 상황을 모두 넘긴다. 확정은 그 결과를 말하는 인용이 원문·합의 문서에 있을 때만 남고, 아니면 미정이 된다.
        texts = [(work / s['file']).read_text(encoding='utf-8') for s in previous] + [raw.decode('utf-8') for raw in incoming]
        sorted_out = situations.classify(findings, texts, [Path(t['path']) for t in plan['targets']])
        if sorted_out['missing']:
            raise ValueError(f"상태 × 명령 표에 상황이 없는 칸이 있다: {sorted_out['missing']}")
        findings = sorted_out['settled'] + sorted_out['open']
        validate({'targets': plan['targets'], 'requirements': findings, 'checks': []}, len(previous) + len(incoming))
        existing = {r['id'] for r in plan['requirements']}
        if any(r['id'] in existing for r in findings):
            raise ValueError('독자 발견은 현재 요구와 겹치지 않는 새 ID여야 한다')
    # 미정 해소 출처는 기록한다. 답의 의미는 독립 검토에서도 대조한다.
    event = {'kind': 'record', 'time': time.time(), 'sources': []}
    for raw in incoming:
        index = len(previous) + len(event['sources']) + 1
        name = f'sources/{index:04}.txt'
        (work / 'sources').mkdir(exist_ok=True)
        with (work / name).open('xb') as stream:
            stream.write(raw)
        event['sources'].append({'file': name, 'sha256': digest(raw), 'reply_to': args.reply_to})
    event['evidence'] = []
    count = sum(len(e.get('evidence', [])) for e in events)
    for origin, raw in attachments:
        name = f'evidence/{count + len(event["evidence"]) + 1:04}.txt'
        (work / 'evidence').mkdir(exist_ok=True)
        with (work / name).open('xb') as stream:
            stream.write(raw)
        event['evidence'].append({'file': name, 'sha256': digest(raw), 'origin': origin})
    if args.plan:
        event['plan'] = plan
    if findings:
        event['findings'] = findings
    append(work, event); events.append(event); render(work, events)
    result = {'state': 'recorded', 'sources': len(sources(events)), 'map': str(work / 'work.md')}
    if findings:
        result['demoted'] = sorted_out['demoted']
    return result, 0


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
    for run in candidates:
        for item in run['results']:
            if digest(Path(item['output']).read_bytes()) != item['sha256']:
                raise ValueError('현재 또는 과거 검사 출력이 바뀌었다')
    return result


def call_verify(argv, answer=None, record_path=None):
    outcome = (verify.prepare_review(argv[1:], record_path=record_path) if argv[0] == 'prepare'
               else verify.finish_review(argv[1:], answer or ''))
    for message in outcome.messages:
        print(message, file=sys.stderr)
    return outcome.result, outcome.code


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
    # 과거 실패는 당시 요구·명령과 함께 전달하며 현재 PASS를 대신하지 않는다.
    frozen['history'] = json.loads(json.dumps([e for e in events if e['kind'] in ('record', 'check') and e is not evidence]))
    for run in [frozen] + [e for e in frozen['history'] if e['kind'] == 'check']:
        for item in run['results']:
            item['stdout_stderr'] = Path(item['output']).read_text(encoding='utf-8', errors='replace')
    for event in frozen['history']:
        for item in event.get('evidence', []):
            item['content'] = (work / item['file']).read_text(encoding='utf-8', errors='replace')
    bundle.write_bytes(encoded(frozen))
    record_path = work / 'review-input.json'
    record_path.write_bytes(encoded(plan))
    command = ['prepare', '--output', str(bundle)]
    for source in sources(events):
        command += ['--request', str(work / source['file'])]
    result, code = call_verify(command, record_path=record_path)
    if code == 0:
        append(work, {'kind': 'review', 'context': context_key(events), 'kept': result['kept'], 'check': digest(encoded(evidence))})
    return result, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'check', 'review'])
    parser.add_argument('work', type=Path)
    parser.add_argument('--request', action='append', default=[])
    parser.add_argument('--plan')
    parser.add_argument('--reply-to', action='append', default=[], help='새 사용자 답이 해소하는 미정 질문 ID')
    parser.add_argument('--resolution-review', help='새 답 없이 잘못 표시한 미정을 정정할 독립 검토 회차 경로')
    parser.add_argument('--findings', help='독자가 반환한 상황 배열(확정은 인용 출처를 확인하고, 없으면 미정으로 기록)')
    parser.add_argument('--evidence', action='append', default=[], help='원문과 구분해 보존할 실제 검사·관찰 증거 파일')
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
