"""macOS 파일 사건(FSEvents) 감시: 한 턴 동안 폴더 아래에서 쓰이거나 생기거나 지워진 파일을 모은다.

  w = Watch(root); (에이전트 실행); paths = w.stop()

감시를 켜기 전에 일어난 쓰기의 사건이 표식 뒤에 도착하는 일이 있다(프로젝트를 막 만든 직후). stop() 은 사건이 온 경로 가운데
감시 시작 뒤에 실제로 상태가 바뀐 것(또는 없어진 것)만 돌려준다.

사건은 순서대로 오지만 늦게 온다. 그래서 시작과 끝에 .git 안의 표식 파일을 쓰고 그 사건이 올 때까지 기다린다:
시작 표식이 오면 감시가 켜진 것이고, 끝 표식이 오면 그보다 먼저 일어난 사건은 모두 받은 것이다. 표식이 제한 시간 안에 오지 않거나 감시를 쓸 수 없으면(macOS 가 아님, GOALFLOW_NO_WATCH=1) OSError(관찰 불가).
"""
import ctypes, ctypes.util, os, threading, time, uuid

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
        self.timed = []  # (받은 시각, 경로, 사건 종류 비트): 무엇이 언제 어떻게 쓰였는지 명령 기록과 맞춰 보는 증거

        def cb(stream, info, n, paths, flags, ids):
            now = time.time()
            with self.lock:
                self.out.extend((paths[i].decode("utf-8", "replace"), flags[i]) for i in range(n))
                self.timed.extend((now, paths[i].decode("utf-8", "replace"), flags[i]) for i in range(n))
        self.cb = _CB(cb)
        arr = _LIBS[1].CFArrayCreate(None, (ctypes.c_void_p * 1)(_LIBS[1].CFStringCreateWithCString(None, self.root.encode(), 0x08000100)), 1, None)
        self.stream = _LIBS[0].FSEventStreamCreate(None, self.cb, None, arr, _SINCE_NOW, 0.0, _FILE_EVENTS | _NO_DEFER)
        _LIBS[0].FSEventStreamSetDispatchQueue(self.stream, _LIBS[2].dispatch_queue_create(b"turn-watch", None))
        if not _LIBS[0].FSEventStreamStart(self.stream):
            self._close(); raise OSError("파일 사건 감시를 시작하지 못했다")
        self._barrier()
        with self.lock:
            self.out.clear()
            self.timed.clear()
        self.started = time.time()

    def events(self):
        """stop() 뒤에 부른다: .git 밖 사건을 [{"time", "path", "flags"}] 로(받은 순서). flags 는 FSEvents 사건 종류 비트다."""
        with self.lock:
            rows = [(t, os.path.relpath(p, self.root), f) for t, p, f in self.timed]
        return [{"time": round(t, 3), "path": rel, "flags": hex(f)} for t, rel, f in rows
                if rel not in (".", ".git") and not rel.startswith(".git/")]

    def _barrier(self):
        # 시작 표식의 늦은 사건을 종료 표식으로 오인하지 않도록 매번 다른 경로를 쓴다.
        self.mark = os.path.join(self.root, '.git', 'fsevents-mark-' + uuid.uuid4().hex)
        token = f"{time.time_ns()}"
        with open(self.mark, "w") as f:
            f.write(token)
        end = time.time() + self.timeout
        while time.time() < end:
            _LIBS[0].FSEventStreamFlushSync(self.stream)
            with self.lock:
                seen = [p for p, _ in self.out]
                if self.mark in seen:
                    # 같은 배치에서 표식 뒤에 실린 제품 사건도 이미 관찰한 증거다.
                    os.unlink(self.mark)
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
                if rel not in (".", ".git") and not rel.startswith(".git/") and self._changed_since_start(p):
                    found[rel] = found.get(rel, False) or bool(flag & _IS_DIR)
        return found

    def _changed_since_start(self, path):
        """사건이 온 경로가 감시 시작 뒤에 실제로 바뀌었는가. 감시를 켜기 전에 만든 파일의 사건은 늦게 올 수 있다.
        지금 있는 경로의 상태 변경 시각(쓰기·되돌리기·이름 바꾸기·권한 변경 모두 갱신)이 시작 전이면 이 턴의 쓰기가 아니다.
        없어진 경로는 지워진 것이므로 남긴다."""
        started = getattr(self, "started", None)
        if started is None:
            return True
        try:
            return os.lstat(path).st_ctime >= started
        except OSError:
            return True
