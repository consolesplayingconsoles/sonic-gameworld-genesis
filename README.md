# sonic-gameworld-genesis

**A port of Sonic The Hedgehog's Gameworld (Sega Pico, 1994) to the Sega Mega
Drive / Genesis.** It is a game, not a tool: you end up playing a Pico title on
a Mega Drive, with a normal controller in your hands.

The Pico was a children's console shaped like a storybook, with a pen on a
drawing tablet, a page sensor under the book, one red button and a D-pad. Its
ROMs are already Mega Drive code (same 68000, same VDP, same header slot), so
porting one is not a recompile. It is a substitution: every place the game
talks to hardware the Mega Drive does not have, answered by something it does.

The patcher in this repo (`patch.py`) is how the port is produced, not the
point of it. **It ships a patch, never a ROM**, so you bring your own dump of
the original.

## State

| | |
|---|---|
| Pico I/O registers found | 5, across 11 sites |
| patched | Z80 silenced, all Pico I/O including the $800015 handshake, TMSS unlock, page sensor, console string, header |
| not patched | pen coordinates (a pad cannot point) |
| audio | out of scope |
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
| D-pad | the Pico's D-pad |
| Start | the red button (red for red) |
| B | pen tap |
| A held + D-pad | moves the pen cursor (the cursor itself is not built yet) |
| C held + Left/Right | turns the storybook page, wrapping through closed |

There is no page sensor on a Mega Drive, and on this game the page *is* the
mode selector, so turning it from the pad is what makes more than one of its
activities reachable from a single build.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
