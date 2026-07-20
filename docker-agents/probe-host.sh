#!/bin/bash
docker exec docker-agents-mailbus-1 python3 <<'PY'
import socket
for host in ("host.docker.internal", "10.255.255.254"):
    try:
        print(host, "->", socket.gethostbyname(host))
    except Exception as e:
        print(host, "DNS FAIL", e)
PY
