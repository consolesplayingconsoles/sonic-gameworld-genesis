#!/usr/bin/env python3
"""Patch Sonic the Hedgehog's Gameworld (Sega Pico) to run on a Mega Drive.

Applies only substitutions justified by decoded code, listed in FINDINGS.md.
Every patch is size-neutral: this is a linked binary with no relocation
information, so moving a byte breaks every branch over it.

    python3 patch.py <pico rom> <output rom>

The storybook page is no longer baked in: it starts closed and C and Start turn it.
"""
import struct
import sys

CONSOLE = b"SEGA MEGA DRIVE "      # 16 bytes at $100, space padded
CHECKSUM_AT = 0x18E

# A Pico declares neither of these, having no joypad and one region. A Mega Drive ROM says
# which devices it uses ($190) and which regions it is for ($1F0); this one's says "4", US
# NTSC only, which is not what a converted ROM should claim.
IO_SUPPORT_AT, IO_SUPPORT = 0x190, b"J" + b" " * 15
REGION_AT, REGION = 0x1F0, b"JUE" + b" " * 13
RESET_VECTOR = 0x004

# Where the TMSS stub goes: inside the existing $FF filler near the end of the ROM, so
# nothing moves and the ROM does not grow. Checked before it is written.
STUB_AT = 0x07F800
PAD_STUB_AT = 0x07F850
PAGE_STUB_AT = 0x07FA00

# Free work RAM, found by watching it stay zero through boot, menu and input.
PAGE_VAR = 0xFB00          # absolute short: $FFFB00. The page, 0 = closed, 1-6 = a page.
PREV_VAR = 0xFB01          # last frame's page buttons, so a hold is not a repeat

# move.b $80000d.l, d0  -- the page sensor read, 6 bytes at this address.
PAGE_SITE = 0x00038E
PAGE_READ = bytes.fromhex("10390080000d")
NOP = bytes.fromhex("4e71")

# Every remaining access to Pico I/O, which does not exist on a Mega Drive. Leaving them in
# means the game reads whatever the bus happens to hold, which differs between emulators and
# hardware: the same ROM then behaves differently everywhere, and that is not a port.
#
# (site, what must be there, what replaces it). Same length every time.
IO_SITES = [
    # The pad: read the Mega Drive controller instead (see pad_stub). 8 bytes becomes a
    # 6-byte jsr and a nop. The address is built from PAD_STUB_AT below, never written
    # here: a hardcoded one survived moving the stub and sent the game into the middle
    # of another one.
    (0x0003FE, "11f900800003f80b", None),
    # Write-only control: nothing reads it back, so it just goes.
    (0x000B66, "13c700800017", "4e71" * 3),
    # Sound command writes: six of them, all stores into a chip that is not there.
    (0x06D1C8, "33c000800012", "4e71" * 3),
    (0x06D22A, "33c000800012", "4e71" * 3),
    (0x06D29E, "33c000800012", "4e71" * 3),
    (0x06D2BA, "33c000800012", "4e71" * 3),
    (0x06D2E6, "33fc800000800012", "4e71" * 4),
    (0x06D2EE, "33fc088000800012", "4e71" * 4),
    # The one sound READ of $800012. A Pico answers $80 there (ADPCM control), so N is set
    # and the `bpl` below is NOT taken: moveq #-1 reproduces those flags exactly.
    (0x06D1D4, "4a3900800012", "70ff" + "4e71" * 2),
    # The FIFO count read through a1 ($800010). Zero makes the `beq` below it taken, which
    # skips the dbra loop that streams sample words into the same dead address.
    (0x06D202, "3011", "7000"),
]


