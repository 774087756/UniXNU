"""Read the live FDT through adb; never writes to or reboots the phone."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
from datetime import datetime, timezone


def validate(raw):
    if len(raw) < 40:
        raise ValueError('Output is shorter than an FDT header')
    magic, size, off_struct, off_strings, off_reserve, version, compatible, cpu, strings_size, struct_size = struct.unpack_from('>10I', raw)
    if magic != 0xd00dfeed:
        raise ValueError('Output is not a binary FDT (root denial or shell text possible)')
    if size != len(raw) or not 40 <= size <= 32 * 1024 * 1024:
        raise ValueError('FDT length mismatch or unreasonable size')
    if version < 17 or compatible > 17:
        raise ValueError('Unsupported FDT header version')
    for offset, length in ((off_struct, struct_size), (off_strings, strings_size)):
        if offset < 40 or offset + length > size:
            raise ValueError('FDT block exceeds file bounds')
    if off_reserve < 40 or off_reserve + 16 > size or off_reserve % 8:
        raise ValueError('Invalid reserve-map offset')
    return size


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    adb = str(a.adb.resolve())
    devices = subprocess.run([adb, 'devices'], capture_output=True, check=True, timeout=20).stdout.decode(errors='replace')
    entries = [line.split() for line in devices.splitlines()[1:] if line.strip()]
    if len(entries) != 1 or entries[0][1:] != ['device']:
        raise SystemExit('Connect exactly one authorized ADB device before collecting.')
    device_args = [adb, '-s', entries[0][0]]
    product = subprocess.run(device_args + ['shell', 'getprop', 'ro.product.device'], capture_output=True, check=True, timeout=20).stdout.strip()
    if product != b'houji':
        raise SystemExit('Device is not houji; stopped.')
    print('Reading live FDT. Allow the shell root request on the phone if prompted.', flush=True)
    # adb joins the remote arguments; preserve quotes for the device shell.
    result = subprocess.run(device_args + ['exec-out', "su -c 'cat /sys/firmware/fdt'"], capture_output=True, timeout=90)
    if result.returncode:
        raise SystemExit('Read failed: ' + result.stderr.decode(errors='replace')[:500])
    try:
        size = validate(result.stdout)
    except ValueError as error:
        print('Validation failed:', error)
        print('Received bytes:', len(result.stdout))
        print('First 16 bytes (hex):', result.stdout[:16].hex(' '))
        # Print only text responses, never a potentially sensitive binary tree.
        prefix = result.stdout[:300]
        if prefix and all(b in (9, 10, 13) or 32 <= b <= 126 for b in prefix):
            print('Text response:', repr(prefix.decode('ascii')))
        if result.stderr:
            print('stderr:', repr(result.stderr[:300].decode(errors='replace')))
        raise SystemExit('No DTB saved. Send this diagnostic output for review.') from None
    a.output_dir.mkdir(parents=True, exist_ok=True)
    target = a.output_dir / ('houji-live-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.dtb')
    with target.open('xb') as f:
        f.write(result.stdout)
    print('Saved:', target.resolve())
    print('Bytes:', size)
    print('SHA256:', hashlib.sha256(result.stdout).hexdigest())
    print('Header/bounds checked only; hardware compatibility is not yet validated.')


if __name__ == '__main__':
    main()
