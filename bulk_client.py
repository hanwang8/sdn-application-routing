#!/usr/bin/env python3
"""Send a configurable number of MiB to the demo bulk server."""

import socket
import sys


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.2"
    size_mib = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    target = size_mib * 1024 * 1024
    payload = b"T" * 65536

    with socket.create_connection((host, 5001), timeout=10) as connection:
        sent = 0
        while sent < target:
            amount = min(len(payload), target - sent)
            connection.sendall(payload[:amount])
            sent += amount
        connection.shutdown(socket.SHUT_WR)
        acknowledgement = connection.recv(64).decode("ascii")

    print("Sent {} bytes; server received {} bytes".format(sent, acknowledgement))


if __name__ == "__main__":
    main()