def tmss_stub(reset_pc):
    """Unlock the VDP on a TMSS console, then run the game.

    A Pico has no TMSS, so a Pico game never writes 'SEGA' to $A14000 and never needed to.
    A Mega Drive that has one leaves the VDP locked until something does, which is a black
    screen and no sound: the console boots, the game runs, nothing can draw.

    The check first: $A10001's low nibble is 0 on a console without TMSS, where writing
    $A14000 would be a write into nothing.
    """
    parts = [
        # Silence the Z80 before anything else. A Pico has none, so a Pico game never
        # touches it; a Mega Drive powers one up RUNNING, with RAM full of whatever the
        # last power-on left, and it reaches the 68000 bus (the VDP ports included)
        # through its bank window. An emulator zeroes that RAM, so the Z80 executes NOPs
        # and nothing shows; real hardware executes garbage and scribbles over the
        # display. Take the bus from it and hold it in reset: there is no sound to lose,
        # the ADPCM chip it would have driven does not exist here either.
        ("move.w #$0100,($A11100).l", bytes.fromhex("33fc010000a11100")),   # bus request
        ("move.w #$0000,($A11200).l", bytes.fromhex("33fc000000a11200")),   # hold in reset
        ("move.b ($A10001).l,d0", bytes.fromhex("103900a10001")),
        ("andi.b #$0F,d0", bytes.fromhex("0200000f")),
        ("beq.b skip", None),                                      # filled in below
        ("move.l #'SEGA',($A14000).l", bytes.fromhex("23fc5345474100a14000")),
        ("jmp reset.l", bytes.fromhex("4ef9") + struct.pack(">I", reset_pc)),
    ]
    # The displacement is computed from the layout, never written by hand, and from the
    # branch's own position rather than a counted index: inserting an instruction above it
    # must not silently move where it lands.
    branch = next(i for i, (_, b) in enumerate(parts) if b is None)
    sizes = [2 if b is None else len(b) for _, b in parts]
    after_branch = sum(sizes[:branch + 1])
    skip = sum(sizes[:branch + 2])             # past the move.l it jumps over
    disp = skip - after_branch
    assert 0 < disp < 0x80, disp
    parts[branch] = ("beq.b +%d" % disp, bytes([0x67, disp]))

    code = b"".join(b for _, b in parts)
    # Every branch must land on an instruction boundary: here, exactly where the jmp starts.
    boundaries = set()
    at = 0
    for _, b in parts:
        boundaries.add(at)
        at += len(b)
    assert after_branch + disp in boundaries, "beq lands mid-instruction"
    assert len(code) == at
    return code, parts


