"""Shared Paramiko command-session lifecycle helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from paramiko import Transport
from paramiko.channel import Channel


@contextmanager
def open_ssh_session(transport: Transport, command: str) -> Iterator[Channel]:
    """Open a command channel and always close it after the caller finishes."""
    session = transport.open_session()
    try:
        session.exec_command(command)
        yield session
    finally:
        session.close()
