"""Validate a generated houji ADT against the driver and loader contracts.

Three consumers constrain the blob: DarwinBoot walks it before handoff and
requires the walk to end exactly at the file length, XNU's topology parser
reads state/reg per CPU node, and ArmDTPlatform and ArmCpu read the GIC and
NVRAM properties with fixed widths. Static only: nothing here proves a boot.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ALLOWED = {'/', '/chosen', '/cpus', '/arm-io', '/arm-io/intc',
           '/defaults', '/options', '/aliases', '/psci'}
FORBIDDEN = ('memory', 'reserved-memory', 'soc', 'cpu-map')
REQUIRED = ('/chosen', '/cpus', '/arm-io', '/defaults', '/options', '/psci')


def _normalize(nodes):
    """Re-key so the root is '/', whatever the root node is called."""
    roots = [p for p in nodes if '/' not in p]
    if len(roots) != 1:
        raise ValueError('expected exactly one root node, found %d' % len(roots))
    name = roots[0]
    if name != 'device-tree':
        raise ValueError('root node is %r, the platform expert expects device-tree' % name)
    out = {}
    for path, props in nodes.items():
        if path == name:
            out['/'] = props
        elif path.startswith(name + '/'):
            out['/' + path[len(name) + 1:]] = props
        else:
            raise ValueError('detached node: %s' % path)
    return out


def validate(blob, source_nodes=None, allow_multicpu=False):
    fmt = runpy.run_path(str(HERE / 'houji-adt-format.py'))
    chrp = runpy.run_path(str(HERE / 'check-houji-chrp.py'))['validate']

    nodes, used = fmt['parse'](blob)
    # DarwinBoot refuses the tree unless the walk consumes the whole file.
    if used != len(blob):
        raise ValueError('walk consumed %d of %d bytes; DarwinBoot requires an exact end'
                         % (used, len(blob)))
    nodes = _normalize(nodes)

    for path in nodes:
        if any(f in path.strip('/').split('/') for f in FORBIDDEN):
            raise ValueError('forbidden node in ADT: %s' % path)
        if path not in ALLOWED and not path.startswith('/cpus/'):
            raise ValueError('node outside the whitelist: %s' % path)
    if len(nodes) > 16:
        raise ValueError('node count %d exceeds the bring-up budget' % len(nodes))
    for required in REQUIRED:
        if required not in nodes:
            raise ValueError('required node absent: %s' % required)

    # --- NVRAM ------------------------------------------------------------
    chosen = nodes['/chosen']
    for key, width in (('nvram-bank-size', 4), ('nvram-bank-count', 4), ('nvram-current-bank', 4)):
        if len(chosen.get(key, b'')) != width:
            raise ValueError('%s is not %d bytes' % (key, width))
    if len(chosen.get('nvram-proxy-data', b'')) == 0:
        raise ValueError('nvram-proxy-data is empty')
    parts = chrp({'nvram-bank-size': chosen['nvram-bank-size'],
                  'nvram-proxy-data': chosen['nvram-proxy-data']})
    window = chosen.get('darwinboot-memory-size', b'')
    if len(window) != 8:
        raise ValueError('darwinboot-memory-size must be 8 bytes')
    window_bytes, = struct.unpack('<Q', window)
    if not (256 << 20 <= window_bytes <= 8 << 30) or window_bytes % (2 << 20):
        raise ValueError('darwinboot-memory-size out of range or unaligned')

    # --- CPU --------------------------------------------------------------
    cpu_paths = sorted(p for p in nodes if p.startswith('/cpus/'))
    if not cpu_paths:
        raise ValueError('no CPU nodes')
    running, affinities = 0, []
    for path in cpu_paths:
        props = nodes[path]
        if props.get('device_type') != b'cpu\0':
            raise ValueError('%s is not device_type cpu' % path)
        if 'state' not in props:
            raise ValueError('%s has no state property (the parser panics)' % path)
        if props['state'].rstrip(b'\0') == b'running':
            running += 1
        reg = props.get('reg', b'')
        if len(reg) != 4:
            raise ValueError('%s reg is not 4 bytes' % path)
        affinities.append(struct.unpack('<I', reg)[0])
    if running != 1:
        raise ValueError('expected exactly one running CPU, found %d' % running)
    if len(set(affinities)) != len(affinities):
        raise ValueError('duplicate CPU affinities')
    clusters = {(a >> 8) & 0xFF for a in affinities}
    for affinity in affinities:
        if ((affinity >> 8) & 0xFF) > 7:
            raise ValueError('AFF1 beyond the audited range')
    if len(cpu_paths) > 1 and not allow_multicpu:
        raise ValueError('%d CPU nodes span %d clusters; MAX_CPU_CLUSTERS is 1'
                         % (len(cpu_paths), len(clusters)))

    # --- GIC --------------------------------------------------------------
    bus = nodes['/arm-io'].get('ranges', b'')
    if len(bus) != 24:
        raise ValueError('arm-io ranges is %d bytes, the driver needs 24' % len(bus))
    intc = nodes['/arm-io/intc']
    reg = intc.get('reg', b'')
    if len(reg) != 32:
        raise ValueError('intc reg is %d bytes, the driver needs 32' % len(reg))
    if intc.get('compatible', b'') != b'arm,gic-v3\0':
        raise ValueError('intc compatible must be the 11-byte NUL-terminated string')
    stride_raw = intc.get('redistributor-stride', b'')
    if len(stride_raw) != 8:
        raise ValueError('redistributor-stride is not 8 bytes')
    stride, = struct.unpack('<Q', stride_raw)
    if stride not in (0x20000, 0x30000, 0x40000):
        raise ValueError('unsupported stride %#x' % stride)

    regions = struct.unpack('<4Q', reg)
    child, parent, span = struct.unpack('<3Q', bus)
    if regions[1] < 0x10000 or regions[3] < 0x20000:
        raise ValueError('GIC region below the driver minimum')
    for base, size in zip(regions[::2], regions[1::2]):
        if base < child or base - child > span or size > span - (base - child):
            raise ValueError('GIC region outside the bus window')

    # --- PSCI -------------------------------------------------------------
    method = nodes['/psci'].get('method', b'')
    if len(method) != 4 or method not in (b'smc\0', b'hvc\0'):
        raise ValueError('psci method must be smc or hvc, 4 bytes')

    # --- agreement with the source FDT ------------------------------------
    if source_nodes is not None:
        soc = source_nodes['/soc']
        src_child, src_parent, src_span = struct.unpack('>IQI', soc['ranges'])
        if (src_child, src_parent, src_span) != (child, parent, span):
            raise ValueError('ranges does not match the source FDT')
        gic = next(v for v in source_nodes.values()
                   if b'arm,gic-v3' in v.get('compatible', b'').split(b'\0'))
        if struct.unpack('>4I', gic['reg']) != regions:
            raise ValueError('GIC regions do not match the source FDT')
        src_stride, = struct.unpack('>Q', gic['redistributor-stride'])
        if src_stride != stride:
            raise ValueError('stride does not match the source FDT')
        if source_nodes['/soc/psci']['method'] != method:
            raise ValueError('PSCI method does not match the source FDT')
        src_affinity = set()
        for path, props in source_nodes.items():
            if path.startswith('/cpus/') and props.get('device_type') == b'cpu\0':
                src_affinity.add(struct.unpack('>Q', props['reg'])[0])
        for affinity in affinities:
            if affinity not in src_affinity:
                raise ValueError('CPU affinity %#x absent from the source FDT' % affinity)

    return {
        'result': 'PASS',
        'format': 'apple-adt',
        'adt_sha256': hashlib.sha256(blob).hexdigest(),
        'adt_bytes': len(blob),
        'nodes': len(nodes),
        'cpu_nodes': len(cpu_paths),
        'cpu_affinities': [hex(a) for a in affinities],
        'running_cpus': running,
        'clusters': len(clusters),
        'gic_regions': [hex(v) for v in regions],
        'gic_stride': hex(stride),
        'window_mib': window_bytes >> 20,
        'nvram_partitions': parts,
        'scope': 'static contract check only; no boot, no MMIO',
    }


def _negative_cases(fdt_path):
    """Mutate the tree and confirm the checker refuses each variant."""
    build = runpy.run_path(str(HERE / 'build-houji-adt.py'))
    fmt = runpy.run_path(str(HERE / 'houji-adt-format.py'))
    raw, nodes = build['load_fdt'](Path(fdt_path))
    ext = build['extract'](nodes)
    cases = {}

    def cpus_of(tree):
        return next(c for c in tree.children if c.name == 'cpus')

    def set_prop(node, key, value):
        node.props = [(k, value if k == key else v) for k, v in node.props]

    tree = build['build_tree'](ext, 1)
    set_prop(cpus_of(tree).children[0], 'state', b'waiting\0')
    cases['no running cpu'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 2)
    for cpu in cpus_of(tree).children:
        set_prop(cpu, 'state', b'running\0')
    cases['two running cpus'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    cpu0 = cpus_of(tree).children[0]
    cpu0.props = [(k, v) for k, v in cpu0.props if k != 'state']
    cases['missing state'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    tree.add(fmt['Node']('memory', [('reg', b'\0' * 16)]))
    cases['leaked memory node'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    arm_io = next(c for c in tree.children if c.name == 'arm-io')
    set_prop(arm_io, 'ranges', arm_io.get('ranges')[:16])
    cases['short ranges'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    cpus_of(tree).add(fmt['Node']('cpu-map'))
    cases['cpu-map leaked in'] = fmt['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    chosen = next(c for c in tree.children if c.name == 'chosen')
    set_prop(chosen, 'darwinboot-memory-size', bytes(8))
    cases['zero memory window'] = fmt['serialize'](tree)

    good = fmt['serialize'](build['build_tree'](ext, 1))
    cases['trailing bytes after the tree'] = good + b'\0' * 4
    cases['truncated tree'] = good[:-4]

    return cases


def _multicpu_case(fdt_path):
    build = runpy.run_path(str(HERE / 'build-houji-adt.py'))
    fmt = runpy.run_path(str(HERE / 'houji-adt-format.py'))
    raw, nodes = build['load_fdt'](Path(fdt_path))
    ext = build['extract'](nodes)
    return fmt['serialize'](build['build_tree'](ext, len(ext['cpus'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('adt', type=Path)
    parser.add_argument('--source', type=Path, help='source FDT for agreement checks')
    parser.add_argument('--negatives', action='store_true', help='also run rejection cases')
    parser.add_argument('--allow-multicpu', action='store_true',
                        help='permit more than one CPU node (needs MAX_CPU_CLUSTERS raised)')
    args = parser.parse_args()

    source_nodes = None
    if args.source:
        load = runpy.run_path(str(HERE / 'inspect-houji-fdt.py'))
        source_nodes = load['parse'](args.source.read_bytes())[0]

    report = validate(args.adt.read_bytes(), source_nodes, args.allow_multicpu)

    if args.negatives:
        if not args.source:
            raise SystemExit('--negatives requires --source')
        rejected = []
        for name, variant in _negative_cases(args.source).items():
            try:
                validate(variant, None, allow_multicpu=True)
            except ValueError:
                rejected.append(name)
            else:
                raise AssertionError('variant accepted but should be refused: %s' % name)
        try:
            validate(_multicpu_case(args.source), None, allow_multicpu=False)
        except ValueError:
            rejected.append('eight cpus under MAX_CPU_CLUSTERS=1')
        else:
            raise AssertionError('multi-CPU tree accepted under a single-cluster limit')
        report['negative_cases'] = rejected

    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
