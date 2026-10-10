# sonic-gameworld-genesis

**Sonic The Hedgehog's Gameworld** (Sega Pico, 1994), ported to the Sega Mega
Drive / Genesis and played with a normal controller.

The Pico was a children's console shaped like a storybook: a pen on a drawing
tablet, a sensor reading which page is open, one red button and a D-pad. Its
ROMs are already Mega Drive code, same 68000, same VDP, same header slot, so
the port is not a recompile. It is a substitution: everywhere the game reaches
for hardware a Mega Drive does not have, something it does have answers
instead.

**It ships a patch, never a ROM.** You bring your own dump of the original.

## State

| | |
|---|---|
| Pico I/O registers found | 5, across 11 sites |
| patched | Z80 silenced, all Pico I/O including the $800015 handshake, TMSS unlock, page sensor, console string, header |
| not patched | nothing known |
| audio | the PSG plays as it always did; the Pico's sampled voice is gone |
| in Genesis Plus GX and PicoDrive | boots to the title screen and first menu |
| in BlastEm (accuracy core) | runs, zero unmapped accesses |
| in OpenEmu | boots: the core that matched the console all along |
| tested on hardware | black until now: an unmapped write stalled the 68000 at the first instruction. Retest pending |

The pad works: D-pad, B as the Pico's red button, Start standing in for the
pen. What it cannot do is point, because the pen is an absolute coordinate and
a pad has none, so anything that needs a cursor placed somewhere specific is
still out of reach. [FINDINGS.md](FINDINGS.md) quotes the decoded code and the
measurements behind every claim here.

## Build

```
cp .env.sample .env     # fill PICO_ROM
./build.sh
```

Writes `rom/` (gitignored) and an `.ips` beside it.

## Controls

| pad | Pico |
|---|---|
| D-pad | moves the hand, which is always on screen |
| A | switches the D-pad between the hand and the game's own directions |
| B | taps where the hand is |
| C held + Left/Right | turns the storybook page, wrapping through closed |
| Start | the red button (red for red) |

The hand is visible all the time because the Pico reports **where** the pen is
separately from **whether its tip is pressed**. Resting on the tablet draws the
hand and selects nothing; the tip switch is the click. Nothing is rendered by
the patch: the game draws its own hand, it just needed to be told the pen is
there.

There is no page sensor on a Mega Drive, and on this game the page *is* the
mode selector, so turning it from the pad is what makes more than one of its
activities reachable from a single build.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
