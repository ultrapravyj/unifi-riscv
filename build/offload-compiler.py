#!/usr/bin/env python3
"""Linux compiler wrapper: native preprocessing/linking, desktop RISC-V code generation."""
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import zlib

args = sys.argv[1:]
kind = 'CXX' if Path(sys.argv[0]).name.endswith('cxx') else 'CC'
native = '/usr/bin/g++' if kind == 'CXX' else '/usr/bin/gcc'
if '-c' not in args or '-o' not in args:
    sys.exit(subprocess.call([native, *args]))
out_index = args.index('-o')
output = Path(args[out_index + 1])
sources = [a for a in args if a.endswith(('.cpp', '.cc', '.c', '.cxx', '.C'))]
if len(sources) != 1:
    sys.exit(subprocess.call([native, *args]))
source = sources[0]
preprocess_args = []
skip = False
for i, a in enumerate(args):
    if skip:
        skip = False
        continue
    if a == '-o':
        skip = True
    elif a == '-c':
        preprocess_args.append('-E')
    else:
        preprocess_args.append(a)
result = subprocess.run([native, *preprocess_args], capture_output=True)
if result.returncode:
    sys.stderr.buffer.write(result.stderr)
    sys.exit(result.returncode)
flags = []
skip = False
for a in args:
    if skip:
        skip = False
        continue
    if a in ['-o', '-include', '-I', '-D', '-isystem', '-iquote', '-imacros', '-MF', '-MT', '-MQ']:
        skip = True
    elif a == source or a in ['-c', '-pthread', '-MMD', '-MD', '-MP'] or a.startswith(('-I', '-D')):
        continue
    else:
        flags.append(a)
payload = zlib.compress(result.stdout, 1)
header = json.dumps({'kind': kind, 'flags': flags, 'name': source, 'source_size': len(payload)}).encode()

def read_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        b = connection.recv(min(1048576, size - len(data)))
        if not b:
            raise EOFError('Cross compiler connection closed')
        data.extend(b)
    return bytes(data)

with socket.create_connection(('127.0.0.1', 39001), timeout=120) as connection:
    connection.settimeout(1000)
    connection.sendall(struct.pack('!I', len(header)) + header + payload)
    response = json.loads(read_exact(connection, struct.unpack('!I', read_exact(connection, 4))[0]))
    binary = read_exact(connection, response['object_size'])
sys.stdout.write(response['stdout'])
sys.stderr.write(response['stderr'])
if response['status'] == 0:
    output.write_bytes(zlib.decompress(binary))
sys.exit(response['status'])