def pad_stub():
    """Read the Mega Drive pad and leave a Pico-shaped byte where the Pico read used to land.

    The Pico's $800003 is active low: bits 0-3 up/down/left/right, bit 4 the red button,
    bit 7 the pen, bits 5-6 unused (which is why the game ors $60 over them). A Mega Drive
    pad's TH=1 read has the same four directions in the same bits, so they pass straight
    through.

        D-pad            directions
        Start            the red button
        B                pen tap
        A held + D-pad   moves the pen cursor, so the directions are withheld
        C held + L/R     turns the storybook page, so left and right are withheld

    A held and C held withhold the directions they claim, otherwise one press would both
    move the cursor and walk a menu.
    """
    P = [
        ("save", "48e7f800"),                       # movem.l d0-d4,-(a7)
        ("th out", "13fc004000a10009"),             # move.b #$40,($A10009).l
        ("th high", "13fc004000a10003"),
        ("settle1", "4e71"),
        ("settle2", "4e71"),
        ("read high", "103900a10003"),              # d0 = ..CBRLDU
        ("th low", "13fc000000a10003"),
        ("settle3", "4e71"),
        ("settle4", "4e71"),
        ("read low", "123900a10003"),               # d1 = ..SA..DU

        # Capture every button we care about before the mask below rewrites those bits.
        # d2: 0 C, 1 B, 2 A, 3 Start, 4 Left, 5 Right. Set means held (the pad is active low).
        ("clear buttons", "7400"),                  # moveq #0,d2
        ("test C", "08000005"),
        (">noC", None),
        ("hold C", "08c20000"),
        ("test B", "08000004"),                     # noC:
        (">noB", None),
        ("hold B", "08c20001"),
        ("test A", "08010004"),                     # noB:
        (">noA", None),
        ("hold A", "08c20002"),
        ("test Start", "08010005"),                 # noA:
        (">noStart", None),
        ("hold Start", "08c20003"),
        ("test Left", "08000002"),                  # noStart:
        (">noLeft", None),
        ("hold Left", "08c20004"),
        ("test Right", "08000003"),                 # noLeft:
        (">noRight", None),
        ("hold Right", "08c20005"),

        # The Pico byte: directions as they came, everything else said explicitly.
        ("mask", "000000f0"),                       # ori.b #$F0,d0   (noRight:)
        ("test red", "08020003"),                   # Start -> red
        ("=noRed", None),
        ("set red", "08800004"),                    # bclr #4,d0
        ("test tap", "08020001"),                   # B -> pen        (noRed:)
        ("=noTap", None),
        ("set tap", "08800007"),                    # bclr #7,d0
        ("test cursor", "08020002"),                # A: cursor owns the D-pad  (noTap:)
        ("=noCursor", None),
        ("drop dirs", "0000000f"),                  # ori.b #$0F,d0
        ("test pageheld", "08020000"),              # C: pages own left/right  (noCursor:)
        ("=noPageDirs", None),
        ("drop lr", "0000000c"),                    # ori.b #$0C,d0
        ("store pad", "11c0f80b"),                  # move.b d0,$F80B.w  (noPageDirs:)

        # Pages, on the press rather than the hold: a page sensor does not auto-repeat.
        ("load prev", "1638fb01"),
        ("save prev", "11c2fb01"),
        ("invert prev", "4603"),
        ("edge", "c602"),                           # d3 = newly pressed
        ("test page mode", "08020000"),             # C held?
        ("=nopage", None),
        ("load page", "1838fb00"),
        ("test fwd", "08030005"),                   # Right newly pressed
        ("=noFwd", None),
        ("page up", "5204"),
        ("wrap check", "0c040007"),
        ("<noFwd", None),                           # bcs: still in range
        ("page wrap", "7800"),
        ("test back", "08030004"),                  # Left newly pressed  (noFwd:)
        ("=noBack", None),
        ("page down", "5304"),
        ("!noBack", None),                          # bcc: no borrow
        ("page wrap back", "7806"),
        ("store page", "11c4fb00"),                 # noBack:
        ("restore", "4cdf001f"),                    # nopage: movem.l (a7)+,d0-d4
        ("return", "4e75"),
    ]
    # A branch's name starts with its condition; its target is the instruction after the
    # block it skips, found from the layout rather than written by hand.
    COND = {">": 0x66, "=": 0x67, "<": 0x65, "!": 0x64}   # bne, beq, bcs, bcc
    TARGET = {
        ">noC": "test B", ">noB": "test A", ">noA": "test Start", ">noStart": "test Left",
        ">noLeft": "test Right", ">noRight": "mask",
        "=noRed": "test tap", "=noTap": "test cursor", "=noCursor": "test pageheld",
        "=noPageDirs": "store pad", "=nopage": "restore",
        "=noFwd": "test back", "<noFwd": "test back",
        "=noBack": "store page", "!noBack": "store page",
    }
    parts = [(n, None if h is None else bytes.fromhex(h)) for n, h in P]
    names = [n for n, _ in parts]
    assert len(set(names)) == len(names), "names must be unique to resolve branches"

    for i, (name, code) in enumerate(parts):
        if code is not None:
            continue
        sizes = [2 if b is None else len(b) for _, b in parts]
        after = sum(sizes[:i + 1])
        disp = sum(sizes[:names.index(TARGET[name])]) - after
        assert 0 < disp < 0x80, (name, disp)
        parts[i] = (name, bytes([COND[name[0]], disp]))

    offsets, at = [], 0
    for _, b in parts:
        offsets.append(at)
        at += len(b)
    for i, (name, code) in enumerate(parts):
        if name[0] in COND:
            assert offsets[i] + 2 + code[1] in offsets, "%s lands mid-instruction" % name
    return b"".join(b for _, b in parts), parts


def page_stub():
    """Answer the page sensor from the byte the pad stub keeps.

    The hardware returns a mask of the low bits, `(1 << pages) - 1`, 0 when the book is
    closed. The game takes the highest set bit, so the mask and a single bit agree, but
    the mask is what a Pico actually puts on the bus and costs nothing to reproduce.
    """
    parts = [
        ("move.l d1,-(a7)", bytes.fromhex("2f01")),
        ("moveq #1,d1", bytes.fromhex("7201")),
        ("move.b $FB00.w,d0", bytes.fromhex("1038fb00")),
        ("lsl.l d0,d1", bytes.fromhex("e1a9")),           # 1 << page
        ("subq.l #1,d1", bytes.fromhex("5381")),          # (1 << page) - 1
        ("move.l d1,d0", bytes.fromhex("2001")),
        ("move.l (a7)+,d1", bytes.fromhex("221f")),
        ("rts", bytes.fromhex("4e75")),
    ]
    return b"".join(b for _, b in parts), parts


def expect(rom, at, want, what):
    got = rom[at:at + len(want)]
    if got != want:
        sys.exit("[ERROR] %s: expected %s at $%06X, found %s.\n"
                 "        This is a different build. Re-run the I/O scan "
                 "before patching it." % (what, want.hex(), at, got.hex()))


