#!/usr/bin/env python3
"""Patch Sonic the Hedgehog's Gameworld (Sega Pico) to run on a Mega Drive.

Applies only substitutions justified by decoded code, listed in FINDINGS.md.
Every patch is size-neutral: this is a linked binary with no relocation
information, so moving a byte breaks every branch over it.

    python3 patch.py <pico rom> <output rom> [--page N]
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
PAD_STUB_AT = 0x07F820

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
    # 6-byte jsr and a nop.
    (0x0003FE, "11f900800003f80b", "4eb90007f820" + "4e71"),
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
        ("move.b ($A10001).l,d0", bytes.fromhex("103900a10001")),
        ("andi.b #$0F,d0", bytes.fromhex("0200000f")),
        ("beq.b skip", None),                                      # filled in below
        ("move.l #'SEGA',($A14000).l", bytes.fromhex("23fc5345474100a14000")),
        ("jmp reset.l", bytes.fromhex("4ef9") + struct.pack(">I", reset_pc)),
    ]
    # The displacement is computed from the layout, never written by hand: it is measured
    # from the END of the 2-byte branch to the first byte after the move.l it skips.
    sizes = [2 if b is None else len(b) for _, b in parts]
    after_branch = sum(sizes[:3])
    skip = sum(sizes[:4])
    disp = skip - after_branch
    assert 0 < disp < 0x80, disp
    parts[2] = ("beq.b +%d" % disp, bytes([0x67, disp]))

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
    """Read the Mega Drive pad and leave it where the game expects the Pico's byte.

    The Pico's $800003 is active low with bits 0-3 up/down/left/right, bit 4 the red
    button and bit 7 the pen, which is why the game ors $60 over the two unused bits
    before inverting. A Mega Drive pad's TH=1 read is active low with bits 0-3 in the
    SAME order and bit 4 the B button, so four directions and the red button need no
    rearranging at all: force the unused bits high and the byte is already Pico-shaped.

    The pen is the one thing a pad has no equivalent for, so Start stands in for it.
    """
    parts = [
        ("move.b #$40,($A10009).l", bytes.fromhex("13fc004000a10009")),  # TH is an output
        ("move.b #$40,($A10003).l", bytes.fromhex("13fc004000a10003")),  # TH high
        ("nop", bytes.fromhex("4e71")),
        ("nop", bytes.fromhex("4e71")),
        ("move.b ($A10003).l,d0", bytes.fromhex("103900a10003")),        # ..CBRLDU
        ("move.b #$00,($A10003).l", bytes.fromhex("13fc000000a10003")),  # TH low
        ("nop", bytes.fromhex("4e71")),
        ("nop", bytes.fromhex("4e71")),
        ("move.b ($A10003).l,d1", bytes.fromhex("123900a10003")),        # ..SA..DU
        ("ori.b #$E0,d0", bytes.fromhex("000000e0")),                    # unused + pen high
        ("btst #5,d1", bytes.fromhex("08010005")),                       # Start held?
        ("bne.b nopen", None),
        ("bclr #7,d0", bytes.fromhex("08800007")),                       # yes: pen down
        ("move.b d0,$F80B.w", bytes.fromhex("11c0f80b")),
        ("rts", bytes.fromhex("4e75")),
    ]
    sizes = [2 if b is None else len(b) for _, b in parts]
    branch = parts.index(("bne.b nopen", None))
    after_branch = sum(sizes[:branch + 1])
    target = sum(sizes[:branch + 2])          # past the bclr
    disp = target - after_branch
    assert 0 < disp < 0x80, disp
    parts[branch] = ("bne.b +%d" % disp, bytes([0x66, disp]))

    boundaries, at = set(), 0
    for _, b in parts:
        boundaries.add(at)
        at += len(b)
    assert after_branch + disp in boundaries, "bne lands mid-instruction"
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
        sys.exit("usage: patch.py <pico rom> <output rom> [--page N]")
    page = 0
    if "--page" in argv:
        page = int(argv[argv.index("--page") + 1])
    if not 0 <= page <= 5:
        sys.exit("[ERROR] --page must be 0 to 5: the sensor has six positions.")

    rom = bytearray(open(argv[1], "rb").read())
    if b"PICO" not in rom[0x100:0x110]:
        sys.exit("[ERROR] %s is not a Sega Pico ROM (no PICO at $100)." % argv[1])

    # 1. Page sensor. The read is followed by `move.w #$5,d7 / btst d7,d0 /
    #    bne / dbra d7`, which walks bit 5 down to bit 0 and leaves d7 as the
    #    page index when a bit is set. So a byte with bit N set selects page N,
    #    and `moveq #1<<N,d0` replaces the read in 2 bytes plus two nops.
    expect(rom, PAGE_SITE, PAGE_READ, "page sensor read")
    rom[PAGE_SITE:PAGE_SITE + 6] = bytes([0x70, 1 << page]) + NOP + NOP

    # 2. Pico I/O: every access replaced, so the ROM touches no absent hardware.
    for at, want, repl in IO_SITES:
        want, repl = bytes.fromhex(want), bytes.fromhex(repl)
        assert len(want) == len(repl), "%06X: %d bytes becomes %d" % (at, len(want), len(repl))
        expect(rom, at, want, "Pico I/O site $%06X" % at)
        rom[at:at + len(repl)] = repl

    # 2b. The pad stub the site above jumps to.
    pad, pad_parts = pad_stub()
    expect(rom, PAD_STUB_AT, b"\xFF" * len(pad), "free space for the pad stub")
    rom[PAD_STUB_AT:PAD_STUB_AT + len(pad)] = pad

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
    print("page sensor      : fixed at page %d (bit %d)" % (page, page))
    print("TMSS unlock      : $%06X, %d bytes, reset was $%06X" % (STUB_AT, len(code), reset_pc))
    for name, b in parts:
        print("                   %-26s %s" % (name, b.hex()))
    print("console string   : %s" % CONSOLE.decode())
    print("I/O support      : %s (joypad)" % IO_SUPPORT.decode().strip())
    print("region           : %s" % REGION.decode().strip())
    print("header checksum  : $%04X" % checksum(rom))
    print("pad stub         : $%06X, %d bytes (D-pad, B = red, Start = pen)"
          % (PAD_STUB_AT, len(pad)))
    print("Pico I/O         : %d sites neutralised, no $8000xx access left" % len(IO_SITES))
    print("still missing    : pen coordinates (a pad cannot point)")
    print("wrote %s (%d bytes)" % (argv[2], len(rom)))


if __name__ == "__main__":
    main(sys.argv)
