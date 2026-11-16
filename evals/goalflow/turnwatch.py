"""macOS 파일 사건(FSEvents) 감시: 한 턴 동안 폴더 아래에서 쓰이거나 생기거나 지워진 파일을 모은다.

  w = Watch(root); (에이전트 실행); paths = w.stop()

사건은 순서대로 오지만 늦게 온다. 그래서 시작과 끝에 .git 안의 표식 파일을 쓰고 그 사건이 올 때까지 기다린다:
시작 표식이 오면 감시가 켜진 것이고, 끝 표식이 오면 그보다 먼저 일어난 사건은 모두 받은 것이다. 표식이 제한 시간 안에 오지 않거나 감시를 쓸 수 없으면(macOS 가 아님, GOALFLOW_NO_WATCH=1) OSError(관찰 불가).
"""
import ctypes, ctypes.util, os, threading, time

_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_char_p),
                       ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint64))


def _bind():
    """macOS CoreServices·CoreFoundation 함수를 묶는다. macOS 가 아니면(함수를 찾지 못하면) None."""
    cs, cf = (ctypes.util.find_library(n) for n in ("CoreServices", "CoreFoundation"))
    if not cs or not cf:
        return None
    _CS, _CF, _LS = ctypes.cdll.LoadLibrary(cs), ctypes.cdll.LoadLibrary(cf), ctypes.CDLL(None)
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
    return _CS, _CF, _LS


try:
    _LIBS = _bind()
except (OSError, AttributeError):
    _LIBS = None
_SINCE_NOW, _FILE_EVENTS, _NO_DEFER = 0xFFFFFFFFFFFFFFFF, 0x10, 0x2
_IS_DIR = 0x20000  # kFSEventStreamEventFlagItemIsDir


class Watch:
    def __init__(self, root, timeout=10):
        if os.environ.get("GOALFLOW_NO_WATCH") == "1" or _LIBS is None:  # 감시를 끈 실행, CoreServices 가 없는 운영체제
            raise OSError("파일 사건 감시를 쓸 수 없다(macOS FSEvents 아님)")
        self.root, self.timeout, self.out, self.lock = os.path.realpath(root), timeout, [], threading.Lock()
        self.mark = os.path.join(self.root, ".git", "fsevents-mark")

        def cb(stream, info, n, paths, flags, ids):
            with self.lock:
                self.out.extend((paths[i].decode("utf-8", "replace"), flags[i]) for i in range(n))
        self.cb = _CB(cb)
        arr = _LIBS[1].CFArrayCreate(None, (ctypes.c_void_p * 1)(_LIBS[1].CFStringCreateWithCString(None, self.root.encode(), 0x08000100)), 1, None)
        self.stream = _LIBS[0].FSEventStreamCreate(None, self.cb, None, arr, _SINCE_NOW, 0.0, _FILE_EVENTS | _NO_DEFER)
        _LIBS[0].FSEventStreamSetDispatchQueue(self.stream, _LIBS[2].dispatch_queue_create(b"turn-watch", None))
        if not _LIBS[0].FSEventStreamStart(self.stream):
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
            _LIBS[0].FSEventStreamFlushSync(self.stream)
            with self.lock:
                seen = [p for p, _ in self.out]
                if self.mark in seen:
                    cut = len(seen) - seen[::-1].index(self.mark)  # 표식까지의 사건
                    self.out = self.out[:cut]
                    return
            time.sleep(0.05)
        self._close(); raise OSError("파일 사건이 제한 시간 안에 오지 않았다")

    def _close(self):
        _LIBS[0].FSEventStreamStop(self.stream); _LIBS[0].FSEventStreamInvalidate(self.stream); _LIBS[0].FSEventStreamRelease(self.stream)

    def stop(self):
        """감시를 끝내고 그동안 사건이 난 경로를 {상대 경로: 폴더인가} 로 돌려준다(.git 안 제외).
        macOS 는 폴더를 옮기거나 지울 때 안의 파일마다 사건을 내지 않을 수 있어 폴더 사건도 남긴다. 무엇이 제품 변경인지는 부르는 쪽이 정한다."""
        self._barrier()
        self._close()
        found = {}
        with self.lock:
            for p, flag in self.out:
                rel = os.path.relpath(p, self.root)
                if rel not in (".", ".git") and not rel.startswith(".git/"):
                    found[rel] = found.get(rel, False) or bool(flag & _IS_DIR)
        return found
