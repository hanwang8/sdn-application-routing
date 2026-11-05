#!/usr/bin/env python3
"""Tiny TCP sink used by the automated Mininet demonstration."""

import socket


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", 5001))
        server.listen(5)
        while True:
            connection, _ = server.accept()
            with connection:
                total = 0
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                connection.sendall(str(total).encode("ascii"))


if __name__ == "__main__":
    main()
