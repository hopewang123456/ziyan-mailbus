"""Linux distro profiles — Ubuntu + CentOS family (Rocky/Alma/RHEL)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class DistroProfile:
    id: str
    family: str  # debian | rhel | unknown
    package_hint: str
    firewall_hint: str
    mac_hint: str


UBUNTU = DistroProfile(
    id="ubuntu",
    family="debian",
    package_hint="apt",
    firewall_hint="ufw",
    mac_hint="apparmor",
)

CENTOS = DistroProfile(
    id="centos",
    family="rhel",
    package_hint="dnf|yum",
    firewall_hint="firewalld",
    mac_hint="selinux",
)

GENERIC = DistroProfile(
    id="unknown",
    family="unknown",
    package_hint="unknown",
    firewall_hint="unknown",
    mac_hint="unknown",
)


def parse_os_release(text: str) -> Mapping[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def detect_distro(os_release_text: str = "", *, os_release_path: str = "/etc/os-release") -> DistroProfile:
    """Detect Ubuntu vs CentOS family. Prefer explicit text (tests); else read path."""
    text = os_release_text
    if not text and os_release_path:
        try:
            with open(os_release_path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
    data = parse_os_release(text)
    oid = (data.get("ID") or "").lower()
    like = (data.get("ID_LIKE") or "").lower()
    if oid == "ubuntu" or "ubuntu" in like or "debian" in like:
        return UBUNTU
    if oid in ("centos", "rhel", "rocky", "almalinux", "fedora") or "rhel" in like or "centos" in like or "fedora" in like:
        return CENTOS
    if not text:
        return GENERIC
    return GENERIC
