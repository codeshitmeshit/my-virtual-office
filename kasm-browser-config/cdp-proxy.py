#!/usr/bin/env python3
import selectors
import socket


LISTEN = ("0.0.0.0", 9223)
UPSTREAM = ("127.0.0.1", 9222)


def proxy(client):
    upstream = socket.create_connection(UPSTREAM)
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, upstream)
    selector.register(upstream, selectors.EVENT_READ, client)
    try:
        while True:
            for key, _ in selector.select():
                data = key.fileobj.recv(65536)
                if not data:
                    return
                key.data.sendall(data)
    finally:
        selector.close()
        client.close()
        upstream.close()


def main():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    while True:
        client, _ = server.accept()
        try:
            proxy(client)
        except OSError:
            client.close()


if __name__ == "__main__":
    main()
