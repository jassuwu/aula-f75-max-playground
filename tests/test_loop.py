from keys import loop
from keys.board import BoardLost


class FakeBoard:
    instances = 0

    def __init__(self, fail_after=None):
        FakeBoard.instances += 1
        self.writes = 0
        self.fail_after = fail_after

    def write(self, frame):
        if self.fail_after is not None and self.writes >= self.fail_after:
            raise BoardLost("device not responding")
        self.writes += 1

    def close(self):
        pass


class Counter:
    keys = None

    def __init__(self):
        self.ticks = 0
        self.done = False

    def start(self, layout):
        pass

    def on_key(self, key, down):
        pass

    def tick(self, t, dt):
        self.ticks += 1
        if self.ticks >= 20:
            self.done = True
        return {"esc": (self.ticks, 0, 0)}

    def stop(self):
        self.stopped = True


def test_a_lost_board_is_reopened_and_the_source_keeps_running(monkeypatch):
    reopened = []

    class Reopen(FakeBoard):
        def __init__(self):
            super().__init__()
            reopened.append(self)

    monkeypatch.setattr(loop, "Board", Reopen)
    monkeypatch.setattr(loop, "RETRY", 0.0)
    said = []
    src = Counter()
    first = FakeBoard(fail_after=5)
    loop.run(src, fps=200, board=first, say=said.append)
    assert src.ticks == 20 and src.stopped
    assert first.writes == 5
    assert reopened and reopened[0].writes > 0
    assert any("stopped answering" in m for m in said) and any("back" in m for m in said)
