from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Representative:
    name: str = ""
    passport: str = ""
    address: str = ""
    phone: str = ""
    discord: str = ""
    passport_scan_url: str = ""


@dataclass
class Victim:
    name: str = ""
    passport: str = ""
    address: str = ""
    phone: str = ""
    discord: str = ""
    passport_scan_url: str = ""
