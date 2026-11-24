"""감시 종료와 같은 묶음으로 도착한 변경도 잃지 않아야 한다."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals/goalflow'))
import turnwatch

class Events:
    def __init__(self, watch): self.watch=watch
    def FSEventStreamFlushSync(self, stream):
        self.watch.out.extend([(self.watch.mark,0),(str(Path(self.watch.root)/'product.py'),0)])
    def FSEventStreamStop(self, stream): pass
    def FSEventStreamInvalidate(self, stream): pass
    def FSEventStreamRelease(self, stream): pass

class BarrierTest(unittest.TestCase):
    def test_end_marker_does_not_discard_other_delivered_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.git').mkdir()
            watch=turnwatch.Watch.__new__(turnwatch.Watch)
            watch.root=str(root);watch.mark=str(root/'.git/marker');watch.timeout=1
            watch.out=[];watch.lock=threading.Lock();watch.stream=None
            with patch.object(turnwatch,'_LIBS',(Events(watch),None,None)):
                self.assertEqual(watch.stop(), {'product.py':False})

class LateSetupEventTest(unittest.TestCase):
    """감시를 켜기 전에 만든 파일의 사건이 늦게 도착해도 턴 안의 쓰기로 세지 않는다.

    2026-11-24 rooms-checks: 에이전트의 첫 명령보다 4초 앞선 시각에, 프로젝트를 만들 때 쓴 파일 전부(.agents·AGENTS.md 포함)의
    '생성' 사건이 한꺼번에 도착해 "답 전에 제품 파일을 바꿨다"로 판정됐다. 내용도 시각도 감시 시작 뒤에 바뀐 적이 없었다."""
    def stop_with(self, root, paths, started):
        class Late(Events):
            def FSEventStreamFlushSync(inner, stream):
                inner.watch.out.extend([(inner.watch.mark,0)]+[(str(root/p),0) for p in paths])
        watch=turnwatch.Watch.__new__(turnwatch.Watch)
        watch.root=str(root);watch.mark=str(root/'.git/marker');watch.timeout=1
        watch.out=[];watch.timed=[];watch.lock=threading.Lock();watch.stream=None;watch.started=started
        with patch.object(turnwatch,'_LIBS',(Late(watch),None,None)):
            return watch.stop()
    def test_untouched_file_reported_late_is_dropped_but_rewritten_one_is_kept(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.git').mkdir();(root/'docs').mkdir()
            for name in ('README.md','rooms.py','docs/operations.md'): (root/name).write_text('처음')
            time.sleep(0.05); started=time.time(); time.sleep(0.05)
            # 감시 시작 뒤 고쳤다가 같은 내용으로 되돌린 파일: 내용은 같아도 쓰기는 있었다.
            (root/'rooms.py').write_text('고침');(root/'rooms.py').write_text('처음')
            found=self.stop_with(root,['README.md','rooms.py','docs','docs/operations.md','gone.py'],started)
            self.assertEqual(sorted(found),['gone.py','rooms.py'])

if __name__=='__main__':unittest.main()
