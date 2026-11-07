"""Apple ADT binary format: what DarwinBoot and XNU actually parse.

A node is a pair of little-endian uint32 counts (properties, children).
A property is a 32-byte NUL-padded name, a uint32 length, then the value,
padded so the next property starts on a 4-byte boundary. There is no magic,
no string table and no inline node name: the name is a property.

Two consequences drive every caller here. A node with zero properties is
unreachable for its children, because XNU's skipProperties() returns NULL
instead of the position after the header, so every node carries a `name`
property. And DarwinBoot requires the walk to end exactly at the end of the
file, so no trailing padding is allowed.
"""
import struct

NAME_FIELD = 32
PROP_HEADER = NAME_FIELD + 4
NODE_HEADER = 8
MAX_DEPTH = 64


class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name, props=None, children=None):
        self.name = name
        self.props = list(props or [])
        self.children = list(children or [])

    def add(self, child):
        self.children.append(child)
        return child

    def get(self, key):
        for name, value in self.props:
            if name == key:
                return value
        return None


def _encode_name(name):
    raw = name.encode('ascii')
    if not raw or len(raw) >= NAME_FIELD:
        raise ValueError('property or node name must be 1..%d bytes: %r' % (NAME_FIELD - 1, name))
    return raw.ljust(NAME_FIELD, b'\0')


def serialize(root):
    """Emit the tree; every node gets its name property first."""
    out = bytearray()

    def emit(node, depth):
        if depth > MAX_DEPTH:
            raise ValueError('tree deeper than %d levels' % MAX_DEPTH)
        props = [('name', node.name.encode('ascii') + b'\0')]
        for name, value in node.props:
            if name == 'name':
                raise ValueError('name is emitted automatically')
            props.append((name, value))
        out.extend(struct.pack('<II', len(props), len(node.children)))
        for name, value in props:
            out.extend(_encode_name(name))
            out.extend(struct.pack('<I', len(value)))
            out.extend(value)
            out.extend(b'\0' * (-len(out) % 4))
        for child in node.children:
            emit(child, depth + 1)

    emit(root, 0)
    return bytes(out)


def parse(data):
    """Walk the blob the way XNU does; return ({path: {prop: value}}, used)."""
    nodes = {}
    offset = 0

    def walk(depth, path):
        nonlocal offset
        if depth > MAX_DEPTH:
            raise ValueError('tree deeper than %d levels' % MAX_DEPTH)
        if len(data) - offset < NODE_HEADER:
            raise ValueError('truncated node header at %#x' % offset)
        count, children = struct.unpack_from('<II', data, offset)
        offset += NODE_HEADER
        props = {}
        for _ in range(count):
            if len(data) - offset < PROP_HEADER:
                raise ValueError('truncated property header at %#x' % offset)
            raw_name = data[offset:offset + NAME_FIELD]
            if b'\0' not in raw_name:
                raise ValueError('property name is not NUL-padded at %#x' % offset)
            name = raw_name.split(b'\0', 1)[0].decode('ascii')
            length, = struct.unpack_from('<I', data, offset + NAME_FIELD)
            offset += PROP_HEADER
            if length > len(data) - offset:
                raise ValueError('property %s overruns the blob' % name)
            if name in props:
                raise ValueError('duplicate property %s in %s' % (name, path or '/'))
            props[name] = data[offset:offset + length]
            offset += length
            offset += -offset % 4
        if 'name' not in props:
            raise ValueError('node without a name property at %s' % (path or '/'))
        node_name = props['name'].rstrip(b'\0').decode('ascii')
        here = node_name if path is None else path + '/' + node_name
        nodes[here] = props
        for _ in range(children):
            walk(depth + 1, here)

    walk(0, None)
    return nodes, offset
