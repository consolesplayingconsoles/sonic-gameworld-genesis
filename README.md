# sonic-gameworld-genesis

Converting **Sonic the Hedgehog's Gameworld** (Sega Pico, 1994) so it runs on
Mega Drive / Genesis hardware.

A Pico ROM is already Mega Drive code: same 68000, same VDP, same header slot.
What differs is the I/O. A Pico has no controller ports; it has six storybook
page positions, a drawing pen, and sound behind a command port. So this is a
substitution at a handful of addresses, not a recompile.

This repo is the first target of a private skill that generalises the
procedure. It exists so the procedure gets tested against a real game instead
of being written in the abstract, and so what breaks is written down.

**It ships a patch, never a ROM.** You need your own dump.

## State

| | |
|---|---|
| Pico I/O registers found | 5, across 11 sites |
| patched | all Pico I/O, TMSS unlock, page sensor, console string, header |
| not patched | pen coordinates (a pad cannot point) |
| audio | out of scope |
| in Genesis Plus GX and PicoDrive | boots to the title screen and first menu |
| tested on hardware | black screen, cause not yet found |

The pad works: D-pad, B as the Pico's red button, Start standing in for the
pen. What it cannot do is point, because the pen is an absolute coordinate and
a pad has none, so anything that needs a cursor placed somewhere specific is
still out of reach. [FINDINGS.md](FINDINGS.md) quotes the decoded code and the
measurements behind every claim here.

## Build

```
cp .env.sample .env     # fill PICO_ROM, pick PAGE 0-5
./build.sh
```

Writes `rom/` (gitignored) and an `.ips` beside it.

The page matters: there is no page sensor on a Mega Drive, and on this game the
physical page *is* the mode selector, so one build reaches one page's activity.
Six builds reach six.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
