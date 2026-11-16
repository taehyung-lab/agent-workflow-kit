"""macOS 파일 사건(FSEvents) 감시: 한 턴 동안 폴더 아래에서 쓰이거나 생기거나 지워진 파일을 모은다.

  w = Watch(root); (에이전트 실행); paths = w.stop()

사건은 순서대로 오지만 늦게 온다. 그래서 시작과 끝에 .git 안의 표식 파일을 쓰고 그 사건이 올 때까지 기다린다:
시작 표식이 오면 감시가 켜진 것이고, 끝 표식이 오면 그보다 먼저 일어난 사건은 모두 받은 것이다. 표식이 제한 시간 안에 오지 않으면 OSError(관찰 불가).
"""
import ctypes, ctypes.util, os, threading, time

_CS = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreServices") or "")
_CF = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation") or "")
_LS = ctypes.CDLL(None)
_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_char_p),
                       ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint64))
_CF.CFStringCreateWithCString.restype = ctypes.c_void_p
_CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_CF.CFArrayCreate.restype = ctypes.c_void_p
_CF.CFArrayCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_long, ctypes.c_void_p]
_CS.FSEventStreamCreate.restype = ctypes.c_void_p
_CS.FSEventStreamCreate.argtypes = [ctypes.c_void_p, _CB, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint32]
_CS.FSEventStreamStart.restype = ctypes.c_bool
for _f in ("FSEventStreamSetDispatchQueue",):
    getattr(_CS, _f).argtypes = [ctypes.c_void_p, ctypes.c_void_p]
for _f in ("FSEventStreamStart", "FSEventStreamStop", "FSEventStreamInvalidate", "FSEventStreamRelease", "FSEventStreamFlushSync"):
    getattr(_CS, _f).argtypes = [ctypes.c_void_p]
_LS.dispatch_queue_create.restype = ctypes.c_void_p
_LS.dispatch_queue_create.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
_SINCE_NOW, _FILE_EVENTS, _NO_DEFER = 0xFFFFFFFFFFFFFFFF, 0x10, 0x2
_IS_DIR, _RENAMED = 0x20000, 0x800  # kFSEventStreamEventFlagItemIsDir, ItemRenamed


class Watch:
    def __init__(self, root, timeout=10):
        self.root, self.timeout, self.out, self.lock = os.path.realpath(root), timeout, [], threading.Lock()
        self.mark = os.path.join(self.root, ".git", "fsevents-mark")

        def cb(stream, info, n, paths, flags, ids):
            with self.lock:
                self.out.extend((paths[i].decode("utf-8", "replace"), flags[i]) for i in range(n))
        self.cb = _CB(cb)
        arr = _CF.CFArrayCreate(None, (ctypes.c_void_p * 1)(_CF.CFStringCreateWithCString(None, self.root.encode(), 0x08000100)), 1, None)
        self.stream = _CS.FSEventStreamCreate(None, self.cb, None, arr, _SINCE_NOW, 0.0, _FILE_EVENTS | _NO_DEFER)
        _CS.FSEventStreamSetDispatchQueue(self.stream, _LS.dispatch_queue_create(b"turn-watch", None))
        if not _CS.FSEventStreamStart(self.stream):
            self._close(); raise OSError("파일 사건 감시를 시작하지 못했다")
        self._barrier()
        with self.lock:
            self.out.clear()

    def _barrier(self):
        token = f"{time.time_ns()}"
        with open(self.mark, "w") as f:
            f.write(token)
        end = time.time() + self.timeout
        while time.time() < end:
            _CS.FSEventStreamFlushSync(self.stream)
            with self.lock:
                seen = [p for p, _ in self.out]
                if self.mark in seen:
                    cut = len(seen) - seen[::-1].index(self.mark)  # 표식까지의 사건
                    self.out = self.out[:cut]
                    return
            time.sleep(0.05)
        self._close(); raise OSError("파일 사건이 제한 시간 안에 오지 않았다")

    def _close(self):
        _CS.FSEventStreamStop(self.stream); _CS.FSEventStreamInvalidate(self.stream); _CS.FSEventStreamRelease(self.stream)

    def stop(self):
        """감시를 끝내고 그동안 사건이 난 경로를 {상대 경로: 종류} 로 돌려준다(.git 안 제외).
        종류: file(파일 쓰기·만들기·지우기·이름 바꾸기), dir-moved(폴더 이름 바꾸기·옮기기: macOS 는 안의 파일마다 사건을 내지 않는다),
        dir(폴더 만들기·지우기만). 어느 것이 제품 변경인지는 부르는 쪽(conversation.turn_writes)이 정한다."""
        self._barrier()
        self._close()
        rank = {"dir": 0, "file": 1, "dir-moved": 2}
        kinds = {}
        with self.lock:
            for p, flag in self.out:
                rel = os.path.relpath(p, self.root)
                if rel in (".", ".git") or rel.startswith(".git/"):
                    continue
                kind = ("dir-moved" if flag & _RENAMED else "dir") if flag & _IS_DIR else "file"
                if rank[kind] >= rank.get(kinds.get(rel), -1):
                    kinds[rel] = kind
        return kinds
