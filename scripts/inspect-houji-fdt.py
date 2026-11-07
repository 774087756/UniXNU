"""Offline FDT inspection; prints only selected hardware properties."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from importlib.machinery import SourceFileLoader


def parse(raw):
    validator = SourceFileLoader('collector', str(Path(__file__).with_name('collect-houji-fdt.py'))).load_module()
    validator.validate(raw)
    _, _, start, strings, reserve, _, _, _, slen, length = struct.unpack_from('>10I', raw)
    names = raw[strings:strings+slen]
    pos, end, stack, nodes = start, start+length, [], {}
    while pos < end:
        if pos+4 > end:
            raise ValueError('Truncated token')
        token = struct.unpack_from('>I', raw, pos)[0]
        pos += 4
        if token == 1:
            stop = raw.index(b'\0', pos, end)
            stack.append(raw[pos:stop].decode('ascii'))
            pos = (stop+4) & ~3
            path = '/'.join(stack) or '/'
            if path in nodes:
                raise ValueError('Duplicate node')
            nodes[path] = {}
        elif token == 2:
            if not stack:
                raise ValueError('Unbalanced node')
            stack.pop()
        elif token == 3:
            if not stack or pos+8 > end:
                raise ValueError('Invalid property')
            size, offset = struct.unpack_from('>II', raw, pos)
            pos += 8
            if pos+size > end or offset >= len(names):
                raise ValueError('Property out of bounds')
            name = names[offset:names.index(b'\0', offset)].decode('ascii')
            nodes['/'.join(stack) or '/'][name] = raw[pos:pos+size]
            pos = (pos+size+3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            if stack:
                raise ValueError('Unclosed nodes')
            reservations = []
            while reserve+16 <= len(raw):
                address, size = struct.unpack_from('>QQ', raw, reserve)
                reserve += 16
                if address == size == 0:
                    return nodes, reservations
                reservations.append([hex(address), hex(size)])
            raise ValueError('Unterminated reservations')
        else:
            raise ValueError('Unknown FDT token')
    raise ValueError('Missing END token')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    raw = args.file.read_bytes()
    nodes, reservations = parse(raw)
    selected = {}
    keys = {'compatible', 'device_type', 'reg', 'ranges', '#address-cells', '#size-cells', 'method', 'enable-method', 'redistributor-stride', '#redistributor-regions', 'status', 'no-map', 'reusable', 'size', 'alignment', 'alloc-ranges', 'interrupts', 'interrupt-parent', '#interrupt-cells'}
    for path, props in nodes.items():
        compatible = props.get('compatible', b'')
        if not (path == '/' or path.startswith(('/cpus/', '/memory', '/reserved-memory', '/psci')) or b'arm,gic-v3' in compatible or b'arm,psci' in compatible or b'arm,armv8-timer' in compatible):
            continue
        selected[path] = {key: (value.rstrip(b'\0').decode('ascii') if key in {'compatible', 'device_type', 'method', 'enable-method', 'status'} else value.hex(' ')) for key, value in props.items() if key in keys}
    print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'nodes': len(nodes), 'reserve_map': reservations, 'hardware': selected}, indent=2))


if __name__ == '__main__':
    main()
