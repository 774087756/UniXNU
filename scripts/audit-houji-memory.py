"""Compare captured FDT reservations with literal UEFI ranges, offline only."""
import argparse
import hashlib
import re
import runpy
import struct
from pathlib import Path


def overlap(a, b):
    return max(a[0], b[0]) < min(a[0]+a[1], b[0]+b[1])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('fdt', type=Path)
    p.add_argument('map', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    raw = args.fdt.read_bytes()
    nodes, _ = runpy.run_path(str(Path(__file__).with_name('inspect-houji-fdt.py')))['parse'](raw)
    def pairs(value):
        if len(value) % 16:
            raise ValueError('Expected 2 address + 2 size cells')
        return list(struct.iter_unpack('>QQ', value))
    for path in ['/', '/reserved-memory']:
        for key in ['#address-cells', '#size-cells']:
            if nodes[path][key] != struct.pack('>I', 2):
                raise ValueError('Unexpected memory cell widths')
    fixed, dynamic = [], []
    for path, props in nodes.items():
        if not path.startswith('/reserved-memory/'):
            continue
        if 'reg' in props:
            fixed.extend((path, a, s) for a, s in pairs(props['reg']) if s)
        else:
            dynamic.append(path)
    source = args.map.read_text(encoding='utf-8')
    table = source.split('gMemoryDescriptor[] = {', 1)[1].split('\n};', 1)[0]
    entries = re.findall(r'\{"([^"]+)",\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*(\w+)', table)
    lines = ['# UEFI / live FDT range comparison', '',
             'FDT SHA256: `' + hashlib.sha256(raw).hexdigest() + '`',
             'MemoryMapLib SHA256: `' + hashlib.sha256(args.map.read_bytes()).hexdigest() + '`', '',
             'Address intersections only: overlaps are not automatically bugs. Linux and UEFI use different lifecycle allocations. No overlap is not proof of safety.', '',
             '| UEFI entry | Start | Size | Intersecting fixed FDT reservations |',
             '| --- | --- | --- | --- |']
    for name, a, s, kind in entries:
        a, s = int(a,16), int(s,16)
        matches = [path.split('/')[-1] for path, b, length in fixed if overlap((a,s),(b,length))]
        if kind == 'AddMem':
            lines.append(f'| {name} | {a:#x} | {s:#x} | {", ".join(matches) or "none"} |')
    lines += ['', '## Linux memory tuples', '', '| Start | Size | End (exclusive) |', '| --- | --- | --- |']
    for a,s in pairs(nodes['/memory']['reg']):
        lines.append(f'| {a:#x} | {s:#x} | {a+s:#x} |')
    lines += ['', '## Reservations without fixed reg', '', *['- '+path for path in dynamic], '',
              'Symbolic UEFI high-RAM entry is excluded from the literal table and requires separate review of HoujiRootRAM.h. Dynamic reservation addresses cannot be inferred from size. This report does not authorize allocations or boot.']
    args.output.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(f'Compared {len(entries)} literal descriptors against {len(fixed)} nonzero fixed reservations; {len(dynamic)} reservations lack reg.')


if __name__ == '__main__':
    main()
