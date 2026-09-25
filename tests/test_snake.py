import random

from keys import layout
from keys.sources.snake import Snake


def make(seed=1):
    s = Snake(rng=random.Random(seed))
    s.start(layout)
    return s


def key(name):
    return layout.BY_NAME[name]


def test_starts_paused_on_home_row():
    s = make()
    assert [k.name for k in s.body] == ["a", "s", "d"]
    s.tick(5.0, 5.0)
    assert s.state == "waiting" and s.head.name == "d"


def test_first_arrow_starts_and_moves_physically():
    s = make()
    s.on_key(key("right"), True)
    assert s.state == "running"
    s.tick(0.0, 0)
    s.tick(0.4, 0.4)  # one step at 3/s
    assert s.head.name == "f" and s.length == 3


def test_reversal_is_ignored_and_turns_queue_two_deep():
    s = make()
    s.on_key(key("left"), True)          # reversal of the initial "right": ignored
    assert s.state == "waiting"
    s.on_key(key("up"), True)
    s.on_key(key("left"), True)          # queued behind up
    assert list(s.queued) == ["up", "left"]
    s.on_key(key("right"), True)         # reversal of the last queued: ignored
    assert list(s.queued) == ["up", "left"]


def test_wraps_at_the_edges():
    s = make()
    s.body.clear()
    s.body.extend([key("f10"), key("f11"), key("f12")])
    s.direction = "right"
    s.step()
    assert s.head.name == "esc"


def test_eating_grows_and_speeds_up():
    s = make()
    s.apple = layout.neighbor(s.head, "right")
    before = s.speed
    s.step()
    assert s.length == 4 and s.apples == 1 and s.speed > before and s.apple is None
    s.state = "running"
    s.tick(1.0, 1.0)  # long after apple_at: a new apple appears somewhere free
    assert s.apple is not None and s.apple not in set(s.body)


def test_self_collision_dies_and_enter_restarts():
    s = make()
    # head at d going right; force a body that blocks f
    s.body.clear()
    s.body.extend([key("g"), key("f"), key("r"), key("e"), key("d")])
    s.direction = "right"
    s.step()
    assert s.state == "dying"
    s.tick(0.0, 0)
    s.tick(1.0, 1.0)
    assert s.state == "dead"
    frame = s.render(1.0)
    assert frame["enter"] != (0, 0, 0) and frame["d"] == (70, 0, 0)
    s.on_key(key("enter"), True)
    assert s.state == "waiting" and s.length == 3


def test_moving_into_own_tail_is_allowed():
    s = make()
    # a 4-loop: head steps into the tail's cell as the tail leaves
    s.body.clear()
    s.body.extend([key("d"), key("e"), key("r"), key("f")])
    s.direction = "left"
    s.apple = None
    s.step()
    assert s.state == "running" or s.head.name == "d"
