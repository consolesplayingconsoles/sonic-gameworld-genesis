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

## Every Pico I/O access is now gone

Leaving the pad, sound and control accesses in place was wrong, and OpenEmu
showed it: the same ROM ran in Genesis Plus GX and PicoDrive and stayed black
there. A read of `$800003` on a Mega Drive returns whatever the bus happens to
hold, which is a different value in every emulator and on hardware, so the game
was taking a different path everywhere. That is not a port.

All ten sites are now replaced, same length each time:

| site | was | is |
|---|---|---|
| `$0003FE` | `move.b $800003.l,$f80b.w` | `move.b #$FF,$f80b.w` (active low: nothing pressed) |
| `$000B66` | `move.b d7,$800017.l` | `nop` |
| six sites | `move.w ...,$800012.l` | `nop` |
| `$06D1D4` | `tst.b $800012.l` | `moveq #0,d0`, so the `bpl` after it goes the same way every time |
| `$06D202` | `move.w (a1),d0` (the FIFO count, `a1` = `$800010`) | `moveq #0,d0`, which makes the `beq` below it taken and the `dbra` loop that streams samples into `$800010` unreachable |

The `lea $800010.l,a1` at `$06D1EA` stays, because nothing dereferences it any
more and removing it would leave a stale `a1` for anything that did. The I/O
scan confirms it is the only `$8000xx` left and that it is never read or
written.

The pad site is where the real Mega Drive pad read goes once the bit mapping is
known. Until then it is a fixed "nothing pressed", which at least behaves the
same everywhere.

## The pad works, and the register map was wrong

Genesis Plus GX emulates the Pico itself, and its source is the authority this
project had been inferring around. Reading it corrected the map in three
places and handed over the one thing tracing could not reach:

| | this project had | the core says |
|---|---|---|
| `$800001` | unknown | **VERSION register** (region code) |
| `$800003` | pad, active low | pad, active low, `~input.pad[0]` |
| `$800005`/`$800007` | pen X, pen Y | **pen X, MSB and LSB** |
| `$800009`/`$80000B` | not seen | **pen Y, MSB and LSB** |
| `$80000D` | page, one bit per page | page, `(1 << pages) - 1`: a **mask**, not one bit |
| `$800010`/`$800011` | sound base | ADPCM data, reads `$FF` |
| `$800012` | sound command + busy | ADPCM control, reads **`$80`** |

The mask detail does not change this patch: the game's loop takes the *highest*
set bit, so one bit at N and a mask of N+1 bits give the same page. The `$80`
does: the `tst.b`/`bpl` pair sees a negative value on a Pico, so the branch is
not taken, and the replacement is now `moveq #-1` rather than `moveq #0`.

### The pad byte

`$800003` is active low with **bit 0 up, 1 down, 2 left, 3 right, 4 red,
7 pen**, which is exactly why the game ors `$60` over bits 5 and 6 before
inverting: those two are unused.

A Mega Drive pad's TH=1 read is also active low, with bits 0-3 in the **same
order** and bit 4 the B button. So four directions and the red button need no
rearranging whatsoever: force the unused bits high and the byte is already
Pico-shaped. Start stands in for the pen, the one thing a pad cannot be.

```
07F820  move.b #$40,$a10009.l   TH is an output
07F828  move.b #$40,$a10003.l   TH high
07F834  move.b $a10003.l,d0     ..CBRLDU, active low
07F83A  move.b #$00,$a10003.l   TH low
07F846  move.b $a10003.l,d1     ..SA..DU
07F84C  ori.b #$e0,d0           unused bits and pen high
07F850  btst #5,d1              Start held?
07F854  bne.b $7f85a
07F856  bclr #7,d0              yes: pen down
07F85A  move.b d0,$f80b.w       where the Pico read used to land
07F85E  rts
```

Measured in Genesis Plus GX by holding each button and reading `$FFF80A`
after the game's own inversion:

| held | `$FFF80A` | |
|---|---|---|
| nothing | `0000` | |
| Down | `0200` | bit 1 |
| Right | `0800` | bit 3 |
| B | `1000` | bit 4, the red button |
| Start | `8000` | bit 7, the pen |

## $800015: a peripheral handshake the trace never saw

The trace reaches 1.5% of this ROM, and `IO_SITES` was built from what it
found. Scanning the **whole** ROM for decodable `$8000xx` operands turns up 28
more sites, none of them traced:

