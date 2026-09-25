"""one colour per row, esc and space white. the frame that proved the board."""
from __future__ import annotations

ROW_COLORS = [(255, 0, 0), (255, 90, 0), (255, 220, 0), (0, 255, 0), (0, 80, 255), (180, 0, 255)]


class Rows:
    keys = None

    def start(self, layout) -> None:
        self.frame = {k.name: ROW_COLORS[k.row] for k in layout.KEYS}
        self.frame["esc"] = self.frame["space"] = (255, 255, 255)
        self.sent = False

    def on_key(self, key, down) -> None:
        pass

    def tick(self, t, dt):
        if self.sent:
            return None
        self.sent = True
        return self.frame

    def stop(self) -> None:
        pass
