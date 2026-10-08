#!/usr/bin/env python3
"""Write an IPS patch from an original and a patched ROM of the same length.

The release artifact is the patch, never the ROM.

    python3 ips.py <original> <patched> <out.ips>
"""
import sys


def records(a, b):
    i, n = 0, len(a)
    while i < n:
        if a[i] == b[i]:
            i += 1
            continue
        start = i
        # Close a run only after 4 identical bytes: a shorter gap costs more as
        # two record headers (5 bytes each) than as copied data.
        same = 0
        while i < n and same < 4:
            same = same + 1 if a[i] == b[i] else 0
            i += 1
        end = i - same
        yield start, bytes(b[start:end])


def main(argv):
    if len(argv) != 4:
        sys.exit("usage: ips.py <original> <patched> <out.ips>")
    a = open(argv[1], "rb").read()
    b = open(argv[2], "rb").read()
    if len(a) != len(b):
        sys.exit("[ERROR] lengths differ (%d vs %d): this patcher is "
                 "size-neutral, so that is a bug, not a patch." % (len(a), len(b)))
    out = bytearray(b"PATCH")
    count = 0
    for offset, data in records(a, b):
        if offset > 0xFFFFFF:
            sys.exit("[ERROR] offset $%X is past the IPS 24-bit limit." % offset)
        while data:
            chunk, data = data[:0xFFFF], data[0xFFFF:]
            out += offset.to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
            offset += len(chunk)
            count += 1
    out += b"EOF"
    open(argv[3], "wb").write(bytes(out))
    print("wrote %s (%d records, %d bytes)" % (argv[3], count, len(out)))


if __name__ == "__main__":
    main(sys.argv)
