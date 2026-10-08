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

# move.b $80000d.l, d0  -- the page sensor read, 6 bytes at this address.
PAGE_SITE = 0x00038E
PAGE_READ = bytes.fromhex("10390080000d")
NOP = bytes.fromhex("4e71")


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

    # 2. Header, so a Mega Drive and a flashcart menu accept it.
    rom[0x100:0x110] = CONSOLE
    struct.pack_into(">H", rom, CHECKSUM_AT, checksum(rom))

    open(argv[2], "wb").write(bytes(rom))
    print("page sensor      : fixed at page %d (bit %d)" % (page, page))
    print("console string   : %s" % CONSOLE.decode())
    print("header checksum  : $%04X" % checksum(rom))
    print("NOT patched yet  : input ($800003), sound ($800012)")
    print("wrote %s (%d bytes)" % (argv[2], len(rom)))


if __name__ == "__main__":
    main(sys.argv)
