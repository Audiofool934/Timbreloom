"""One writer per local library, even when web and desktop start together."""

import fcntl
from pathlib import Path


class DataDirectoryLock:
    def __init__(self, root: Path) -> None:
        self.path = root / ".service.lock"
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            raise RuntimeError("这个资料库已有 Timbreloom 服务在运行，请连接现有服务。") from None
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
