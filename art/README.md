# The penguin's art

An opt-in desktop pet built from the owner's own character: an electric
penguin, charcoal with a cream face and belly and a white penguin mark,
orange ear tufts, beak and toe claws, blue armour plates with yellow
lightning bolts, and glowing cyan nodes on the collar and flippers. It is
not a Meta character, name or likeness.

The companion was designed for Muse Desktop in
[muse-spark-code](https://github.com/RandyNorthrup/muse-spark-code) (plan
D91.30), where it walks along the status bar, reacts to the agent, and peeks
up from behind the status bar while hidden. This repository holds the
character's art: the reference sheet, the prompts and tools that made the
animations, and how they were made. The animation strips themselves live in
[`../penguin_companion/anim/`](../penguin_companion/anim), where the app loads
them; paths below are relative to this folder.

## Files

| Path                         | What it is                                                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `source/reference-sheet.jpg` | The owner's character sheet (front, side, jump, charge, beam and angry poses), as supplied on 2026-10-05.         |
| `../penguin_companion/anim/<name>.png` | One horizontal strip per animation, 240 px tall, frames left to right, transparent background. |
| `../penguin_companion/anim/manifest.json` | Per animation: `frames`, the frame width `w` and height `h` in pixels, the playback rate `fps`, `loop`, and the display `scale`. |
| `tools/penguin-slice.py`     | Keys the chroma-green sheets, slices each grid into frames, aligns rows and writes the strips and the manifest.   |
| `tools/penguin-cut.py`       | Cuts the six reference poses out of `source/reference-sheet.jpg` (used to check the strips against the original). |
| `prompts.md`                 | The exact twelve image prompts that produced the sheets.                                                          |

Frame `i` of an animation is the `w` × `h` rectangle at `x = i * w` in its
strip.

## The twelve animations

| Name     | Frames | fps | Loops | Used for                                                       |
| -------- | -----: | --: | :---: | -------------------------------------------------------------- |
| `walk`   |      8 |  10 |  yes  | Walking along the status bar (facing right; mirrored for left) |
| `idle`   |      6 |   5 |  yes  | Standing, with a blink                                         |
| `peek`   |      6 |   4 |  no   | Peeking up from behind the status bar while hidden             |
| `talk`   |      6 |   8 |  yes  | Answering                                                      |
| `wave`   |      6 |   7 |  yes  | Greeting                                                       |
| `think`  |      6 |   4 |  yes  | Waiting for an answer                                          |
| `hop`    |      6 |   9 |  yes  | A finished turn (when agent reactions are on)                  |
| `sleep`  |      6 |   3 |  yes  | Inactivity                                                     |
| `charge` |      6 |   9 |  yes  | Working (a long task running)                                  |
| `alert`  |      6 |   8 |  yes  | Something needs the person (points to a waiting approval)      |
| `turn`   |      6 |   6 |  no   | Turning from facing right to facing left                       |
| `beam`   |      6 |   8 |  no   | Celebrating (a merge, a green check)                           |

The sheets were drawn at slightly different scales, so the manifest gives each
animation a display `scale` that keeps the penguin one size on screen. They
were matched by standing height against `idle` (the ear-tuft span used at
first changes with the pose, and made the penguin shrink when it talked):
`hop` 1.13, `charge` 1.17, `alert` 1.05, `peek` 0.47 (matched by head width),
the rest 1. `tools/penguin-slice.py` writes the same values.

## How the sheets were made

1. The owner's reference sheet was uploaded to an image-generation chat in
   the owner's own ChatGPT account on 2026-10-05.
2. Each prompt in `prompts.md` asked for one sprite sheet in a fixed grid
   (walk 4 × 2, the others 3 × 2) on a flat chroma-key green (#00B140), with
   the same character size, camera and baseline in every frame, and no
   shadows, text or grid lines.
3. `tools/penguin-slice.py` removed the green, cut the grid, aligned each row
   by its lowest opaque pixel and mean centre, cropped every frame to the
   union box of its animation, and wrote the strips at 240 px into `../penguin_companion/anim/`.

Under OpenAI's terms of use the person who prompts owns the output; the
character itself is the owner's. Before the art ships anywhere, record this
provenance in that product's third-party notices and re-check the white
belly mark against publishers' penguin logos.

The raw 1536 × 1024 sheets (19 MB) are not in this repository; they were
archived at `~/archive/companion-sheets/` on the Kubuntu desktop. Re-running
the slicer needs them (`python tools/penguin-slice.py <sheets-dir>`, with
Pillow installed); the strips here are the build input.

## Still to do

- 2× strips (480 px) for high-density displays, regenerated from the sheets
  with the same slicer, or re-prompted at a larger size if 2× upscaling blurs.
- A left-facing `walk` is the mirrored strip; check that the lightning bolts
  and the belly mark read correctly when mirrored, or draw a left sheet.
- A high-contrast outline variant and a reduced-motion still for each pose.
