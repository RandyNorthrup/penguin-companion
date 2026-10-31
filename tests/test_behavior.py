import random

from penguin_companion.behavior import Behavior

ANIMS = {
    "walk": (8, 10, True), "idle": (6, 5, True), "peek": (6, 4, False), "talk": (6, 8, True),
    "wave": (6, 7, True), "think": (6, 4, True), "hop": (6, 9, True), "sleep": (6, 3, True),
    "charge": (6, 9, True), "alert": (6, 8, True), "turn": (6, 6, False), "beam": (6, 8, False),
}


def make(**kw):
    b = Behavior(ANIMS, now=0.0, x=500, rng=random.Random(kw.pop("seed", 1)), **kw)
    b.set_floor(50, 1870)
    return b


def run(b, start, end, step=1 / 30):
    """Tick from start to end; return the frames seen."""
    frames, t = [], start
    while t < end:
        frames.append(b.tick(t))
        t += step
    return frames, t


def test_greets_with_a_wave_then_carries_on():
    b = make()
    assert b.tick(0).anim == "wave"
    frames, _ = run(b, 0, 30)
    assert {f.anim for f in frames} - {"wave"}


def test_walks_with_turns_and_stays_on_the_floor():
    b = make(seed=3, sleep_after=0)
    frames, _ = run(b, 0, 300)
    walks = [f for f in frames if f.anim == "walk"]
    assert walks, "never walked"
    assert all(50 <= f.x <= 1870 for f in frames)
    # left-facing walk is mirrored; turning between stances uses the turn strip
    assert {f.mirror for f in walks} == {True, False}
    assert any(f.anim == "turn" for f in frames)


def test_no_walking_when_walk_is_off():
    b = make(walk=False, sleep_after=0)
    frames, _ = run(b, 0, 200)
    assert all(f.anim != "walk" for f in frames) and all(f.x == 500 for f in frames)


def test_alert_interrupts_anything_and_ends():
    b = make()
    run(b, 0, 10)
    b.react("hop", 10)
    b.set_alert(True, 10)
    frames, t = run(b, 10, 12)
    assert frames[-1].anim == "alert"
    b.set_alert(False, t)
    frames, _ = run(b, t, t + 5)
    assert frames[-1].anim != "alert"


def test_sleeps_after_inactivity_and_wakes_with_a_hop():
    b = make(sleep_after=60, walk=False)
    frames, t = run(b, 0, 70)
    assert frames[-1].anim == "sleep" and b.asleep
    b.wake(t)
    frames, _ = run(b, t, t + 3)
    assert not b.asleep and "hop" in {f.anim for f in frames}


def test_agent_work_thinks_then_charges():
    b = make()
    b.set_working(True, 1)
    frames, _ = run(b, 1, 10)
    assert frames[-1].anim == "think"
    frames, _ = run(b, 10, 65)
    assert frames[-1].anim == "charge"
    b.set_working(False, 65)
    b.react("hop", 65)
    assert b.tick(65.05).anim == "hop"


def test_reaction_plays_out_before_the_mood():
    b = make()
    run(b, 0, 5)
    b.react("wave", 5)
    b.set_talking(True, 5)
    assert b.tick(5.1).anim in ("wave", "turn")
    frames, _ = run(b, 5.1, 9)
    assert frames[-1].anim == "talk"


def test_hidden_ducks_then_peeks_now_and_then():
    b = make()
    run(b, 0, 3)
    b.set_hidden(True, 3)
    frames, t = run(b, 3, 130)
    anims = [f.anim for f in frames]
    assert None in anims and anims.count("peek") > 10 and "walk" not in anims
    b.set_hidden(False, t)
    frames, _ = run(b, t, t + 3)
    assert frames[0].anim == "peek" and frames[-1].anim not in (None, "peek")


def test_drag_and_drop_falls_and_lands():
    b = make()
    run(b, 0, 2)
    b.hold(900, 300, 2)
    assert b.tick(2.1).anim == "hop" and b.tick(2.1).lift == 300
    b.release(2.2)
    frames, _ = run(b, 2.2, 3.5)
    assert frames[0].lift > 0 and frames[-1].lift == 0
    assert any(f.anim == "hop" and f.index in (4, 5) for f in frames)


def test_drop_outside_the_floor_is_pulled_back():
    b = make()
    b.hold(5000, 0, 1)
    b.release(1)
    assert b.x == 1870


def test_beam_faces_its_side():
    b = make()
    run(b, 0, 3)
    b.react("beam", 3)
    frames, _ = run(b, 3, 5)
    beams = [f for f in frames if f.anim == "beam"]
    assert beams and len({f.mirror for f in beams}) == 1
