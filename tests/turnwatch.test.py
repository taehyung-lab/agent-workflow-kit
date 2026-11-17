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

if __name__=='__main__':unittest.main()