```
000CE6  move.b  #$20, $800015.l      write a command
000CEE  move.b  #$60, $800017.l
000CF6  btst.b  #$4, $800015.l       wait for the answer
000EF2  move.b  $800015.l, d0        ... and the same loop again, 24 sites in all
000EFC  dbne    d7, $ef2
```

It is a write-then-poll handshake with a peripheral controller, and on a Mega
Drive every one of those reads is the open bus: a different answer in every
emulator and on hardware, so the game decides a device is or is not there based
on noise. The loops are bounded (`dbne`/`dbeq` against `d7 = $FF`), so they
time out rather than hang, but what the game does afterwards depends entirely
on what the noise said.

Reads are now zero and writes are gone. Zero is the game's own "nobody is
pulling the line": one path exits at once with no data, the other spins out its
own timeout and takes the error branch it was written to take. Both are what
the game does when no peripheral answers, and now it is the same answer
everywhere.

**The lesson is about method, not this register.** A trace tells you what a
game does on the paths it reached. For I/O you want every site in the ROM,
which means decoding candidate operands across the whole image and accepting
some false positives (art data decodes as instructions surprisingly often: of
36 apparent hits left, every one is a `move.b #$80,$N(a6)`).

## What a scan of absolute addresses cannot see

Two Pico accesses in this game never name their address: they load it into a
register first. A dataref scan, and therefore everything built on one, is blind
to both.

```
00065E  movea.l #$800005, a0      the pen
000664  movep.w $0(a0), d0        <- the read itself names only a0
06D1EA  lea.l   $800010.l, a1     the sound FIFO
```

The pen matters: this game **does** read it, which contradicts the earlier note
here that it never did. Unpatched it reads the open bus, which answers
differently in every emulator and on hardware, and the game clamps whatever it
gets to X `$3C`-`$15F` and puts the cursor there. It now returns `$8000`, bit
15 set, which is the game's own "pen not down".

So the rule is: after neutralising what the scan finds, search for
**instructions that load a Pico address into a register** (`lea`, `movea.l
#imm`). In this ROM that is exactly two places, and both needed patching.

## The game's own boot is the standard Sega one

Worth knowing before patching any of it:

```
000210  lea     $276(pc), a5         a table of three pointers
00021C  move.l  #'SEGA', d0
000222  movep.l d0, $0(a2)           a2 = $800019 here, $A14000 on a Mega Drive
00023E  move.l  d0, -(a6)            clears all 64 KB of work RAM
000230  move.b  (a5)+, d5 / move.w d5, (a4)    all 24 VDP registers
```

It is the same boot every Mega Drive game ships, with one substitution: the
`'SEGA'` write goes to the Pico's `$800019` instead of TMSS's `$A14000`. That
is why the TMSS unlock genuinely has to be added, and it is also why RAM noise
is not a suspect: the game clears all of it. Register 1 is `$14` at boot
(display off), enabled later through the shadow at `$FFF804`.

## The actual cause: an unmapped WRITE stalls the 68000

Every fix before this was a guess, because the failure was never reproduced on
this machine. BlastEm reproduces it and names it in one line:

```
[libretro ERROR] Unmapped byte write to 800019
```

That is the game's own boot, `movep.l d0,$0(a2)` with `a2 = $800019`, the
`'SEGA'` handshake. A **read** of absent hardware returns the open bus and the
machine carries on. A **write** to an address nothing answers leaves the 68000
waiting for a /DTACK that never comes, and it stops there: at the game's first
instruction, before anything draws. That is the black screen, and it is why
Genesis Plus GX and PicoDrive run the ROM happily while the console does not.

`$A14000` is not the answer either: a console without TMSS has nothing there,
and BlastEm halts on that too. The handshake has no meaning on a Mega Drive at
all, so it now writes into scratch RAM, and the TMSS unlock stays in the boot
stub where the version check guards it.

BlastEm then reported one more, a read this time, which found the pen's **Y**
half: `movep.w $4(a0),d1` through the same `a0`, reading `$800009`/`$80000B`.
No scan had found it, because the instruction names only `a0`.

The build is now clean: **zero unmapped accesses**, and BlastEm runs it to the
title screen.

### How to do this the first time instead of the tenth

Use an accuracy-focused core before a lenient one. `blastem_libretro` reports
every unmapped access and halts where the hardware stalls, which turns "black
screen" into an address and a line of code. Genesis Plus GX and PicoDrive are
for seeing the game once it runs, not for finding out why it does not.

Control first: confirm the strict core runs a known-good ROM of that system, so
an exit means something.

