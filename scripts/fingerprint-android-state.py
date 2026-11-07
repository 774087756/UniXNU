"""Read-only fingerprint of the partitions a boot must never change.

Run once before a test boot and once after, then compare the two JSON files.
Nothing is written to the device: every read goes through
`adb exec-out su -c 'cat <node>'` and is hashed on the host.

Limitation: the GPT is represented by its partition listing, not a hash of the
header sectors, so a change that preserved every size and offset would not show.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

TARGETS = ['misc', 'boot_a', 'vbmeta_a', 'dtbo_a', 'init_boot_a']
BY_NAME = '/dev/block/by-name'


def adb_path(explicit):
    if explicit:
        return str(explicit)
    found = shutil.which('adb')
    if found:
        return found
    local = Path(__file__).resolve().parents[1] / '..' / '..' / 'tools' / 'platform-tools' / 'adb.exe'
    if local.exists():
        return str(local)
    raise SystemExit('adb not found; pass --adb')


def run(adb, serial, args):
    cmd = [adb] + (['-s', serial] if serial else []) + args
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise SystemExit('adb failed (%s): %s' % (' '.join(args),
                                                  result.stderr.decode('utf-8', 'replace').strip()))
    return result.stdout


def device_present(adb):
    out = run(adb, None, ['devices']).decode('utf-8', 'replace')
    serials = [line.split('\t')[0] for line in out.splitlines()[1:] if '\tdevice' in line]
    if not serials:
        raise SystemExit('no adb device in the "device" state')
    if len(serials) > 1:
        raise SystemExit('more than one device attached (%s); pass --serial' % ', '.join(serials))
    return serials[0]


def hash_node(adb, serial, node, limit=None):
    """Hash a block node by streaming it through adb; never writes on device."""
    # The whole `su -c '...'` string must reach the device shell as one argument,
    # otherwise su receives only "cat" as its command.
    remote = "su -c 'cat %s'" % node
    if limit:
        remote = "su -c 'dd if=%s bs=1048576 count=%d'" % (node, limit)
    cmd = [adb] + (['-s', serial] if serial else []) + ['exec-out', remote]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = proc.stdout.read(1 << 20)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    err = proc.stderr.read().decode('utf-8', 'replace').strip()
    if proc.wait() != 0 or total == 0:
        return {'node': node, 'error': err or 'empty read', 'bytes': total}
    return {'node': node, 'sha256': digest.hexdigest(), 'bytes': total}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path,
                        help='compare this earlier fingerprint against --output instead of reading the device')
    parser.add_argument('--label', default='')
    parser.add_argument('--serial')
    parser.add_argument('--adb', type=Path)
    parser.add_argument('--limit-mb', type=int, default=0,
                        help='read at most this many MiB per node (0 = whole node)')
    args = parser.parse_args()

    if args.compare:
        if not args.output:
            raise SystemExit('--compare needs --output pointing at the later fingerprint')
        problems = compare(args.compare, args.output)
        if problems:
            print('CHANGED: %s' % ', '.join(problems))
            raise SystemExit(1)
        print('UNCHANGED: every recorded object matches')
        return

    if not args.output:
        raise SystemExit('--output is required when reading the device')

    adb = adb_path(args.adb)
    serial = args.serial or device_present(adb)

    listing = run(adb, serial, ['exec-out', 'su -c \'ls -l %s\'' % BY_NAME])
    partitions = run(adb, serial, ['exec-out', 'cat /proc/partitions'])

    report = {
        'label': args.label,
        'serial_present': True,
        'by_name_listing_sha256': hashlib.sha256(listing).hexdigest(),
        'proc_partitions_sha256': hashlib.sha256(partitions).hexdigest(),
        'nodes': {},
    }
    for name in TARGETS:
        node = '%s/%s' % (BY_NAME, name)
        report['nodes'][name] = hash_node(adb, serial, node, args.limit_mb or None)

    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Wrote %s; read-only, nothing written to the device.' % args.output)


def compare(before_path, after_path):
    before = json.loads(Path(before_path).read_text(encoding='utf-8'))
    after = json.loads(Path(after_path).read_text(encoding='utf-8'))
    problems = []
    for key in ('by_name_listing_sha256', 'proc_partitions_sha256'):
        if before[key] != after[key]:
            problems.append(key)
    for name, entry in before['nodes'].items():
        other = after['nodes'].get(name, {})
        if entry.get('sha256') != other.get('sha256'):
            problems.append(name)
    return problems


if __name__ == '__main__':
    main()