def checksum(rom):
    total = 0
    for i in range(0x200, len(rom) - 1, 2):
        total = (total + struct.unpack_from(">H", rom, i)[0]) & 0xFFFF
    return total


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: patch.py <pico rom> <output rom>")

    rom = bytearray(open(argv[1], "rb").read())
    if b"PICO" not in rom[0x100:0x110]:
        sys.exit("[ERROR] %s is not a Sega Pico ROM (no PICO at $100)." % argv[1])

    # 1. Page sensor. The read is followed by `move.w #$5,d7 / btst d7,d0 /
    #    bne / dbra d7`, which walks bit 5 down to bit 0 and leaves d7 as the
    #    page index when a bit is set. So a byte with bit N set selects page N,
    #    and `moveq #1<<N,d0` replaces the read in 2 bytes plus two nops.
    expect(rom, PAGE_SITE, PAGE_READ, "page sensor read")
    rom[PAGE_SITE:PAGE_SITE + 6] = bytes.fromhex("4eb9") + struct.pack(">I", PAGE_STUB_AT)

    # 2. Pico I/O: every access replaced, so the ROM touches no absent hardware.
    for at, want, repl in IO_SITES:
        if repl is None:                      # the pad site: jsr to wherever the stub is
            repl = ("4eb9" + "%08x" % PAD_STUB_AT) + "4e71"
        want, repl = bytes.fromhex(want), bytes.fromhex(repl)
        assert len(want) == len(repl), "%06X: %d bytes becomes %d" % (at, len(want), len(repl))
        expect(rom, at, want, "Pico I/O site $%06X" % at)
        rom[at:at + len(repl)] = repl

    # 2b. The pad stub the site above jumps to.
    pad, pad_parts = pad_stub()
    expect(rom, PAD_STUB_AT, b"\xFF" * len(pad), "free space for the pad stub")
    rom[PAD_STUB_AT:PAD_STUB_AT + len(pad)] = pad

    pages, page_parts = page_stub()
    expect(rom, PAGE_STUB_AT, b"\xFF" * len(pages), "free space for the page stub")
    rom[PAGE_STUB_AT:PAGE_STUB_AT + len(pages)] = pages

    # 3. TMSS. The stub goes in filler and the reset vector points at it, so the unlock
    #    runs before anything else and the game's own code is untouched.
    reset_pc = struct.unpack_from(">I", rom, RESET_VECTOR)[0]
    code, parts = tmss_stub(reset_pc)
    expect(rom, STUB_AT, b"\xFF" * len(code), "free space for the TMSS stub")
    rom[STUB_AT:STUB_AT + len(code)] = code
    struct.pack_into(">I", rom, RESET_VECTOR, STUB_AT)

    # 4. Header, so a Mega Drive and a flashcart menu accept it.
    rom[0x100:0x110] = CONSOLE
    rom[IO_SUPPORT_AT:IO_SUPPORT_AT + len(IO_SUPPORT)] = IO_SUPPORT
    rom[REGION_AT:REGION_AT + len(REGION)] = REGION
    struct.pack_into(">H", rom, CHECKSUM_AT, checksum(rom))

    open(argv[2], "wb").write(bytes(rom))
    print("page sensor      : answered from RAM, starts closed; C and Start turn it")
    print("boot stub        : $%06X, %d bytes, reset was $%06X (Z80 silenced, TMSS)"
          % (STUB_AT, len(code), reset_pc))
    for name, b in parts:
        print("                   %-26s %s" % (name, b.hex()))
    print("console string   : %s" % CONSOLE.decode())
    print("I/O support      : %s (joypad)" % IO_SUPPORT.decode().strip())
    print("region           : %s" % REGION.decode().strip())
    print("header checksum  : $%04X" % checksum(rom))
    print("pad stub         : $%06X, %d bytes (D-pad, Start = red, B = tap,\n"
          "                   A+D-pad = cursor, C+Left/Right = page)" % (PAD_STUB_AT, len(pad)))
    print("Pico I/O         : %d sites neutralised, no $8000xx access left" % len(IO_SITES))
    print("still missing    : pen coordinates (a pad cannot point)")
    print("wrote %s (%d bytes)" % (argv[2], len(rom)))


if __name__ == "__main__":
    main(sys.argv)