## The Z80, which is why hardware was black

Real hardware showed the same black screen as OpenEmu, which settles the
earlier open question: OpenEmu was right and the two cores that ran it are the
lenient ones. (The build tested did not yet contain this fix: it is still
unverified on hardware.)

This ROM never touches the Z80. No Pico game does: a Pico has no Z80, no
`$A11100`, no `$A11200`. A Mega Drive powers its Z80 up **running**, with RAM
holding whatever the last power-on left, and the Z80 reaches the 68000 bus
through its bank window, VDP ports included. An emulator zeroes that RAM, so
the Z80 executes NOPs and nothing shows; hardware executes garbage and
scribbles over the display.

The boot stub now takes the bus and holds the Z80 in reset before anything
else, which costs nothing here: the ADPCM chip it would have driven does not
exist on a Mega Drive either.

```
07F800  move.w  #$100, $a11100.l    take the bus from the Z80
07F808  move.w  #$0, $a11200.l      and hold it in reset
07F810  move.b  $a10001.l, d0       TMSS present?
...
```

(This was a real defect, though not the black screen: that was the unmapped
write above.) **The lesson for any conversion: an emulator is not evidence
about boot-time hardware state.** Zeroed RAM, a silent Z80 and a forgiving bus are all things a
real console does not give you.

## OpenEmu: unexplained, not fixed

OpenEmu showed a black screen on every build tried, including one with no
absent-hardware access left. **This was never reproduced and never diagnosed.**
Genesis Plus GX and PicoDrive both ran every one of those builds; PicoDrive
looked like a reproduction and was not, it was simply mid-intro.

So there is no evidence about OpenEmu either way. Its Mega Drive core is the
older GenesisPlus plugin rather than GX, which is a plausible reason and
nothing more. If it matters later, the test is to compare against that bundled
core directly rather than against a third emulator.

Pluto plays Mega Drive ROMs in OpenEmu on purpose. Its core is the strict one:
hardware proved it right about this ROM while two lenient cores ran it happily,
so Play failing there is the early warning that the cartridge would be black.
The RetroArch entry stays configured for when you want the lenient view.

## The pen cursor

The game decodes the pen like this, which is the whole contract a substitute
has to meet:

| | raw word | the game computes | clamped to |
|---|---|---|---|
| X | `$800005`/`$800007` | `raw - $3C` | 0 to `$15F` |
| Y | `$800009`/`$800B` | `raw - $1FC` | 0 to `$1FF` |

and bit 15 set means the pen is not down, in which case it returns `$FFFF` and
the caller ignores the coordinates.

So the cursor lives in RAM and the two read sites just load it. Both are
`movep.w`, four bytes, and `move.w $FB16.w,d0` is also four, so the sites need
no stub at all:

```
000664  move.w  $fb16.w, d0     was movep.w $0(a0),d0
00068C  move.w  $fb18.w, d1     was movep.w $4(a0),d1
```

The pad stub keeps `$FFFB12`/`$FFFB14` as the cursor and writes `$FFFB16`/
`$FFFB18` as the raw form the game expects, adding the offsets back and setting
bit 15 whenever B is not held. **A held + D-pad** moves it two pixels a frame,
clamped to 0-320 and 0-223, and the directions are withheld from the game while
A is down so one press does not both move the cursor and walk a menu.

RAM boots cleared, and a raw zero would read as the pen pressed against the top
left corner, so the first frame centres the cursor and sets a flag byte.

## What `patch.py` does today

| | |
|---|---|
| Z80 | bus taken and held in reset at boot, before anything draws |
| Pico I/O | all ten sites neutralised: no `$8000xx` access left |
| TMSS | unlocked at reset, guarded by the `$A10001` version check |
| header `$190` / `$1F0` | joypad declared, region `JUE` instead of `4` |
| page sensor | fixed at a chosen page, `--page 0` to `5` |
| console string at `$100` | `SEGA MEGA DRIVE ` |
| header checksum at `$18E` | recomputed over `$000200` to the end |
| input | the Mega Drive pad: D-pad, B as the red button, Start as the pen |
| sound | silenced at the source: no writes reach the absent chip |
| audio | out of scope |

So the question this build answers is only: **does it boot and reach page N's
activity on a Mega Drive?** It cannot be played yet. If it still shows nothing
after the TMSS fix, the next suspect is the sound busy poll at `$800012`: 7
sites, and any one of them that waits in a loop waits forever on a chip that
is not there.
