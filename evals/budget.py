"""명시한 로컬 평가 원장의 횟수와 CLI 경과시간을 공유한다.

EVALS_BUDGET_FILE이 없으면 기존 실행에는 적용하지 않는다.
원장은 승인 판단이나 보안 경계가 아니다. 승인 원문의 위치/해시와 고정 한도를
보존하며, 호출자가 승인받은 수치를 create에 명시해야 한다.
생성(승인받은 뒤):
  python3 -I evals/budget.py <원장.json> --approval-source <승인원문> --max-runs <횟수> --max-seconds <초>
실행 시 EVALS_BUDGET_FILE=<원장.json>을 지정한다. 프로세스가 중단돼 정산되지 않은
예약은 계속 사용량으로 남는다. 원장을 재생성하거나 미확인 시간을 되돌리지 않는다.
시간은 관찰한 로컬 CLI 벽시계 시간이다. 부모 CLI 안의 자식 시간은 중복 계산하지
않는다. 원격 서비스의 취소, 토큰/금액 한도나 분리된 프로세스까지 보장하지 않는다.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid


class BudgetError(RuntimeError): pass


def _hash(raw): return hashlib.sha256(raw).hexdigest()

def _bytes(data): return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()

def _number(value): return type(value) in (int,float) and math.isfinite(value) and value >= 0


def create(path, approval_source, max_runs, max_seconds):
    """실제 승인 확인은 호출자의 책임이다. 기존 원장/봉인을 덮어쓰지 않는다."""
    path, source = Path(path).resolve(), Path(approval_source).resolve()
    if type(max_runs) is not int or max_runs < 1 or not _number(max_seconds) or not max_seconds:
        raise BudgetError('budget: 횟수와 초는 양수여야 한다')
    raw = source.read_bytes()
    if not raw.strip(): raise BudgetError('budget: 승인 근거가 비어 있다')
    data = {'version':1, 'policy':{'approval_source':str(source), 'approval_sha256':_hash(raw),
            'max_runs':max_runs, 'max_seconds':max_seconds}, 'runs':[], 'calls':{}}
    encoded = _bytes(data)
    lock = Path(str(path)+'.lock')
    # 봉인은 무심코 한도/사용량을 고친 기록을 거절하기 위한 것이며 접근 권한 집행이 아니다.
    with lock.open('x') as seal:
        with path.open('xb') as output: output.write(encoded)
        seal.write(_hash(encoded)); seal.flush(); os.fsync(seal.fileno())


@contextmanager
def _ledger(path):
    path=Path(path).resolve()
    try:
        with Path(str(path)+'.lock').open('r+') as seal:
            fcntl.flock(seal, fcntl.LOCK_EX)
            raw=path.read_bytes()
            if seal.read().strip()!=_hash(raw): raise BudgetError('budget: 원장 또는 고정 한도가 변경됐다')
            data=json.loads(raw)
            policy=data['policy']
            if (data['version']!=1 or type(policy['max_runs']) is not int or policy['max_runs']<1
                or not _number(policy['max_seconds']) or not policy['max_seconds']
                or not isinstance(data['runs'],list) or not isinstance(data['calls'],dict)):
                raise BudgetError('budget: 원장 형식이 손상됐다')
            if _hash(Path(policy['approval_source']).read_bytes())!=policy['approval_sha256']:
                raise BudgetError('budget: 승인 원문이 변경됐다')
            for call in data['calls'].values():
                if call['status'] not in ('running','finished') or not all(_number(call[k]) for k in ('allocated_seconds','seconds','started_at')):
                    raise BudgetError('budget: 시간 사용 기록이 손상됐다')
            yield data
            encoded=_bytes(data)
            fd,name=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as output:
                    output.write(encoded); output.flush(); os.fsync(output.fileno())
                os.replace(name,path)
                seal.seek(0);seal.truncate();seal.write(_hash(encoded));seal.flush();os.fsync(seal.fileno())
            finally:
                if os.path.exists(name): os.unlink(name)
    except BudgetError: raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise BudgetError('budget: 원장을 읽거나 보존할 수 없다: '+str(error)) from error


def reserve_run(prefix):
    path=os.environ.get('EVALS_BUDGET_FILE')
    if not path: return
    with _ledger(path) as data:
        if len(data['runs'])>=data['policy']['max_runs']: raise BudgetError('budget: 승인된 최상위 실행 횟수를 모두 썼다')
        data['runs'].append({'prefix':str(Path(prefix).resolve()),'started_at':time.time()})


def reserve_time(limit, environment):
    if not _number(limit) or not limit: raise BudgetError('budget: CLI 시간 배정은 양수여야 한다')
    path=environment.get('EVALS_BUDGET_FILE')
    if not path: return None
    with _ledger(path) as data:
        parent=environment.get('EVALS_BUDGET_CALL_ID')
        call=data['calls'].get(parent)
        if call and call['status']=='running' and call.get('process_group')==os.getpgrp():
            remaining=call['allocated_seconds']-(time.time()-call['started_at'])
            if remaining<=0: raise BudgetError('budget: 상위 CLI의 남은 시간이 없다')
            return {'nested':True,'seconds':min(limit,remaining),'id':parent,'path':path}
        used=sum(call['allocated_seconds'] if call['status']=='running' else call['seconds'] for call in data['calls'].values())
        remaining=data['policy']['max_seconds']-used
        if remaining<=0.001: raise BudgetError('budget: 승인된 합산 CLI 시간을 모두 사용하거나 예약했다')
        allocated=min(float(limit),remaining)
        identifier=uuid.uuid4().hex
        data['calls'][identifier]={'status':'running','started_at':time.time(), 'allocated_seconds':allocated,
                                  'seconds':0,'owner_pid':os.getpid(),'process_group':None}
        return {'nested':False,'seconds':allocated,'id':identifier,'path':path}


def attach(lease, pid):
    if lease and not lease['nested']:
        with _ledger(lease['path']) as data: data['calls'][lease['id']]['process_group']=pid


def finish(lease, elapsed, reason, exit_code):
    if lease and not lease['nested']:
        with _ledger(lease['path']) as data:
            data['calls'][lease['id']].update(status='finished',seconds=elapsed,reason=reason,exit_code=exit_code)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path)
    parser.add_argument('--approval-source',type=Path,required=True)
    parser.add_argument('--max-runs',type=int,required=True)
    parser.add_argument('--max-seconds',type=float,required=True)
    arguments=parser.parse_args()
    create(arguments.path,arguments.approval_source,arguments.max_runs,arguments.max_seconds)
    print(arguments.path.resolve())
