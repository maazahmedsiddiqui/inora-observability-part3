"""Replica identity (Assignment 3).

Docker Compose scaling starts several identical containers per service. Each one needs a short, stable name
that appears in its logs, in a response header (`X-Replica` / gRPC metadata `x-replica`) and in a metric, so
every request can be traced to the replica that handled it.

Naming rule: Compose names the containers `<project>-<service>-<n>` (for example
`inora-observability-part3-api-2`). Replica A is container 1, B is container 2, C is container 3.

How a container finds its own number: Docker's DNS resolves every container name. If REPLICA_BASE is set
(for example `inora-observability-part3-api`), the container resolves `<REPLICA_BASE>-1`, `-2`, ... and the
one whose address equals its own address is itself. (Reverse DNS cannot be used: /etc/hosts answers first
with the container id.)

Order of precedence: REPLICA_ID (explicit override) > DNS lookup via REPLICA_BASE > container hostname.
The replica name is NEVER a unique-per-request value, so it is safe as a metric label (at most a handful of values).
"""
import os
import socket


def _letter(n):
    return chr(ord("A") + n - 1) if 1 <= n <= 26 else str(n)


def resolve_replica_id(environ=None, resolver=socket.gethostbyname, hostname=socket.gethostname):
    env = os.environ if environ is None else environ
    explicit = (env.get("REPLICA_ID") or "").strip()
    if explicit:
        return explicit
    base = (env.get("REPLICA_BASE") or "").strip()
    try:
        own_name = hostname()
    except OSError:
        own_name = ""
    if base:
        try:
            me = resolver(own_name)
        except OSError:
            me = None
        if me:
            for n in range(1, 10):
                try:
                    if resolver(f"{base}-{n}") == me:
                        return _letter(n)
                except OSError:
                    continue
    return own_name[:12] or "unknown"


REPLICA = resolve_replica_id()
