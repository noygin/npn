import asyncio
import os
import subprocess
from pathlib import Path

from bot import ovpn

HELPER = Path(__file__).parent.parent / "deploy" / "ovpn-helper.sh"
FAKE_CLIENT = """#!/usr/bin/env bash
set -e
[ "$1" = 1 ] || exit 3
d=client/openvpn
mkdir -p $d/antizapret $d/vpn $d/vpn-udp
echo "days=$3" > "$d/antizapret/antizapret-$2-(1.2.3.4).ovpn"
echo x > "$d/vpn/vpn-$2-(1.2.3.4).ovpn"
echo x > "$d/vpn-udp/vpn-$2-(1.2.3.4)-udp.ovpn"
"""


def run_helper(tmp_path, az):
    env = {**os.environ, "OVPN_DIR": str(tmp_path / "ovpn"), "AZ_DIR": str(az)}
    subprocess.run(["bash", str(HELPER)], env=env, check=True, capture_output=True)


def test_helper_issues_profiles(tmp_path):
    az = tmp_path / "az"
    az.mkdir()
    (az / "client.sh").write_text(FAKE_CLIENT)
    base = tmp_path / "ovpn"
    name = ovpn.client_name(3, now=0)
    assert name == "tmp3d-700101-000000"
    ovpn.submit(base, name, 3)
    run_helper(tmp_path, az)
    result = asyncio.run(ovpn.wait(base, name, timeout=1, step=0.1))
    assert result.ok
    assert [f.name for f in result.files] == [
        f"antizapret-{name}-(1.2.3.4).ovpn", f"vpn-{name}-(1.2.3.4).ovpn"
    ]
    assert result.files[0].read_text() == "days=3\n"
    ovpn.cleanup(base, name)
    assert not (base / "done" / name).exists()


def test_helper_reports_missing_antizapret(tmp_path):
    base = tmp_path / "ovpn"
    ovpn.submit(base, "x1", 3)
    run_helper(tmp_path, tmp_path / "nope")
    result = asyncio.run(ovpn.wait(base, "x1", timeout=1, step=0.1))
    assert not result.ok and "client.sh" in result.error


def test_helper_ignores_bad_names(tmp_path):
    base = tmp_path / "ovpn" / "requests"
    base.mkdir(parents=True)
    (base / "bad.req").write_text("../../etc 3\n")
    run_helper(tmp_path, tmp_path)
    assert not list(base.iterdir())
    assert not list((tmp_path / "ovpn" / "done").iterdir())


def test_wait_times_out(tmp_path):
    assert asyncio.run(ovpn.wait(tmp_path, "none", timeout=0.2, step=0.1)) is None
