"""Validate a generated houji ADT against the current driver contract.

Checks the blob against ArmDTPlatform, ArmCpu and the pinned XNU topology
parser, and against the source FDT it was derived from. Static only: nothing
here proves the tree can boot.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ALLOWED = {'/', '/chosen', '/cpus', '/arm-io', '/arm-io/intc', '/defaults', '/options', '/psci'}
FORBIDDEN = ('/memory', '/reserved-memory', 'cpu-map', '/soc', '/firmware')
REQUIRED = ('/chosen', '/cpus', '/arm-io', '/defaults', '/options', '/psci')


def _normalize(nodes):
    """Re-key the parsed tree so the root is '/' regardless of its node name."""
    roots = [p for p in nodes if '/' not in p]
    if len(roots) != 1:
        raise ValueError('Expected exactly one root node, found %d' % len(roots))
    name = roots[0]
    if name != 'device-tree':
        raise ValueError('Root node is %r, platform expert expects device-tree' % name)
    out = {}
    for path, props in nodes.items():
        if path == name:
            out['/'] = props
        elif path.startswith(name + '/'):
            out['/' + path[len(name) + 1:]] = props
        else:
            raise ValueError('Detached node: %s' % path)
    return out


def validate(blob, source_nodes=None, allow_multicpu=False):
    """Return a report dict; raise ValueError on any contract violation."""
    parse = runpy.run_path(str(HERE / 'inspect-houji-fdt.py'))['parse']
    chrp = runpy.run_path(str(HERE / 'check-houji-chrp.py'))['validate']
    nodes, reserve = parse(blob)
    if reserve:
        raise ValueError('Unexpected memory reservation entries')
    nodes = _normalize(nodes)

    # --- tree shape -------------------------------------------------------
    for path in nodes:
        if any(f in path for f in FORBIDDEN):
            raise ValueError('Forbidden node in ADT: %s' % path)
        if path not in ALLOWED and not path.startswith('/cpus/cpu@'):
            raise ValueError('Node outside the whitelist: %s' % path)
    if len(nodes) > 16:
        raise ValueError('Node count %d exceeds the bring-up budget' % len(nodes))
    for required in REQUIRED:
        if required not in nodes:
            raise ValueError('Required node absent: %s' % required)

    # --- NVRAM ------------------------------------------------------------
    chosen = nodes['/chosen']
    if len(chosen.get('nvram-bank-size', b'')) != 4:
        raise ValueError('nvram-bank-size is not 4 bytes')
    if len(chosen.get('nvram-proxy-data', b'')) == 0:
        raise ValueError('nvram-proxy-data is empty')
    parts = chrp({'nvram-bank-size': chosen['nvram-bank-size'],
                  'nvram-proxy-data': chosen['nvram-proxy-data']})

    # --- CPU --------------------------------------------------------------
    cpu_paths = sorted(p for p in nodes if p.startswith('/cpus/'))
    if not cpu_paths:
        raise ValueError('No CPU nodes')
    running, affinities = 0, []
    for path in cpu_paths:
        props = nodes[path]
        if props.get('device_type') != b'cpu\0':
            raise ValueError('%s is not device_type cpu' % path)
        if 'state' not in props:
            raise ValueError('%s has no state property (parser panics)' % path)
        if props['state'].rstrip(b'\0') == b'running':
            running += 1
        reg = props.get('reg', b'')
        if len(reg) != 4:
            raise ValueError('%s reg is not 4 bytes' % path)
        affinities.append(struct.unpack('<I', reg)[0])
    if running != 1:
        raise ValueError('Expected exactly one running CPU, found %d' % running)
    if len(set(affinities)) != len(affinities):
        raise ValueError('Duplicate CPU affinities')
    for affinity in affinities:
        if ((affinity >> 8) & 0xFF) > 7:
            raise ValueError('AFF1 beyond the audited range')
    # The topology parser derives one cluster per distinct AFF1 and the current
    # patch leaves MAX_CPU_CLUSTERS at 1, so a multi-CPU tree asserts before any
    # driver runs. Refuse it here instead of producing a tree that cannot boot.
    clusters = {(a >> 8) & 0xFF for a in affinities}
    if len(cpu_paths) > 1 and not allow_multicpu:
        raise ValueError('%d CPU nodes span %d clusters; MAX_CPU_CLUSTERS is 1'
                         % (len(cpu_paths), len(clusters)))

    # --- GIC --------------------------------------------------------------
    bus = nodes['/arm-io'].get('ranges', b'')
    if len(bus) != 24:
        raise ValueError('arm-io ranges is %d bytes, driver needs 24' % len(bus))
    intc = nodes['/arm-io/intc']
    reg = intc.get('reg', b'')
    if len(reg) != 32:
        raise ValueError('intc reg is %d bytes, driver needs 32' % len(reg))
    if intc.get('compatible', b'') != b'arm,gic-v3\0':
        raise ValueError('intc compatible must be the 11-byte NUL-terminated string')
    stride_raw = intc.get('redistributor-stride', b'')
    if len(stride_raw) != 8:
        raise ValueError('redistributor-stride is not 8 bytes')
    stride, = struct.unpack('<Q', stride_raw)
    if stride not in (0x20000, 0x30000, 0x40000):
        raise ValueError('Unsupported stride %#x' % stride)

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
        'adt_sha256': hashlib.sha256(blob).hexdigest(),
        'adt_bytes': len(blob),
        'nodes': len(nodes),
        'cpu_nodes': len(cpu_paths),
        'cpu_affinities': [hex(a) for a in affinities],
        'running_cpus': running,
        'clusters': len(clusters),
        'gic_regions': [hex(v) for v in regions],
        'gic_stride': hex(stride),
        'nvram_partitions': parts,
        'scope': 'static contract check only; no boot, no MMIO',
    }


def _negative_cases(fdt_path, source_nodes):
    """Mutate the tree and confirm the checker refuses each variant."""
    build = runpy.run_path(str(HERE / 'build-houji-adt.py'))
    raw, nodes = build['load_fdt'](Path(fdt_path))
    ext = build['extract'](nodes)
    cases = {}

    def cpus_of(tree):
        return next(c for c in tree.children if c.name == 'cpus')

    tree = build['build_tree'](ext, 1)
    cpus_of(tree).children[0].props[b'state'] = b'not-running\0'
    cases['no running cpu'] = build['serialize'](tree)

    tree = build['build_tree'](ext, 2)
    for cpu in cpus_of(tree).children:
        cpu.props[b'state'] = b'running\0'
    cases['two running cpus'] = build['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    del cpus_of(tree).children[0].props[b'state']
    cases['missing state'] = build['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    leaked = build['Node']('memory')
    leaked.props[b'reg'] = b'\0' * 16
    tree.add(leaked)
    cases['leaked memory node'] = build['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    arm_io = next(c for c in tree.children if c.name == 'arm-io')
    arm_io.props[b'ranges'] = arm_io.props[b'ranges'][:16]
    cases['short ranges'] = build['serialize'](tree)

    tree = build['build_tree'](ext, 1)
    cpus_of(tree).add(build['Node']('cpu-map'))
    cases['cpu-map leaked in'] = build['serialize'](tree)

    return cases


def _multicpu_case(fdt_path):
    """An eight-CPU tree, which the current cluster limit cannot accept."""
    build = runpy.run_path(str(HERE / 'build-houji-adt.py'))
    raw, nodes = build['load_fdt'](Path(fdt_path))
    ext = build['extract'](nodes)
    return build['serialize'](build['build_tree'](ext, len(ext['cpus'])))


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
        for name, variant in _negative_cases(args.source, source_nodes).items():
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
