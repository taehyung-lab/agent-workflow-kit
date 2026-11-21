"""저장된 goalflow 원문과 독립 판독 인용을 대조해 별도 근거를 보존한다.

python3 -I evals/goalflow/discovery_review.py <summary.json> \
    --quotes <quotes.json> --reader <판독자 식별> --method <독립 판독 방법>
quotes.json: {"quotes": {"1": "원문 그대로의 문장", "2": null}}
각 정책에 인용 또는 null이 필요하다. 첫 턴, 정정 과제는 static_turns 전체를 읽는다.
문자열 대조는 인용의 존재만 확인한다. 발견의 의미 판단은 명시된 판독자가 맡는다.
기존 실행의 summary/meta/원점수는 바꾸지 않는다. 결과는 reviews/의 별도 근거다.
종료: 0=인용 근거 확인, 1=인용 거절, 2=원문 또는 당시 기준 미확인.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transcript
sys.path.insert(0, str(Path(__file__).resolve().parent))
from table import discovery_scope


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def preserve(path, destination):
    raw = path.read_bytes()
    destination.write_bytes(raw)
    return raw


def read_original(log, directory, number, evidence):
    """손상 줄을 건너뛰지 않는다. 고정 사본을 공용 기록 해석기로 읽는다."""
    snapshot = directory / f'turn-{number}.jsonl'
    raw = preserve(log, snapshot)
    evidence.update(snapshot=snapshot.name, sha256=digest(raw))
    lines = [line for line in raw.decode('utf-8').splitlines() if line.strip()]
    if not lines or any(not isinstance(json.loads(line), dict) for line in lines):
        raise ValueError('원문 사건이 비어 있거나 객체가 아니다')
    replies = transcript.replies(snapshot)
    if not replies or any(not isinstance(reply, str) for reply in replies):
        raise ValueError('사용자에게 보낸 원문을 읽을 수 없다')
    text = directory / f'turn-{number}-replies.txt'
    text.write_text('\n\n'.join(replies), encoding='utf-8')
    evidence.update(readable=True, replies_file=text.name,
                    replies_sha256=digest(json.dumps(replies, ensure_ascii=True).encode()),
                    reply_chars=sum(map(len, replies)))
    return replies


def review(summary_path, quotes_path, reader, method):
    reviews = summary_path.parent / 'reviews'; reviews.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=summary_path.stem + '-', dir=reviews))
    record = {'kind': 'independent-discovery-review', 'version': 1,
              'created_at': datetime.now(timezone.utc).isoformat(),
              'status': 'unverified', 'reasons': [],
              'reader': {'identity': reader, 'method': method},
              'validation': '인용이 실제 원문에 존재하는지만 대조했다. 의미 판단은 독립 판독자가 제공했다.',
              'source': {'path': str(summary_path)}, 'execution': {}, 'originals': [],
              'matches': {}, 'assessment': {'discovery': 'unverified'}}
    originals = []
    summary = {}
    try:
        raw = preserve(summary_path, directory / 'summary.original')
        record['source']['sha256'] = digest(raw)
        summary = json.loads(raw)
        if not isinstance(summary, dict): raise ValueError('요약이 객체가 아니다')
        record['source'].update({key: summary.get(key) for key in
            ('name', 'task', 'conversation_contract', 'policy_topics', 'required_discovery_topics',
             'discovery_exclusions', 'static_turns', 'discovered', 'surfaced_quotes', 'mock_error')})
        record['execution'] = {key: summary.get(key) for key in
            ('task_fingerprint', 'judge_version', 'model', 'mock_user_model', 'harness_version')}
        count = summary.get('static_turns', 1)
        if type(count) is not int or count < 1: raise ValueError('원문 턴 범위를 알 수 없다')
        for number in range(1, count + 1):
            log = transcript.turn_log(summary_path.with_suffix('.jsonl'), number)
            evidence = {'turn': number, 'path': str(log), 'readable': False}
            record['originals'].append(evidence)
            try:
                replies = read_original(log, directory, number, evidence)
                originals.append((number, replies))
            except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
                record['reasons'].append(f'턴 {number} 원문 미확인: ' + str(error))
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
        record['reasons'].append('원문 미확인: ' + str(error))
    try:
        raw = preserve(quotes_path, directory / 'quotes.original')
        record['quotes_sha256'] = digest(raw)
        supplied = json.loads(raw)
        quotes = supplied['quotes']
        record['quotes'] = quotes
        policy = summary.get('policy_topics')
        if (not isinstance(policy, list) or not policy or
            any(type(n) is not int for n in policy) or len(set(policy)) != len(policy)):
            raise ValueError('실행 당시 정책 번호가 없다')
        if summary.get('conversation_contract') != 'fixed-policy-v1':
            raise ValueError('실행 당시 발견 계약을 확인할 수 없다')
        if any(not isinstance(summary.get(key), str) or not summary[key].strip()
               for key in ('task_fingerprint', 'judge_version')):
            raise ValueError('실행 당시 과제 또는 판정 지문이 없다')
        required = discovery_scope(policy, summary.get('required_discovery_topics', policy), summary.get('discovery_exclusions', {}))
        if not isinstance(quotes, dict) or set(quotes) != {str(n) for n in policy}:
            raise ValueError('각 정책에 인용문 또는 null이 필요하다')
        invalid = []
        for topic, quote in quotes.items():
            if quote is None: continue
            matches = [{'turn': turn, 'reply': index} for turn, replies in originals
                       for index, text in enumerate(replies, 1)
                       if isinstance(quote, str) and quote.strip() and quote in text]
            record['matches'][topic] = matches
            if not matches: invalid.append(topic)
        if not record['reasons']:
            if invalid:
                record['status'] = 'rejected'
                record['reasons'].append('원문에 없는 인용: 정책 ' + ', '.join(sorted(invalid)))
            else:
                found = sorted(int(topic) for topic, quote in quotes.items() if quote is not None)
                missing = sorted(set(required) - set(found))
                record['status'] = 'supported'
                record['assessment'] = {'discovery': 'incomplete' if missing else 'complete',
                                        'discovered': found, 'missing_topics': missing,
                                        'required_discovery_topics': required,
                                        'meaning_judged_by': reader}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as error:
        record['reasons'].append('판독 기준 미확인: ' + str(error))
    path = directory / 'review.json'
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--quotes', type=Path, required=True)
    parser.add_argument('--reader', required=True)
    parser.add_argument('--method', required=True)
    args = parser.parse_args()
    if not args.reader.strip() or not args.method.strip(): parser.error('판독자와 독립 판독 방법이 필요하다')
    path, record = review(args.summary.resolve(), args.quotes.resolve(), args.reader, args.method)
    print(json.dumps({'review': str(path), 'status': record['status']}, ensure_ascii=False))
    return {'supported': 0, 'rejected': 1, 'unverified': 2}[record['status']]


if __name__ == '__main__':
    sys.exit(main())
