"""Tests for pot_provider.py - bundled bgutil POT provider process manager."""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pot_provider
from pot_provider import PotProviderManager, bundle_available
from settings import Settings


def _fake_bundle(monkeypatch, tmp_path, script_body="import time\ntime.sleep(60)\n"):
    """Create a fake provider bundle: python interpreter as node, a script as main.js."""
    main_js = tmp_path / "build" / "main.js"
    main_js.parent.mkdir(parents=True)
    main_js.write_text(script_body)
    monkeypatch.setattr(pot_provider, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(pot_provider, "NODE_BIN", Path(sys.executable))
    monkeypatch.setattr(pot_provider, "MAIN_JS", main_js)
    return main_js


class TestBundleAvailable:
    def test_missing_bundle(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pot_provider, "NODE_BIN", tmp_path / "bin" / "node")
        monkeypatch.setattr(pot_provider, "MAIN_JS", tmp_path / "build" / "main.js")
        assert bundle_available() is False

    def test_present_bundle(self, monkeypatch, tmp_path):
        _fake_bundle(monkeypatch, tmp_path)
        assert bundle_available() is True


class TestApplySettings:
    async def test_disabled_does_not_start(self, monkeypatch, tmp_path):
        _fake_bundle(monkeypatch, tmp_path)
        mgr = PotProviderManager()
        await mgr.apply_settings(Settings(yt_pot_enabled=False))
        assert mgr._task is None

    async def test_external_url_does_not_start(self, monkeypatch, tmp_path):
        _fake_bundle(monkeypatch, tmp_path)
        mgr = PotProviderManager()
        await mgr.apply_settings(Settings(yt_pot_enabled=True, yt_pot_provider_url="http://pot:4416"))
        assert mgr._task is None

    async def test_missing_bundle_does_not_start(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pot_provider, "NODE_BIN", tmp_path / "missing-node")
        monkeypatch.setattr(pot_provider, "MAIN_JS", tmp_path / "missing.js")
        mgr = PotProviderManager()
        await mgr.apply_settings(Settings(yt_pot_enabled=True))
        assert mgr._task is None

    async def test_enabled_starts_and_disable_stops(self, monkeypatch, tmp_path):
        _fake_bundle(monkeypatch, tmp_path)

        async def no_ping(timeout=2.0):
            return False

        monkeypatch.setattr(pot_provider, "_ping", no_ping)
        monkeypatch.setattr(PotProviderManager, "_wait_ready", lambda self, proc: _true())
        mgr = PotProviderManager()
        await mgr.apply_settings(Settings(yt_pot_enabled=True))
        assert mgr._task is not None
        await asyncio.sleep(0.3)
        assert mgr._proc is not None
        assert mgr._proc.returncode is None
        assert mgr.is_healthy() is True
        await mgr.apply_settings(Settings(yt_pot_enabled=False))
        assert mgr._task is None
        assert mgr._proc is None
        assert mgr.is_healthy() is False


async def _true():
    return True


class TestSupervision:
    async def test_restarts_after_exit(self, monkeypatch, tmp_path):
        # Script exits immediately; the supervisor should respawn it
        main_js = _fake_bundle(monkeypatch, tmp_path, script_body="print('boot')\n")
        spawns = []
        real_exec = asyncio.create_subprocess_exec

        async def counting_exec(*args, **kwargs):
            spawns.append(args)
            return await real_exec(*args, **kwargs)

        async def no_ping(timeout=2.0):
            return False

        monkeypatch.setattr(pot_provider.asyncio, "create_subprocess_exec", counting_exec)
        monkeypatch.setattr(pot_provider, "_ping", no_ping)
        mgr = PotProviderManager()
        await mgr.start()
        try:
            # first spawn + ~1s readiness poll + 1s backoff + second spawn
            await asyncio.sleep(3.5)
            assert len(spawns) >= 2
            assert str(main_js) in spawns[0]
        finally:
            await mgr.stop()

    async def test_stop_terminates_running_process(self, monkeypatch, tmp_path):
        _fake_bundle(monkeypatch, tmp_path)

        async def no_ping(timeout=2.0):
            return False

        monkeypatch.setattr(pot_provider, "_ping", no_ping)
        monkeypatch.setattr(PotProviderManager, "_wait_ready", lambda self, proc: _true())
        mgr = PotProviderManager()
        await mgr.start()
        await asyncio.sleep(0.3)
        proc = mgr._proc
        assert proc is not None and proc.returncode is None
        await mgr.stop()
        assert proc.returncode is not None
        assert mgr._task is None

    async def test_existing_listener_not_replaced(self, monkeypatch, tmp_path):
        # If /ping already answers, no process is spawned
        _fake_bundle(monkeypatch, tmp_path)
        spawned = []

        async def yes_ping(timeout=2.0):
            return True

        async def fail_exec(*args, **kwargs):
            spawned.append(args)
            raise AssertionError("should not spawn")

        monkeypatch.setattr(pot_provider, "_ping", yes_ping)
        monkeypatch.setattr(pot_provider.asyncio, "create_subprocess_exec", fail_exec)
        mgr = PotProviderManager()
        await mgr.start()
        try:
            await asyncio.sleep(0.3)
            assert spawned == []
            assert mgr.is_healthy() is True
        finally:
            await mgr.stop()
