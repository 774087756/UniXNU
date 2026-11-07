"""Build a minimal houji ADT from the live FDT. Output is NOT bootable.

The tree is built by whitelist, not by converting the Linux tree: the platform
expert publishes a nub for every /arm-io child and the live /soc has 545 of
them. Only the nodes the current drivers read are emitted.

The container is Apple's ADT, not FDT. DarwinBoot parses the ADT itself before
handoff and rejects anything that does not walk to exactly the file length.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
NVRAM_BANK_SIZE = 8192
WINDOW_MIB = 256


def load_fdt(path):
    parse = runpy.run_path(str(HERE / 'inspect-houji-fdt.py'))['parse']
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
    # ranges is child(1) + parent(2) + length(1) cells: the root declares two
    # address cells, so reading three cells misaligns every later field.
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
    for _, affinity in cpus:
        if (affinity >> 8) & 0xFF > 7:
            raise ValueError('AFF1 beyond the audited range')

    return {
        'ranges': struct.pack('<3Q', child, parent, span),
        'gic_regions': regions,
        'gic_stride': struct.pack('<Q', stride),
        'psci_method': method,
        'cpus': cpus,
        'soc_ranges_cells': (child, parent, span),
    }


def nvram_proxy(size=NVRAM_BANK_SIZE):
    """The empty volatile CHRP bank, byte for byte as the proven fixture."""
    def header(name, length):
        raw = bytearray(struct.pack('<BBH12s', 0x70, 0, length // 16, name))
        checksum = sum(raw)
        while checksum > 255:
            checksum = (checksum & 255) + (checksum >> 8)
        raw[1] = checksum
        return raw

    image = bytearray(size)
    image[:16] = header(b'nvram', 32)
    image[32:48] = header(b'common', 2064)
    image[2096:2112] = header(b'free', len(image) - 2096)
    struct.pack_into('<I', image, 16, zlib.adler32(bytes(image[20:])))
    return {
        'nvram-bank-size': struct.pack('<I', len(image)),
        'nvram-bank-count': struct.pack('<I', 1),
        'nvram-current-bank': bytes(4),
        'nvram-proxy-data': bytes(image),
    }


def build_tree(ext, cpu_count, window_mib=WINDOW_MIB):
    Node = runpy.run_path(str(HERE / 'houji-adt-format.py'))['Node']

    root = Node('device-tree', [
        ('compatible', b'xiaomi,houji\0qcom,sm8650\0AppleARM\0'),
        ('model', b'Xiaomi 14\0'),
        ('manufacturer', b'Xiaomi\0'),
        ('target-type', b'houji\0'),
    ])

    chosen = root.add(Node('chosen', [
        # Both stay zero: DarwinBoot fills the real window through BootArgs and
        # no consumer of these two has been located in the pinned sources.
        ('dram-base', bytes(8)),
        ('dram-size', bytes(8)),
        ('darwinboot-memory-size', struct.pack('<Q', window_mib * 1024 * 1024)),
        ('firmware-version', b'houji-xnu-12377-uefi\0'),
    ] + list(nvram_proxy().items())))

    cpus = root.add(Node('cpus'))
    # One CPU only: the topology parser derives a cluster per distinct AFF1 and
    # the patch allows a single cluster, so eight nodes trip its assert before
    # any driver runs.
    for index in range(cpu_count):
        _, affinity = ext['cpus'][index]
        cpus.add(Node('cpu%d' % index, [
            ('device_type', b'cpu\0'),
            ('reg', struct.pack('<I', affinity)),
            ('compatible', b'qcom,kryo\0ARM,v8\0'),
            # Mandatory on every CPU node; the parser panics without it.
            ('state', b'running\0' if index == 0 else b'waiting\0'),
        ]))

    arm_io = root.add(Node('arm-io', [('ranges', ext['ranges'])]))
    arm_io.add(Node('intc', [
        ('reg', struct.pack('<4Q', *ext['gic_regions'])),
        ('compatible', b'arm,gic-v3\0'),
        ('redistributor-stride', ext['gic_stride']),
    ]))

    # Apple-only nodes. The platform expert requires defaults and options to
    # exist; aliases is carried over from the proven houji tree.
    root.add(Node('defaults'))
    root.add(Node('options'))
    root.add(Node('aliases'))

    root.add(Node('psci', [('method', ext['psci_method'])]))
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fdt', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cpus', type=int, default=1,
                        help='CPU nodes to emit (default 1; more is not bootable today)')
    parser.add_argument('--window-mib', type=int, default=WINDOW_MIB,
                        help='darwinboot-memory-size, 256..8192 and 2 MiB aligned')
    args = parser.parse_args()

    if not (256 <= args.window_mib <= 8192) or args.window_mib % 2:
        raise SystemExit('--window-mib must be 256..8192 and a multiple of 2')

    format_module = runpy.run_path(str(HERE / 'houji-adt-format.py'))
    raw, nodes = load_fdt(args.fdt)
    ext = extract(nodes)
    if not 1 <= args.cpus <= len(ext['cpus']):
        raise SystemExit('--cpus must be between 1 and %d' % len(ext['cpus']))

    blob = format_module['serialize'](build_tree(ext, args.cpus, args.window_mib))

    parsed, used = format_module['parse'](blob)
    if used != len(blob):
        raise SystemExit('ADT did not round-trip: consumed %d of %d bytes' % (used, len(blob)))
    if parsed.get('device-tree', {}).get('name') != b'device-tree\0':
        raise SystemExit('root node name is wrong after round-trip')

    args.output.write_bytes(blob)
    manifest = {
        'status': 'OFFLINE_ADT_NOT_BOOTABLE',
        'format': 'apple-adt',
        'source_fdt_sha256': hashlib.sha256(raw).hexdigest(),
        'adt_sha256': hashlib.sha256(blob).hexdigest(),
        'adt_bytes': len(blob),
        'nodes': len(parsed),
        'cpu_nodes': args.cpus,
        'cpu_affinities': [hex(a) for _, a in ext['cpus'][:args.cpus]],
        'window_mib': args.window_mib,
        'soc_ranges_cells': [hex(v) for v in ext['soc_ranges_cells']],
        'gic_regions': [hex(v) for v in ext['gic_regions']],
        'gic_stride': hex(struct.unpack('<Q', ext['gic_stride'])[0]),
        'psci_method': ext['psci_method'].rstrip(b'\0').decode(),
        'nvram_bank_sha256': hashlib.sha256(nvram_proxy()['nvram-proxy-data']).hexdigest(),
        'decisions': {
            'container': 'Apple ADT, not FDT: DarwinBoot parses the ADT itself before handoff',
            'fd_base': '0xA7100000 kept; the only address with two independent documentary sources',
            'ramoops_overlap': 'accepted; loading the firmware volume overwrites the persistent kernel log',
            'boot_cpu': 'cpu0 (affinity 0x0) is an unverified candidate until P3 reads MPIDR_EL1',
            'dram_base_size': 'left zero to match the proven tree; consumer chain still unresolved',
        },
        'blockers': [
            'Boot MPIDR unverified; topology assumes affinity 0x0 is the running core',
            'Multi-CPU trees need MAX_CPU_CLUSTERS raised; AFF1 0..7 spans eight clusters',
            'Runtime EFI memory map, GOP geometry and CurrentEL not collected',
            'dram-base/dram-size consumer chain still unresolved',
        ],
    }
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Wrote %s (%d bytes, %d nodes, %d CPU); Apple ADT, not bootable.'
          % (args.output, len(blob), len(parsed), args.cpus))


if __name__ == '__main__':
    main()
