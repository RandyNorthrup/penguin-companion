"""What the penguin is doing from moment to moment.

Pure Python, no Qt: the window asks `tick()` which frame to draw and where,
and tells the behaviour what happened (a click, a drag, an agent at work).
Times are seconds on any monotonic clock.

Moods, highest first: hidden, alert, talk, think (an answer on its way),
attend (you're typing to it), work (an agent is busy: think, then charge),
sleep, and ambient (wandering, idling, the odd wave). One-off reactions (a
hop, a wave, a beam) play out before the mood takes over again, unless the
new mood is alert or hidden.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Frames of the `turn` strip: 0 side right, 1 three-quarter right, 2 front,
# 3 three-quarter left, 4 side left, 5 side left with a little hop. Any change
# of stance plays the part of the strip between the two.
TURN = {
    ("right", "front"): [0, 1, 2],
    ("front", "right"): [2, 1, 0],
    ("left", "front"): [4, 3, 2],
    ("front", "left"): [2, 3, 4],
    ("right", "left"): [0, 1, 2, 3, 4],
    ("left", "right"): [4, 3, 2, 1, 0],
}
TURN_FPS = 10


@dataclass
class Clip:
    anim: str | None  # None draws nothing (hidden between peeks)
    frames: list[int]
    fps: float
    loop: bool = False
    mirror: bool = False
    duration: float | None = None  # loops: how long to play; None until something changes
    stance: str = "front"  # "front", "right" or "left" while this clip plays
    reaction: bool = False


@dataclass
class Frame:
    anim: str | None
    index: int
    mirror: bool
    x: float
    lift: float


class Behavior:
    WALK_MIN = 120.0  # shortest walk, px
    WALK_MAX = 700.0  # longest walk, px
    CHARGE_AFTER = 60.0  # seconds of agent work before thinking turns to charging
    GRAVITY = 2600.0  # px/s² when dropped

    def __init__(
        self,
        anims: dict[str, tuple[int, float, bool]],
        *,
        now: float,
        x: float = 600.0,
        rng: random.Random | None = None,
        walk: bool = True,
        sleep_after: float = 600.0,
        speed: float = 48.0,
    ):
        self.anims = anims
        self.rng = rng or random.Random()
        self.walk_enabled = walk
        self.sleep_after = sleep_after
        self.speed = speed
        self.x = x
        self.left, self.right = 0.0, 1920.0
        self.lift = 0.0
        self.stance = "front"
        self.held = self.falling = False
        self.hidden = self.alert = self.talking = self.thinking = self.attending = False
        self.working_since: float | None = None
        self.asleep = False
        self.last_interaction = now
        self.mood = "ambient"
        self._vy = 0.0
        self._target: float | None = None
        self._queue: list[Clip] = []
        self._last = now
        self._start(Clip("wave", self._all("wave"), self._fps("wave"), reaction=True), now)

    # -- what the outside world tells it

    def set_floor(self, left: float, right: float) -> None:
        self.left, self.right = left, max(left, right)
        if not self.held:
            self.x = min(max(self.x, self.left), self.right)
        if self._target is not None:
            self._target = min(max(self._target, self.left), self.right)

    def set_alert(self, on: bool, now: float) -> None:
        self._flag("alert", on, now)

    def set_talking(self, on: bool, now: float) -> None:
        self._flag("talking", on, now)

    def set_thinking(self, on: bool, now: float) -> None:
        self._flag("thinking", on, now)

    def set_attending(self, on: bool, now: float) -> None:
        self._flag("attending", on, now)

    def set_hidden(self, on: bool, now: float) -> None:
        self.hidden = on
        if not on:
            self.asleep = False
            self.last_interaction = now

    def set_working(self, on: bool, now: float) -> None:
        if on and self.working_since is None:
            self.working_since = now
            self.wake(now)
        elif not on:
            self.working_since = None

    def wake(self, now: float) -> None:
        """Attention of any kind: resets the sleep timer and wakes it up."""
        self.last_interaction = now
        if self.asleep and not self.hidden:
            self.asleep = False
            self._play([Clip("sleep", [2, 1, 0], 6, reaction=True), Clip("hop", self._all("hop"), self._fps("hop"), reaction=True)], now)

    def poke(self, now: float) -> None:
        if self.asleep:
            self.wake(now)
        else:
            self.last_interaction = now
            self.react("wave", now)

    def react(self, anim: str, now: float, times: int = 1) -> None:
        """Play a one-off (hop, wave, beam...) then carry on."""
        if self.held or self.falling or self.hidden:
            return
        if anim == "beam":
            side = self.stance if self.stance in ("left", "right") else "right"
            clips = self._turn(side)
            clips.append(Clip("beam", self._all("beam"), self._fps("beam"), mirror=side == "left", stance=side))
        else:
            clips = self._to_front()
            clips.append(Clip(anim, self._all(anim) * times, self._fps(anim)))
        for clip in clips:
            clip.reaction = True
        self._play(clips, now)

    def hold(self, x: float, lift: float, now: float) -> None:
        """Being dragged by the mouse."""
        self.held, self.falling = True, False
        self.x, self.lift = x, max(0.0, lift)
        self._target, self._queue = None, []
        self.asleep = False
        self.last_interaction = now

    def release(self, now: float) -> None:
        self.held = False
        self.x = min(max(self.x, self.left), self.right)
        self.stance = "front"
        if self.lift > 0:
            self.falling, self._vy = True, 0.0
        else:
            self._play([Clip("hop", [4, 5], 9, reaction=True)], now)

    # -- the frame to draw

    def tick(self, now: float) -> Frame:
        dt = max(0.0, min(now - self._last, 0.25))
        self._last = now
        if self.held:
            return Frame("hop", 2, False, self.x, self.lift)
        if self.falling:
            self._vy += self.GRAVITY * dt
            self.lift -= self._vy * dt
            if self.lift > 0:
                return Frame("hop", 3, False, self.x, self.lift)
            self.lift, self.falling = 0.0, False
            self._play([Clip("hop", [4, 5], 9, reaction=True)], now)
        wanted = self.wanted_mood(now)
        if wanted != self.mood and (not self._clip.reaction or wanted in ("alert", "hidden")):
            self._plan(wanted, now)
        clip = self._clip
        if clip.anim == "walk" and self._target is not None:
            step = self.speed * dt
            if abs(self._target - self.x) <= step:
                self.x, self._target = self._target, None
                self._advance(now)
            else:
                self.x += step if self._target > self.x else -step
        elif self._finished(now):
            self._advance(now)
        clip = self._clip
        n = int((now - self._clip_start) * clip.fps)
        index = clip.frames[n % len(clip.frames)] if clip.loop else clip.frames[min(n, len(clip.frames) - 1)]
        return Frame(clip.anim, index, clip.mirror, self.x, self.lift)

    def wanted_mood(self, now: float) -> str:
        if self.hidden:
            return "hidden"
        if self.alert:
            return "alert"
        if self.talking:
            return "talk"
        if self.thinking:
            return "think"
        if self.attending:
            return "attend"
        if self.working_since is not None:
            return "charge" if now - self.working_since >= self.CHARGE_AFTER else "think"
        if self.asleep or (self.sleep_after > 0 and now - self.last_interaction >= self.sleep_after):
            return "sleep"
        return "ambient"

    # -- planning

    def _flag(self, name: str, on: bool, now: float) -> None:
        if getattr(self, name) != on:
            setattr(self, name, on)
            if on:
                self.wake(now)

    def _all(self, anim: str) -> list[int]:
        return list(range(self.anims[anim][0]))

    def _fps(self, anim: str) -> float:
        return self.anims[anim][1]

    def _turn(self, to: str) -> list[Clip]:
        if self.stance == to:
            return []
        return [Clip("turn", list(TURN[(self.stance, to)]), TURN_FPS, stance=to)]

    def _to_front(self) -> list[Clip]:
        return self._turn("front")

    def _start(self, clip: Clip, now: float) -> None:
        self._clip, self._clip_start = clip, now
        self.stance = clip.stance

    def _play(self, clips: list[Clip], now: float) -> None:
        self._target = None
        self._queue = clips[1:]
        self._start(clips[0], now)

    def _finished(self, now: float) -> bool:
        clip, elapsed = self._clip, now - self._clip_start
        if clip.loop:
            return clip.duration is not None and elapsed >= clip.duration
        return elapsed >= len(clip.frames) / clip.fps

    def _advance(self, now: float) -> None:
        if self._queue:
            self._start(self._queue.pop(0), now)
        else:
            self._plan(self.wanted_mood(now), now)

    def _plan(self, mood: str, now: float) -> None:
        previous, self.mood = self.mood, mood
        self._target = None
        clips: list[Clip] = []
        if previous == "hidden" and mood != "hidden":
            clips.append(Clip("peek", [0, 1, 2, 4], 8))
        if mood == "hidden":
            if previous != "hidden":
                clips.append(Clip("peek", [4, 2, 1, 0], 8))
            clips.append(Clip(None, [0], 1, loop=True, duration=self.rng.uniform(20, 60)))
            clips.append(Clip("peek", self._all("peek"), self._fps("peek")))
        elif mood == "sleep":
            self.asleep = True
            clips += self._to_front()
            clips += [Clip("sleep", [0, 1, 2], self._fps("sleep")), Clip("sleep", [3, 4, 5], self._fps("sleep"), loop=True)]
        elif mood in ("alert", "talk", "think", "charge"):
            clips += self._to_front() + [Clip(mood, self._all(mood), self._fps(mood), loop=True)]
        elif mood == "attend":
            clips += self._to_front() + [Clip("idle", self._all("idle"), self._fps("idle"), loop=True)]
        else:
            clips += self._ambient()
        target = self._target
        self._play(clips, now)
        self._target = target

    def _ambient(self) -> list[Clip]:
        roll = self.rng.random()
        if self.walk_enabled and roll < 0.5 and self.right - self.left >= self.WALK_MIN:
            target = self._pick_target()
            side = "right" if target > self.x else "left"
            frames, fps, _ = self.anims["walk"]
            clips = self._turn(side)
            clips.append(Clip("walk", list(range(frames)), fps, loop=True, mirror=side == "left", stance=side))
            self._target = target
            return clips
        clips = self._to_front()
        if roll < 0.58:
            clips.append(Clip("wave", self._all("wave"), self._fps("wave")))
        clips.append(Clip("idle", self._all("idle"), self._fps("idle"), loop=True, duration=self.rng.uniform(4, 10)))
        return clips

    def _pick_target(self) -> float:
        lo = max(self.left, self.x - self.WALK_MAX)
        hi = min(self.right, self.x + self.WALK_MAX)
        for _ in range(8):
            target = self.rng.uniform(lo, hi)
            if abs(target - self.x) >= self.WALK_MIN:
                return target
        return self.left if self.x - self.left > self.right - self.x else self.right
