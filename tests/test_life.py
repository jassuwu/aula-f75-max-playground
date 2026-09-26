import random

from keys import layout
from keys.layout import neighbors
from keys.sources.life import ALIVE, BORN, DENSITY, GPS, HISTORY, STALE, Life


def key(name):
    return layout.BY_NAME[name]


def make(seed=1):
    s = Life(rng=random.Random(seed))
    s.start(layout)
    return s


# ── the graph ────────────────────────────────────────────────────────────────

def test_neighbors_follow_the_stagger():
    assert {k.name for k in neighbors(key("g"))} == {"f", "h", "r", "t", "y", "v", "b"}
    assert {k.name for k in neighbors(key("1"))} == {"`", "2", "esc", "f1", "tab", "q"}


def test_neighbors_wrap_both_ways():
    esc = {k.name for k in neighbors(key("esc"))}
    assert {"f12", "lctrl", "win"} <= esc          # row wrap and top-to-bottom wrap
    assert "f12" in {k.name for k in neighbors(key("left"))}


def test_neighbors_are_symmetric_and_never_self():
    for k in layout.KEYS:
        ns = neighbors(k)
        assert k not in ns
        assert len(ns) == len(set(ns))
        for m in ns:
            assert k in neighbors(m), (k.name, m.name)


def test_wide_keys_collect_many_neighbors():
    assert len(neighbors(key("space"))) == 17
    assert 6 <= len(neighbors(key("d"))) <= 8


# ── the rules ────────────────────────────────────────────────────────────────

def alive(s, *names):
    s.alive = {key(n) for n in names}
    s.age = {k: 0 for k in s.alive}


def test_birth_on_three_survival_on_two_or_three():
    s = make()
    # e sits above s d f (all three touch it); x sits above only s and d
    alive(s, "s", "d", "f")
    s.step()
    assert key("e") in s.alive              # 3 live neighbours: born
    assert key("d") in s.alive              # 2 live neighbours (s, f): survives
    assert key("s") not in s.alive          # 1 live neighbour: dies
    assert key("x") not in s.alive          # 2 live neighbours, was dead: stays dead


def test_lonely_and_crowded_cells_die():
    s = make()
    alive(s, "g")
    s.step()
    assert s.population == 0
    alive(s, "g", "f", "h", "t", "y")       # g has four live neighbours
    s.step()
    assert key("g") not in s.alive


def test_age_counts_generations_alive():
    s = make()
    alive(s, "s", "d", "f")
    s.step()
    assert s.age[key("e")] == 0 and s.age[key("d")] == 1


# ── the controls ─────────────────────────────────────────────────────────────

def test_deal_fills_about_a_third_and_runs():
    s = make()
    assert not s.paused
    assert 0.2 < s.population / 80 < 0.5
    assert abs(DENSITY - 0.35) < 1e-9


def test_tap_toggles_a_cell_and_keeps_esc_out_of_it():
    s = make()
    alive(s)
    s.on_key(key("q"), True)
    assert s.alive == {key("q")}
    s.on_key(key("q"), False)                 # release does nothing
    s.on_key(key("q"), True)
    assert s.population == 0
    s.on_key(key("esc"), True)
    assert s.population == 0


def test_backspace_clears_and_pauses_so_you_can_draw():
    s = make()
    s.on_key(key("backspace"), True)
    assert s.population == 0 and s.paused
    s.on_key(key("k"), True)
    s.tick(10.0, 10.0)                        # paused: nothing runs, nothing is dealt
    assert s.alive == {key("k")}


def test_space_pauses_and_resumes():
    s = make()
    alive(s, "s", "d", "f")
    s.on_key(key("space"), True)
    s.tick(1.0, 1.0)
    assert s.alive == {key("s"), key("d"), key("f")}
    s.on_key(key("space"), True)
    assert not s.paused
    s.tick(1.0 + 1.0 / GPS, 1.0 / GPS)
    assert s.gen == 1


def test_enter_deals_a_new_board():
    s = make()
    s.on_key(key("backspace"), True)
    s.on_key(key("enter"), True)
    assert s.population > 0 and not s.paused


def test_a_settled_running_board_is_dealt_again():
    s = make()
    alive(s, "g")
    s.tick(0.0, 0.0)
    t = 0.0
    while t < STALE - 0.5:                    # empty board loops on itself: settled, not yet stale
        t += 1.0 / GPS
        s.tick(t, 1.0 / GPS)
    assert s.population == 0 and s.stale_since is not None
    t += 1.0
    s.tick(t, 1.0)
    assert s.population > 0                   # dealt


def test_drawing_on_a_settled_board_resets_the_stale_clock():
    s = make()
    alive(s, "g")
    for i in range(HISTORY + 2):
        s.tick(i / GPS, 1 / GPS)
    assert s.stale_since is not None
    s.on_key(key("k"), True)
    assert s.stale_since is None


# ── the frame ────────────────────────────────────────────────────────────────

def test_frame_shows_newborns_white_and_deaths_red():
    s = make()
    alive(s, "s", "d", "f")
    s.tick(0.0, 0.0)
    f = s.tick(1.0 / GPS, 1.0 / GPS)
    assert f["e"] == BORN
    assert f["s"][0] > f["s"][2]              # ember: red over blue
    s.on_key(key("space"), True)              # hold the board still
    f = s.render(1.0 / GPS + 1.0)             # long after the fade
    assert "s" not in f
    s.alive, s.age, s.dying = {key("d")}, {key("d"): 10}, {}
    assert s.render(5.0)["d"] == ALIVE
    assert "space" in s.render(5.0)           # the pause pulse
