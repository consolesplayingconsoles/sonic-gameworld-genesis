# What the ROM actually does

Decoded from `Sonic The Hedgehog's Gameworld (USA)`, trace coverage 1.47%.
Every claim here is a decoded instruction, quoted. Nothing here is inferred
from documentation, because there is none.

## Pico I/O this game touches

5 registers, 11 sites.

### `$800003`: console buttons, read into RAM

```
0003FA  4278f80a          clr.w   $f80a.w
0003FE  11f900800003f80b  move.b  $800003.l, $f80b.w
000406  00780060f80a      ori.w   #$60, $f80a.w
00040C  4638f80b          not.b   $f80b.w
000410  3038f80a          move.w  $f80a.w, d0
```

So the raw byte lands at `$FFF80B`, bits 5 and 6 of the word above it are
forced set, and the byte is inverted: the hardware is **active low**. The
mask is `#$60` here, not the `#$FF60` seen elsewhere.

**The bit-to-button mapping is still unknown.** The only code that touches
`$FFF80A/B` is this routine itself; whatever tests the individual bits is in
the 98.5% the trace has not reached, past the computed `jmp (a0)` at
`$001F9E`. Deriving it is the next job, and until it is derived there is no
honest way to write the pad substitution: a guessed mapping would be
indistinguishable from a broken one.

### `$80000D`: storybook page sensor, six positions

```
00038E  10390080000d      move.b  $80000d.l, d0
000394  3e3c0005          move.w  #$5, d7
000398  0f00              btst.l  d7, d0
00039A  6600000a          bne.w   $3a6
00039E  51cffff8          dbra    d7, $398
0003A2  3e3cffff          move.w  #$ffff, d7
```

The loop walks bit 5 down to bit 0 and leaves `d7` holding the index of the
first set bit, or `$FFFF` when none is set. **A byte with bit N set means page
N**, which is what makes this one substitutable with no stub at all:
`moveq #1<<N,d0` is 2 bytes where the read was 6.

### `$800010` and `$800012`: sound

```
06D1EA  43f900800010      lea.l   $800010.l, a1
...
06D1C4  00404000          ori.w   #$4000, d0
06D1C8  33c000800012      move.w  d0, $800012.l
06D1CE  4eb90006d1e6      jsr     $6d1e6.l
06D1D4  4a3900800012      tst.b   $800012.l
06D1DA  6a04              bpl.b   $6d1e0
```

`$800012` takes the command word (with `#$4000` or'd in) **and** is the byte
polled afterwards. `$800010` is only ever loaded as a base pointer into `a1`.
7 of the 11 sites are `$800012`.

Not patched yet. The write to absent hardware is harmless; what matters is
whether any of the 7 polls is a *wait* loop rather than the conditional above,
because a wait on a chip that is not there hangs forever. That is a per-site
read, not a guess.

### `$800017`: write-only, unknown

```
000B64  7e40              moveq   #$40, d7
000B66  13c700800017      move.b  d7, $800017.l
```

Written once with `$40`, never read back anywhere in the trace. Left alone
deliberately: a write to absent hardware costs nothing, and a read we guessed
wrong about would hang.

## TMSS: why the first build booted black

The first build reached a Mega Drive and showed a black screen with no sound.
The trace says why, and it is not the sound hardware.

This ROM's only hardware writes are `$C00000` and `$C00004` (VDP data and
control) and `$C00011` (PSG). It never writes `$A14000`, and no Pico game ever
would: TMSS is a Mega Drive thing, so a Pico game has nothing to unlock.

On a Mega Drive that has TMSS, the VDP stays locked until something writes
`'SEGA'` to `$A14000`. The console boots, the 68000 runs the game, and nothing
it draws reaches the screen. A black screen with no sound is exactly the
symptom.

The fix is a 28-byte stub, written into the `$FF` filler at `$07F800` so
nothing moves and the ROM does not grow, with the reset vector at `$004`
pointed at it:

```
07F800  103900a10001           move.b  $a10001.l, d0     ; TMSS present?
07F806  0200000f               andi.b  #$f, d0
07F80A  670a                   beq.b   $7f816            ; no: skip the write
07F80C  23fc5345474100a14000   move.l  #'SEGA', $a14000.l
07F816  4ef900000210           jmp     $210.l            ; the game's own reset
```

The displacement is computed from the layout and asserted to land on an
instruction boundary, then checked by disassembling the built ROM: `beq.b`
goes to `$07F816`, which is where `jmp` starts.

## It runs in Genesis Plus GX

The build that showed a black screen on hardware boots in Genesis Plus GX,
through the Sega Pico logo and into the game's first menu, with the pen cursor
drawn:

> How Many Players? One / Two. Difficulty Level: Easy / Hard.

So page 0 is a real activity and the conversion's logic is sound. Whatever
blacks the screen is something the emulator does not model, and the first
candidate is the thing it cannot model here: TMSS. Genesis Plus GX emulates it
only with a boot ROM in its system folder, and there is none.

Two header fields were also wrong for a Mega Drive, and are now set: `$190`
I/O support was blank (now `J`, joypad) and `$1F0` region said `4`, US NTSC
only (now `JUE`). Both sit below `$200`, so the checksum is unaffected.

## What `patch.py` does today

| | |
|---|---|
| TMSS | unlocked at reset, guarded by the `$A10001` version check |
| header `$190` / `$1F0` | joypad declared, region `JUE` instead of `4` |
| page sensor | fixed at a chosen page, `--page 0` to `5` |
| console string at `$100` | `SEGA MEGA DRIVE ` |
| header checksum at `$18E` | recomputed over `$000200` to the end |
| input | **not patched**, mapping unknown |
| sound | **not patched**, polls not yet classified |
| audio | out of scope |

So the question this build answers is only: **does it boot and reach page N's
activity on a Mega Drive?** It cannot be played yet. If it still shows nothing
after the TMSS fix, the next suspect is the sound busy poll at `$800012`: 7
sites, and any one of them that waits in a loop waits forever on a chip that
is not there.
