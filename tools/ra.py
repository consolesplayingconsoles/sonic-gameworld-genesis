#!/usr/bin/env python3
"""Drive this port in RetroArch (Genesis Plus GX) without touching the Mac: RetroArch's
network commands over UDP 55355 (memory, pause, frame step, screenshot) and its network
gamepad on 55400 (player 1). Stdlib only.

    ra.py launch [rom]      start RetroArch with the Genesis core and the built ROM
    ra.py status            RetroArch's state (playing/paused, content)
    ra.py read ADDR [N]     N bytes (default 4) at a 68000 address, e.g. FFF80A
    ra.py word ADDR         one big-endian 16-bit value
    ra.py long ADDR         one big-endian 32-bit value
    ra.py write ADDR HEX    e.g. ra.py write FFF80A 0000
    ra.py watch ADDR [N] [SECONDS]
                            read the same bytes repeatedly: says whether the game is alive
    ra.py pause / step [N] / shot
    ra.py press BUTTON [FRAMES] / hold BUTTON / release BUTTON|all
                            A B C START UP DOWN LEFT RIGHT

Sibling of the Crazy Taxi sandbox's tools/ra.py, which came first and talks to Flycast.
Same protocol, different core and address space; worth lifting into one shared tool the
moment a third project needs it.

RetroArch needs network_cmd_enable, network_remote_enable and network_remote_enable_user_p1
set in retroarch.cfg.
"""
import glob
import os
import socket
import struct
import subprocess
import sys
import time

HOST = '127.0.0.1'
CMD_PORT = 55355
PAD_PORT = 55400                                  # network_remote_base_port + user 0
RA = '/Applications/RetroArch.app'
CORE = os.path.expanduser('~/Library/Application Support/RetroArch/cores/'
                          'genesis_plus_gx_libretro.dylib')
SHOTS = os.path.expanduser('~/Documents/RetroArch/screenshots')
HERE = os.path.dirname(os.path.abspath(__file__))
ROM_DIR = os.path.join(HERE, '..', 'rom')
WORK_RAM = 0xFF0000                               # 68000 work RAM, 64 KB

# RetroPad ids as Genesis Plus GX maps them: RetroPad Y->A, B->B, A->C, measured by
# holding each one and reading the byte the game stores its pad in.
PAD = {'A': 1, 'B': 0, 'C': 8, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7,
       'X': 9, 'Y': 10, 'Z': 11, 'MODE': 2}
JOYPAD, ANALOG = 1, 5


def cmd(text, reply=True, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(text.encode(), (HOST, CMD_PORT))
        return s.recv(65536).decode().strip() if reply else None
    except (socket.timeout, ConnectionRefusedError):
        return None
    finally:
        s.close()


def read(addr, n):
    """Bytes at a 68000 address: the core's memory map first, then work RAM by offset."""
    for _ in range(3):                            # a busy machine drops or delays answers
        for name, a in (('READ_CORE_MEMORY', addr), ('READ_CORE_RAM', addr - WORK_RAM)):
            r = cmd('%s %x %d' % (name, a, n))
            if r and r.split()[2:3] != ['-1']:
                return bytes(int(b, 16) for b in r.split()[2:])
    sys.exit('read failed at %06X (is RetroArch running with the ROM?)' % addr)


def write(addr, data):
    hexes = ' '.join('%02x' % b for b in data)
    r = cmd('WRITE_CORE_MEMORY %x %s' % (addr, hexes))
    if r is None or r.split()[2:3] == ['-1']:
        cmd('WRITE_CORE_RAM %x %s' % (addr - WORK_RAM, hexes), reply=False)


def pad(device, index, ident, state):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(struct.pack('<iiiiHxx', 0, device, index, ident, state & 0xFFFF), (HOST, PAD_PORT))
    s.close()


def button(name, down):
    pad(JOYPAD, 0, PAD[name.upper()], 1 if down else 0)


def launch(rom=None):
    if rom is None:
        found = sorted(glob.glob(os.path.join(glob.escape(ROM_DIR), '*.bin')))
        if not found:
            sys.exit('no ROM in %s: build it from Pluto first' % ROM_DIR)
        rom = found[0]
    subprocess.check_call(['open', '-g', '-n', '-a', RA, '--args', '-L', CORE, rom])
    for _ in range(60):
        time.sleep(1)
        r = cmd('GET_STATUS')
        if r and 'CONTENTLESS' not in r:
            print(r)
            return
    print('RetroArch started, no answer on port %d yet' % CMD_PORT)


def shot():
    before = set(glob.glob(os.path.join(SHOTS, '*.png')))
    cmd('SCREENSHOT', reply=False)
    for _ in range(50):
        time.sleep(0.1)
        new = set(glob.glob(os.path.join(SHOTS, '*.png'))) - before
        if new:
            path, size = max(new, key=os.path.getmtime), -1
            for _ in range(50):                   # written in pieces: wait until it settles
                time.sleep(0.2)
                now = os.path.getsize(path)
                if now and now == size:
                    return path
                size = now
            return path
    sys.exit('no screenshot appeared in %s' % SHOTS)


def watch(addr, n, seconds):
    """Is anything running? The same bytes, sampled: a frozen 68000 never changes them."""
    seen, first = {}, None
    end = time.time() + seconds
    while time.time() < end:
        got = read(addr, n).hex()
        first = first if first is not None else got
        seen[got] = seen.get(got, 0) + 1
        time.sleep(0.2)
    print('%06X+%d over %gs: %d distinct values' % (addr, n, seconds, len(seen)))
    for value, count in sorted(seen.items(), key=lambda kv: -kv[1])[:6]:
        print('   %s  x%d' % (value, count))
    print('verdict: %s' % ('something is writing it' if len(seen) > 1 else 'unchanged'))


def main(a):
    if not a:
        sys.exit(__doc__)
    c = a[0]
    if c == 'launch':
        launch(a[1] if len(a) > 1 else None)
    elif c == 'status':
        print(cmd('GET_STATUS'))
    elif c == 'read':
        print(read(int(a[1], 16), int(a[2]) if len(a) > 2 else 4).hex())
    elif c == 'word':
        print('%04X' % struct.unpack('>H', read(int(a[1], 16), 2))[0])
    elif c == 'long':
        print('%08X' % struct.unpack('>I', read(int(a[1], 16), 4))[0])
    elif c == 'write':
        write(int(a[1], 16), bytes.fromhex(a[2]))
    elif c == 'watch':
        watch(int(a[1], 16), int(a[2]) if len(a) > 2 else 4, float(a[3]) if len(a) > 3 else 3)
    elif c == 'pause':
        cmd('PAUSE_TOGGLE', reply=False)
    elif c == 'step':
        for _ in range(int(a[1]) if len(a) > 1 else 1):
            cmd('FRAMEADVANCE', reply=False)
            time.sleep(0.02)
    elif c == 'shot':
        print(shot())
    elif c == 'press':
        button(a[1], True)
        time.sleep((int(a[2]) if len(a) > 2 else 6) / 60.0)
        button(a[1], False)
    elif c == 'hold':
        button(a[1], True)
    elif c == 'release':
        for name in (PAD if a[1].lower() == 'all' else [a[1]]):
            button(name, False)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
