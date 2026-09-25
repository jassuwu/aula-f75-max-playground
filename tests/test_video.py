from keys.layout import BY_NAME
from keys.sources.video import GRID_H, GRID_W, Sampler


def grid(fn):
    out = bytearray()
    for y in range(GRID_H):
        for x in range(GRID_W):
            out += bytes(fn(x, y))
    return bytes(out)


def test_left_half_white_lights_left_keys_only():
    s = Sampler()
    frame = s.sample(grid(lambda x, y: (255, 255, 255) if x < GRID_W // 2 else (0, 0, 0)))
    assert frame["esc"] == (255, 255, 255) and frame["q"] == (255, 255, 255)
    assert frame["f12"] == (0, 0, 0) and frame["right"] == (0, 0, 0)
    # space straddles the middle: partly lit
    assert 0 < frame["space"][0] < 255


def test_bottom_row_red_is_only_the_bottom_row():
    s = Sampler()
    frame = s.sample(grid(lambda x, y: (255, 0, 0) if y >= GRID_H * 0.88 else (0, 0, 0)))
    for name in ("lctrl", "space", "fn", "left", "down", "right"):
        assert frame[name][0] > 200, name
    for name in ("z", "rshift", "up", "a", "esc"):
        assert frame[name] == (0, 0, 0), name


def test_grey_is_linearised():
    s = Sampler()
    frame = s.sample(grid(lambda x, y: (128, 128, 128)))
    assert 50 <= frame["g"][0] <= 60  # srgb 128 is about 22% light
