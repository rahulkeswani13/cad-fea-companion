"""Local-only HTTP access helper."""

from __future__ import annotations

from companion.main import client_is_loopback


def test_loopback_hosts_allowed():
    assert client_is_loopback("127.0.0.1")
    assert client_is_loopback("::1")
    assert client_is_loopback("localhost")
    assert client_is_loopback("testclient")
    assert client_is_loopback("::ffff:127.0.0.1")


def test_remote_hosts_rejected():
    assert not client_is_loopback("8.8.8.8")
    assert not client_is_loopback("10.0.0.5")
    assert not client_is_loopback(None)
    assert not client_is_loopback("")
