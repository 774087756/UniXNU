"""Build a minimal houji ADT from the live FDT. Output is NOT bootable.

The device tree is built by whitelist, not by converting the Linux tree: the
platform expert publishes a nub for every /arm-io child and the live /soc has
545 of them. Only the nodes the current drivers actually read are emitted.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
import runpy

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_END = 1, 2, 3, 9

# Apple's platform path matches the tree by this root node name.
ROOT_NAME = 'device-tree'
NVRAM_BANK_SIZE = 8192


def load_fdt(path):
    """Parse a live FDT with the existing read-only parser."""
    parse = runpy.run_path(str(Path(__file__).with_name('inspect-houji-fdt.py')))['parse']
    raw = path.read_bytes()
    nodes, _ = parse(raw)
    return raw, nodes


def extract(nodes):
    """Pull the values the drivers read, refusing anything ambiguous."""
    soc = nodes['/soc']
    if (soc['#address-cells'], soc['#size-cells']) != (struct.pack('>I', 1),) * 2:
        raise ValueError('Unexpected /soc cell widths')
    if nodes['/']['#address-cells'] != struct.pack('>I', 2):
        raise ValueError('Unexpected root address width')
    # ranges entry is child(1) + parent(2) + length(1) cells because the root
    # declares two address cells; parsing it as three cells misaligns the data.
    child, parent, span = struct.unpack('>IQI', soc['ranges'])

    gics = [(p, v) for p, v in nodes.items()
            if b'arm,gic-v3' in v.get('compatible', b'').split(b'\0')]
    if len(gics) != 1:
        raise ValueError('Expected exactly one GICv3 node')
    gic_path, gic = gics[0]
    regions = struct.unpack('>4I', gic['reg'])
    stride, = struct.unpack('>Q', gic['redistributor-stride'])
    if stride not in (0x20000, 0x30000, 0x40000):
        raise ValueError('Unsupported redistributor stride')
    if regions[1] < 0x10000 or regions[3] < 0x20000:
        raise ValueError('GIC region below driver minimum')
    for base, size in zip(regions[::2], regions[1::2]):
        if base < child or base - child + size > span:
            raise ValueError('GIC region outside the bus window')

    method = nodes['/soc/psci']['method']
    if method not in (b'smc\0', b'hvc\0'):
        raise ValueError('Unknown PSCI conduit')

    cpus = []
    for path, props in nodes.items():
        if not path.startswith('/cpus/') or props.get('device_type') != b'cpu\0':
            continue
        affinity, = struct.unpack('>Q', props['reg'])
        if affinity > 0xFFFFFFFF:
            raise ValueError('CPU affinity does not fit the driver ABI')
        cpus.append((path, affinity))
    cpus.sort(key=lambda c: c[1])
    if not cpus:
        raise ValueError('No CPU nodes found')
    # Affinity drives both the XNU cluster id (AFF1) and the PSCI target.
    for _, affinity in cpus:
        if (affinity >> 8) & 0xFF > 7:
            raise ValueError('AFF1 beyond the audited range')

    return {
        'ranges': struct.pack('<3Q', child, parent, span),
        'gic_regions': regions,
        'gic_compatible': b'arm,gic-v3\0',
        'gic_stride': struct.pack('<Q', stride),
        'psci_method': method,
        'cpus': cpus,
        'soc_ranges_cells': (child, parent, span),
    }


def blank_chrp_bank(size=NVRAM_BANK_SIZE):
    """Build the empty v1 CHRP bank: nvram header, common, free partitions."""
    bank = bytearray(size)

    def header(offset, name, blocks):
        sig = 0x7F
        raw = bytearray(16)
        raw[0] = sig
        raw[2:4] = struct.pack('<H', blocks)
        raw[4:16] = name.encode('ascii').ljust(12, b'\0')
        total = sig + sum(raw[2:])
        while total > 255:
            total = (total & 0xFF) + (total >> 8)
        raw[1] = total
        bank[offset:offset + 16] = raw

    header(0, 'nvram', 2)             # 32 bytes
    header(32, 'common', 129)         # 16 + 2048 = 2064 bytes
    header(2096, 'free', 381)         # 16 + 6080 = 6096 bytes
    struct.pack_into('<I', bank, 20, 1)  # generation
    struct.pack_into('<I', bank, 16, zlib.adler32(bytes(bank[20:])))
    return bytes(bank)


class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name):
        self.name = name
        self.props = {}
        self.children = []

    def add(self, child):
        self.children.append(child)
        return child


def build_tree(ext, cpu_count):
    root = Node(ROOT_NAME)

    chosen = root.add(Node('chosen'))
    chosen.props[b'nvram-bank-size'] = struct.pack('<I', NVRAM_BANK_SIZE)
    chosen.props[b'nvram-proxy-data'] = blank_chrp_bank()

    # Only the boot candidate is emitted by default: the topology parser derives
    # one cluster per distinct AFF1, and the current patch allows a single
    # cluster, so eight nodes would trip its assert before any driver runs.
    cpus = root.add(Node('cpus'))
    cpus.props[b'#address-cells'] = struct.pack('>I', 1)
    cpus.props[b'#size-cells'] = struct.pack('>I', 0)
    for index in range(cpu_count):
        path, affinity = ext['cpus'][index]
        cpu = cpus.add(Node('cpu@%x' % affinity))
        cpu.props[b'device_type'] = b'cpu\0'
        cpu.props[b'reg'] = struct.pack('<I', affinity)
        # state is mandatory on every CPU node; the parser panics without it.
        cpu.props[b'state'] = b'running\0' if index == 0 else b'disabled\0'

    arm_io = root.add(Node('arm-io'))
    arm_io.props[b'ranges'] = ext['ranges']
    intc = arm_io.add(Node('intc'))
    intc.props[b'reg'] = struct.pack('<4Q', *ext['gic_regions'])
    intc.props[b'compatible'] = ext['gic_compatible']
    intc.props[b'redistributor-stride'] = ext['gic_stride']

    # Apple-only nodes: the platform expert requires both to exist, the Linux
    # tree has neither. They carry no properties yet.
    root.add(Node('defaults'))
    root.add(Node('options'))

    psci = root.add(Node('psci'))
    psci.props[b'method'] = ext['psci_method']

    return root


def serialize(root):
    strings = bytearray()
    offsets = {}

    def name_offset(name):
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(name + b'\0')
        return offsets[name]

    body = bytearray()

    def emit(node):
        body.extend(struct.pack('>I', FDT_BEGIN_NODE))
        body.extend(node.name.encode('ascii') + b'\0')
        while len(body) % 4:
            body.append(0)
        for key in sorted(node.props):
            value = node.props[key]
            body.extend(struct.pack('>III', FDT_PROP, len(value), name_offset(key)))
            body.extend(value)
            while len(body) % 4:
                body.append(0)
        for child in node.children:
            emit(child)
        body.extend(struct.pack('>I', FDT_END_NODE))

    emit(root)
    body.extend(struct.pack('>I', FDT_END))

    header_len = 40
    rsvmap = bytes(16)
    off_struct = header_len + len(rsvmap)
    off_strings = off_struct + len(body)
    total = off_strings + len(strings)
    header = struct.pack('>10I', FDT_MAGIC, total, off_struct, off_strings,
                         header_len, 17, 16, 0, len(strings), len(body))
    return header + rsvmap + body + strings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fdt', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cpus', type=int, default=1,
                        help='CPU nodes to emit (default 1; >1 is not bootable today)')
    args = parser.parse_args()

    raw, nodes = load_fdt(args.fdt)
    ext = extract(nodes)
    if not 1 <= args.cpus <= len(ext['cpus']):
        raise SystemExit('--cpus must be between 1 and %d' % len(ext['cpus']))

    blob = serialize(build_tree(ext, args.cpus))
    args.output.write_bytes(blob)

    manifest = {
        'status': 'OFFLINE_ADT_NOT_BOOTABLE',
        'source_fdt_sha256': hashlib.sha256(raw).hexdigest(),
        'adt_sha256': hashlib.sha256(blob).hexdigest(),
        'adt_bytes': len(blob),
        'root_name': ROOT_NAME,
        'cpu_nodes': args.cpus,
        'cpu_affinities': [hex(a) for _, a in ext['cpus'][:args.cpus]],
        'soc_ranges_cells': [hex(v) for v in ext['soc_ranges_cells']],
        'gic_regions': [hex(v) for v in ext['gic_regions']],
        'gic_stride': hex(struct.unpack('<Q', ext['gic_stride'])[0]),
        'psci_method': ext['psci_method'].rstrip(b'\0').decode(),
        'nvram_bank_bytes': NVRAM_BANK_SIZE,
        'decisions': {
            'fd_base': '0xA7100000 kept; the only address with two independent documentary sources',
            'ramoops_overlap': 'accepted; loading the firmware volume overwrites the persistent kernel log',
            'boot_cpu': 'cpu@0 (affinity 0x0) is an unverified candidate until P3 reads MPIDR_EL1',
        },
        'blockers': [
            'Boot MPIDR unverified; topology assumes affinity 0x0 is the running core',
            'Multi-CPU trees need MAX_CPU_CLUSTERS raised; AFF1 0..7 spans eight clusters',
            'Runtime EFI memory map, GOP geometry and CurrentEL not collected',
            'dram-base/dram-size consumer chain still unresolved',
        ],
    }
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Wrote %s (%d bytes, %d CPU node(s)); not bootable.' % (args.output, len(blob), args.cpus))


if __name__ == '__main__':
    main()
