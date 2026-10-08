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
| patched | TMSS unlock, page sensor, console string, header checksum |
| not patched | input (bit mapping unknown), sound (polls unclassified) |
| audio | out of scope |
| tested on hardware | first build booted black: TMSS, now fixed |

So the only question this build answers is whether it boots and reaches a
page's activity. You cannot play it yet, and the reason input is missing is
written down rather than guessed at: see [FINDINGS.md](FINDINGS.md), which
quotes the decoded code behind every claim here.

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
