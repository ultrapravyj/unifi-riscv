#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Optional GCC code-generation relay over authenticated SSH loopback forwarding."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import getpass
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib
import paramiko

def read_exact(channel, count):
    data = bytearray()
    while len(data) < count:
        part = channel.recv(min(count - len(data), 1048576))
        if not part:
            raise EOFError('Compile channel closed')
        data.extend(part)
    return bytes(data)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-host', required=True)
    parser.add_argument('--ssh-user', default='root')
    parser.add_argument('--ssh-key')
    parser.add_argument('--ssh-port', type=int, default=22)
    parser.add_argument('--toolchain-bin', required=True)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    # Trust must be established with OpenSSH first; no password/key persistence.
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.ssh_host, port=args.ssh_port, username=args.ssh_user,
                key_filename=args.ssh_key, password=None if args.ssh_key else getpass.getpass('SSH password: '), timeout=30)
    transport = ssh.get_transport()
    transport.set_keepalive(20)
    transport.request_port_forward('127.0.0.1', 39001)
    def compile(channel):
        try:
            header = json.loads(read_exact(channel, struct.unpack('!I', read_exact(channel, 4))[0]))
            source = zlib.decompress(read_exact(channel, header['source_size']))
            with tempfile.TemporaryDirectory(prefix='riscv-codegen-') as folder:
                folder = Path(folder)
                input_file, object_file = folder / 'source.i', folder / 'output.o'
                input_file.write_bytes(source)
                name = 'riscv-none-elf-g++' if header['kind'] == 'CXX' else 'riscv-none-elf-gcc'
                import os
                if os.name == 'nt': name += '.exe'
                result = subprocess.run([str(Path(args.toolchain_bin) / name), '-march=rv64gc', '-mabi=lp64d', '-mtune=rocket',
                                         *header['flags'], '-x', 'c++-cpp-output' if header['kind'] == 'CXX' else 'cpp-output',
                                         '-c', str(input_file), '-o', str(object_file)], capture_output=True, timeout=1800)
                payload = zlib.compress(object_file.read_bytes(), 1) if result.returncode == 0 else b''
                reply = json.dumps({'status': result.returncode, 'stdout': result.stdout.decode(errors='replace'),
                                    'stderr': result.stderr.decode(errors='replace'), 'object_size': len(payload)}).encode()
                channel.sendall(struct.pack('!I', len(reply)) + reply + payload)
        finally:
            channel.close()
    print('Build relay listening on target loopback port 39001; runtime remains native.')
    with ThreadPoolExecutor(max_workers=4) as executor:
        while transport.is_active():
            channel = transport.accept(10)
            if channel is not None:
                executor.submit(compile, channel)
    ssh.close()

if __name__ == '__main__':
    main()
