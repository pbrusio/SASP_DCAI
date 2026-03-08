"""SASP ISE Authentication Event Generator

Generates synthetic Cisco ISE authentication events for DFP (Digital
Fingerprinting) model training. Each user profile has a distinct
behavioral fingerprint (work hours, devices, locations, failure rate)
so the DFP model can learn per-user baselines. Anomaly scenarios inject
deviations to train and validate detection.

Usage:
    # Dry run — print events to stdout
    python -m sasp.scripts.testing.ise_auth_generator --dry-run --duration-days 1

    # Produce 30 days of events to Kafka
    python -m sasp.scripts.testing.ise_auth_generator --duration-days 30 --rate 50

    # List profiles and scenarios
    python -m sasp.scripts.testing.ise_auth_generator --list
"""

import argparse
import json
import logging
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

USER_PROFILES: list[dict] = [
    {
        "username": "jsmith",
        "display_name": "John Smith",
        "work_hours": (8, 18),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"],
        "locations": [
            ("10.0.1.1", "11:22:33:44:55:01", "Ethernet"),
            ("10.0.1.2", "11:22:33:44:55:02", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Corporate-Wired",
        "avg_auths_per_day": 8,
        "failure_rate": 0.02,
    },
    {
        "username": "agarcia",
        "display_name": "Ana Garcia",
        "work_hours": (7, 20),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:03"],
        "locations": [
            ("10.0.2.1", "11:22:33:44:55:03", "Virtual"),
        ],
        "auth_type": "802.1X",
        "policy_set": "VPN-Remote",
        "avg_auths_per_day": 12,
        "failure_rate": 0.05,
    },
    {
        "username": "mchen",
        "display_name": "Michael Chen",
        "work_hours": (6, 22),
        "work_days": [0, 1, 2, 3, 4, 5],
        "devices": ["AA:BB:CC:DD:EE:04", "AA:BB:CC:DD:EE:05", "AA:BB:CC:DD:EE:06"],
        "locations": [
            ("10.0.1.1", "11:22:33:44:55:01", "Ethernet"),
            ("10.0.1.3", "11:22:33:44:55:04", "Ethernet"),
            ("10.0.3.1", "11:22:33:44:55:05", "Ethernet"),
            ("10.0.3.2", "11:22:33:44:55:06", "Ethernet"),
            ("10.0.4.1", "11:22:33:44:55:07", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "IT-Admin",
        "avg_auths_per_day": 20,
        "failure_rate": 0.03,
    },
    {
        "username": "kpatel",
        "display_name": "Kavita Patel",
        "work_hours": (9, 17),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:07", "AA:BB:CC:DD:EE:08"],
        "locations": [
            ("10.0.1.4", "11:22:33:44:55:08", "Ethernet"),
            ("10.0.1.5", "11:22:33:44:55:09", "Wireless"),
            ("10.0.5.1", "11:22:33:44:55:10", "Wireless"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Executive",
        "avg_auths_per_day": 4,
        "failure_rate": 0.01,
    },
    {
        "username": "bot_svc01",
        "display_name": "Service Account 01",
        "work_hours": (0, 24),
        "work_days": [0, 1, 2, 3, 4, 5, 6],
        "devices": ["AA:BB:CC:DD:EE:09"],
        "locations": [
            ("10.0.3.1", "11:22:33:44:55:05", "Ethernet"),
        ],
        "auth_type": "TACACS+",
        "policy_set": "Service-Accounts",
        "avg_auths_per_day": 48,
        "failure_rate": 0.001,
    },
    {
        "username": "ljones",
        "display_name": "Laura Jones",
        "work_hours": (10, 19),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:0A", "AA:BB:CC:DD:EE:0B"],
        "locations": [
            ("10.0.1.2", "11:22:33:44:55:02", "Ethernet"),
            ("10.0.5.2", "11:22:33:44:55:11", "Wireless"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Corporate-Wired",
        "avg_auths_per_day": 6,
        "failure_rate": 0.02,
    },
    {
        "username": "rwilson",
        "display_name": "Robert Wilson",
        "work_hours": (7, 16),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:0C"],
        "locations": [
            ("10.0.6.1", "11:22:33:44:55:12", "Ethernet"),
            ("10.0.6.2", "11:22:33:44:55:13", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Manufacturing",
        "avg_auths_per_day": 10,
        "failure_rate": 0.04,
    },
    {
        "username": "slee",
        "display_name": "Sarah Lee",
        "work_hours": (8, 17),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:0D", "AA:BB:CC:DD:EE:0E"],
        "locations": [
            ("10.0.1.6", "11:22:33:44:55:14", "Ethernet"),
            ("10.0.5.3", "11:22:33:44:55:15", "Wireless"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Corporate-Wired",
        "avg_auths_per_day": 7,
        "failure_rate": 0.02,
    },
    {
        "username": "bot_svc02",
        "display_name": "Service Account 02",
        "work_hours": (0, 24),
        "work_days": [0, 1, 2, 3, 4, 5, 6],
        "devices": ["AA:BB:CC:DD:EE:0F"],
        "locations": [
            ("10.0.3.2", "11:22:33:44:55:06", "Ethernet"),
        ],
        "auth_type": "TACACS+",
        "policy_set": "Service-Accounts",
        "avg_auths_per_day": 96,
        "failure_rate": 0.001,
    },
    {
        "username": "dkim",
        "display_name": "David Kim",
        "work_hours": (11, 20),
        "work_days": [1, 2, 3, 4, 5],
        "devices": ["AA:BB:CC:DD:EE:10"],
        "locations": [
            ("10.0.2.1", "11:22:33:44:55:03", "Virtual"),
            ("10.0.1.7", "11:22:33:44:55:16", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "VPN-Remote",
        "avg_auths_per_day": 10,
        "failure_rate": 0.03,
    },
    {
        "username": "enguyen",
        "display_name": "Emily Nguyen",
        "work_hours": (8, 18),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:11", "AA:BB:CC:DD:EE:12"],
        "locations": [
            ("10.0.1.8", "11:22:33:44:55:17", "Ethernet"),
            ("10.0.5.4", "11:22:33:44:55:18", "Wireless"),
            ("10.0.7.1", "11:22:33:44:55:19", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Engineering",
        "avg_auths_per_day": 14,
        "failure_rate": 0.03,
    },
    {
        "username": "tmartin",
        "display_name": "Thomas Martin",
        "work_hours": (6, 15),
        "work_days": [0, 1, 2, 3, 4],
        "devices": ["AA:BB:CC:DD:EE:13"],
        "locations": [
            ("10.0.6.3", "11:22:33:44:55:1A", "Ethernet"),
        ],
        "auth_type": "802.1X",
        "policy_set": "Manufacturing",
        "avg_auths_per_day": 6,
        "failure_rate": 0.04,
    },
    {
        "username": "bot_monitor",
        "display_name": "Monitoring Service",
        "work_hours": (0, 24),
        "work_days": [0, 1, 2, 3, 4, 5, 6],
        "devices": ["AA:BB:CC:DD:EE:14"],
        "locations": [
            ("10.0.4.1", "11:22:33:44:55:07", "Ethernet"),
        ],
        "auth_type": "TACACS+",
        "policy_set": "Service-Accounts",
        "avg_auths_per_day": 144,
        "failure_rate": 0.0,
    },
]

# ---------------------------------------------------------------------------
# Anomaly scenario definitions
# ---------------------------------------------------------------------------

ANOMALY_SCENARIOS: dict[str, dict] = {
    "brute_force": {
        "description": "50+ failed auths in 5 min from one user",
        "dfp_signal": "Spike in failure rate",
        "count": 55,
    },
    "impossible_travel": {
        "description": "User auths from 2 distant NAS IPs within 2 minutes",
        "dfp_signal": "Location change + time anomaly",
        "count": 2,
    },
    "new_device": {
        "description": "Known user, never-seen-before MAC address",
        "dfp_signal": "Device fingerprint change",
        "count": 1,
    },
    "off_hours": {
        "description": "Office worker authenticating at 3am",
        "dfp_signal": "Temporal anomaly",
        "count": 1,
    },
    "credential_stuffing": {
        "description": "Multiple different usernames from same calling_station_id",
        "dfp_signal": "Cross-user device sharing",
        "count": 10,
    },
    "compromised_svc": {
        "description": "Service account changes NAS IP or timing pattern",
        "dfp_signal": "Behavioral drift",
        "count": 3,
    },
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

# Reverse mapping: internal auth_result → real ISE MESSAGE_CODE
_AUTH_RESULT_TO_CODE: dict[str, str] = {"PASS": "5200", "FAIL": "5400"}

# Reverse mapping: internal auth_type → real ISE Protocol
_AUTH_TYPE_TO_PROTOCOL: dict[str, str] = {"802.1X": "Radius", "TACACS+": "Tacacs"}


class ISEAuthGenerator:
    """Generates synthetic ISE authentication events with anomaly injection."""

    def __init__(self, seed: int = 42, anomaly_probability: float = 0.02) -> None:
        self.rng = random.Random(seed)
        self.profiles = USER_PROFILES
        self.anomaly_probability = anomaly_probability

    def _make_event(
        self,
        username: str,
        nas_ip: str,
        calling_station_id: str,
        called_station_id: str,
        auth_result: str,
        policy_set: str,
        timestamp: datetime,
        auth_type: str = "802.1X",
        nas_port_type: str = "Ethernet",
        anomaly_label: str | None = None,
    ) -> dict:
        """Build a single ISE auth record dict."""
        event: dict = {
            "username": username,
            "nas_ip": nas_ip,
            "calling_station_id": calling_station_id,
            "called_station_id": called_station_id,
            "auth_result": auth_result,
            "policy_set": policy_set,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "auth_type": auth_type,
            "nas_port_type": nas_port_type,
            "session_id": str(uuid.UUID(int=self.rng.getrandbits(128), version=4)),
        }
        if anomaly_label is not None:
            event["_anomaly_label"] = anomaly_label
        return event

    @staticmethod
    def _to_real_ise_format(event: dict) -> dict:
        """Convert an internal-format event to real ISE syslog field names.

        Used with --real-ise-format to test the normalization path end-to-end.
        """
        real: dict = {}
        real["UserName"] = event.get("username", "")
        real["NAS_IP_Address"] = event.get("nas_ip", "")
        # Colon-separated MACs → dash-separated (real ISE style)
        real["Calling_Station_ID"] = event.get("calling_station_id", "").replace(":", "-")
        real["Called_Station_ID"] = event.get("called_station_id", "").replace(":", "-")
        real["MESSAGE_CODE"] = _AUTH_RESULT_TO_CODE.get(
            event.get("auth_result", ""), "5200",
        )
        real["Protocol"] = _AUTH_TYPE_TO_PROTOCOL.get(
            event.get("auth_type", ""), event.get("auth_type", ""),
        )
        real["NAS_Port_Type"] = event.get("nas_port_type", "Ethernet")
        real["ISEPolicySetName"] = event.get("policy_set", "")
        real["_time"] = event.get("timestamp", "")
        real["AcsSessionID"] = event.get("session_id", "")
        if "_anomaly_label" in event:
            real["_anomaly_label"] = event["_anomaly_label"]
        return real

    def generate_normal_event(self, profile: dict, sim_time: datetime) -> dict:
        """Generate a normal auth event for the given user at sim_time."""
        device = self.rng.choice(profile["devices"])
        nas_ip, called_id, port_type = self.rng.choice(profile["locations"])
        auth_result = "FAIL" if self.rng.random() < profile["failure_rate"] else "PASS"
        return self._make_event(
            username=profile["username"],
            nas_ip=nas_ip,
            calling_station_id=device,
            called_station_id=called_id,
            auth_result=auth_result,
            policy_set=profile["policy_set"],
            timestamp=sim_time,
            auth_type=profile["auth_type"],
            nas_port_type=port_type,
        )

    def _random_mac(self) -> str:
        """Generate a random MAC address not in any profile's device list."""
        return ":".join(f"{self.rng.randint(0, 255):02X}" for _ in range(6))

    def _pick_human_profile(self) -> dict:
        """Pick a random non-service-account profile."""
        humans = [p for p in self.profiles if not p["username"].startswith("bot_")]
        return self.rng.choice(humans)

    def _pick_svc_profile(self) -> dict:
        """Pick a random service account profile."""
        svcs = [p for p in self.profiles if p["username"].startswith("bot_")]
        return self.rng.choice(svcs)

    def generate_anomaly_events(
        self, scenario_name: str, sim_time: datetime
    ) -> list[dict]:
        """Generate anomalous auth event(s) for the named scenario.

        Returns a list because some scenarios (brute_force, credential_stuffing)
        produce multiple events in a burst.
        """
        events: list[dict] = []
        scenario = ANOMALY_SCENARIOS[scenario_name]

        if scenario_name == "brute_force":
            profile = self._pick_human_profile()
            device = self.rng.choice(profile["devices"])
            nas_ip, called_id, port_type = self.rng.choice(profile["locations"])
            for i in range(scenario["count"]):
                t = sim_time + timedelta(seconds=i * 5)  # ~55 in 5 min
                events.append(self._make_event(
                    username=profile["username"],
                    nas_ip=nas_ip,
                    calling_station_id=device,
                    called_station_id=called_id,
                    auth_result="FAIL",
                    policy_set=profile["policy_set"],
                    timestamp=t,
                    auth_type=profile["auth_type"],
                    nas_port_type=port_type,
                    anomaly_label="brute_force",
                ))

        elif scenario_name == "impossible_travel":
            profile = self._pick_human_profile()
            device = self.rng.choice(profile["devices"])
            # Two distant NAS IPs
            loc_a = ("10.0.1.1", "11:22:33:44:55:01", "Ethernet")
            loc_b = ("10.0.8.1", "11:22:33:44:55:FF", "Wireless")
            for i, loc in enumerate([loc_a, loc_b]):
                t = sim_time + timedelta(seconds=i * 60)  # 1 min apart
                events.append(self._make_event(
                    username=profile["username"],
                    nas_ip=loc[0],
                    calling_station_id=device,
                    called_station_id=loc[1],
                    auth_result="PASS",
                    policy_set=profile["policy_set"],
                    timestamp=t,
                    auth_type=profile["auth_type"],
                    nas_port_type=loc[2],
                    anomaly_label="impossible_travel",
                ))

        elif scenario_name == "new_device":
            profile = self._pick_human_profile()
            nas_ip, called_id, port_type = self.rng.choice(profile["locations"])
            events.append(self._make_event(
                username=profile["username"],
                nas_ip=nas_ip,
                calling_station_id=self._random_mac(),
                called_station_id=called_id,
                auth_result="PASS",
                policy_set=profile["policy_set"],
                timestamp=sim_time,
                auth_type=profile["auth_type"],
                nas_port_type=port_type,
                anomaly_label="new_device",
            ))

        elif scenario_name == "off_hours":
            profile = self._pick_human_profile()
            # Force 3am on a workday
            off_time = sim_time.replace(hour=3, minute=self.rng.randint(0, 59))
            device = self.rng.choice(profile["devices"])
            nas_ip, called_id, port_type = self.rng.choice(profile["locations"])
            events.append(self._make_event(
                username=profile["username"],
                nas_ip=nas_ip,
                calling_station_id=device,
                called_station_id=called_id,
                auth_result="PASS",
                policy_set=profile["policy_set"],
                timestamp=off_time,
                auth_type=profile["auth_type"],
                nas_port_type=port_type,
                anomaly_label="off_hours",
            ))

        elif scenario_name == "credential_stuffing":
            # Same device, many different usernames
            attacker_mac = self._random_mac()
            nas_ip, called_id, port_type = self.rng.choice(
                self._pick_human_profile()["locations"]
            )
            humans = [p for p in self.profiles if not p["username"].startswith("bot_")]
            targets = self.rng.sample(humans, min(scenario["count"], len(humans)))
            for i, target in enumerate(targets):
                t = sim_time + timedelta(seconds=i * 3)
                events.append(self._make_event(
                    username=target["username"],
                    nas_ip=nas_ip,
                    calling_station_id=attacker_mac,
                    called_station_id=called_id,
                    auth_result="FAIL",
                    policy_set=target["policy_set"],
                    timestamp=t,
                    auth_type="802.1X",
                    nas_port_type=port_type,
                    anomaly_label="credential_stuffing",
                ))

        elif scenario_name == "compromised_svc":
            profile = self._pick_svc_profile()
            # Service account from unexpected NAS IP
            rogue_nas = "10.0.9.99"
            rogue_called = "11:22:33:44:55:FE"
            device = profile["devices"][0]
            for i in range(scenario["count"]):
                t = sim_time + timedelta(minutes=i * 10)
                events.append(self._make_event(
                    username=profile["username"],
                    nas_ip=rogue_nas,
                    calling_station_id=device,
                    called_station_id=rogue_called,
                    auth_result="PASS",
                    policy_set=profile["policy_set"],
                    timestamp=t,
                    auth_type=profile["auth_type"],
                    nas_port_type="Ethernet",
                    anomaly_label="compromised_svc",
                ))

        return events

    def generate_stream(
        self,
        duration_days: int,
        start_time: datetime | None = None,
    ) -> Generator[tuple[dict, bool, str | None], None, None]:
        """Yield (event, is_anomaly, scenario_name) tuples in chronological order.

        Iterates through simulated time, generating events for all users
        based on their profiles. Injects anomalies at anomaly_probability rate.
        """
        if start_time is None:
            start_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(days=duration_days)

        # Pre-schedule all normal events for all profiles
        scheduled: list[tuple[datetime, dict, bool, str | None]] = []

        for profile in self.profiles:
            t = start_time
            while t < end_time:
                weekday = t.weekday()
                start_h, end_h = profile["work_hours"]

                if weekday in profile["work_days"] and end_h > start_h:
                    active_hours = end_h - start_h
                    n_events = max(
                        1,
                        int(self.rng.gauss(
                            profile["avg_auths_per_day"],
                            profile["avg_auths_per_day"] * 0.2,
                        )),
                    )
                    for _ in range(n_events):
                        hour = self.rng.uniform(start_h, end_h)
                        minute = self.rng.uniform(0, 60)
                        event_time = t.replace(
                            hour=int(hour) % 24,
                            minute=int(minute) % 60,
                            second=self.rng.randint(0, 59),
                            microsecond=0,
                        )
                        if start_time <= event_time < end_time:
                            event = self.generate_normal_event(profile, event_time)
                            scheduled.append((event_time, event, False, None))
                elif profile["work_hours"] == (0, 24):
                    # Service accounts: spread events evenly across the day
                    interval_minutes = max(1, 1440 // profile["avg_auths_per_day"])
                    current = t
                    day_end = t + timedelta(days=1)
                    while current < day_end and current < end_time:
                        jitter = self.rng.randint(0, max(1, interval_minutes // 4))
                        event_time = current + timedelta(minutes=jitter)
                        if start_time <= event_time < end_time:
                            event = self.generate_normal_event(profile, event_time)
                            scheduled.append((event_time, event, False, None))
                        current += timedelta(minutes=interval_minutes)

                # Advance to next day
                t += timedelta(days=1)
                t = t.replace(hour=0, minute=0, second=0, microsecond=0)

        # Inject anomalies into the timeline
        total_normal = len(scheduled)
        n_anomalies = int(total_normal * self.anomaly_probability)
        scenario_names = list(ANOMALY_SCENARIOS.keys())

        for _ in range(n_anomalies):
            scenario_name = self.rng.choice(scenario_names)
            # Pick a random time within the simulation window
            offset_seconds = self.rng.uniform(0, duration_days * 86400)
            anomaly_time = start_time + timedelta(seconds=offset_seconds)
            anomaly_events = self.generate_anomaly_events(scenario_name, anomaly_time)
            for ev in anomaly_events:
                ev_time = datetime.strptime(ev["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                ev_time = ev_time.replace(tzinfo=timezone.utc)
                scheduled.append((ev_time, ev, True, scenario_name))

        # Sort chronologically and yield
        scheduled.sort(key=lambda x: x[0])

        for _, event, is_anomaly, scenario_name in scheduled:
            yield event, is_anomaly, scenario_name


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _list_info() -> None:
    """Print user profiles and anomaly scenarios."""
    print("User Profiles:")
    print(f"  {'Username':<16} {'Display Name':<24} {'Hours':<12} {'Devices':<4} "
          f"{'Locations':<4} {'Auth/Day':<10} {'Policy'}")
    print(f"  {'-' * 100}")
    for p in USER_PROFILES:
        h_start, h_end = p["work_hours"]
        hours_str = f"{h_start:02d}:00-{h_end:02d}:00" if h_end <= 24 else "24/7"
        days = "".join(
            "MTWTFSS"[d] for d in sorted(p["work_days"])
        )
        print(
            f"  {p['username']:<16} {p['display_name']:<24} "
            f"{hours_str} {days:<5} {len(p['devices']):<4} "
            f"{len(p['locations']):<4} {p['avg_auths_per_day']:<10} "
            f"{p['policy_set']}"
        )

    print(f"\nAnomaly Scenarios ({len(ANOMALY_SCENARIOS)}):")
    print(f"  {'Name':<24} {'DFP Signal':<36} Description")
    print(f"  {'-' * 100}")
    for name, s in ANOMALY_SCENARIOS.items():
        print(f"  {name:<24} {s['dfp_signal']:<36} {s['description']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SASP ISE Auth Generator — synthetic ISE events for DFP training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run --duration-days 1
  %(prog)s --duration-days 30 --rate 50 --seed 42
  %(prog)s --list
        """,
    )
    parser.add_argument(
        "--duration-days",
        type=int,
        default=30,
        help="Days of activity to simulate (default: 30)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="Max events per second to Kafka (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print events to stdout instead of producing to Kafka",
    )
    parser.add_argument(
        "--bootstrap",
        default="<S2_IP>:9092",
        help="Kafka bootstrap servers (default: <S2_IP>:9092)",
    )
    parser.add_argument(
        "--topic",
        default="ise-raw",
        help="Output Kafka topic (default: ise-raw)",
    )
    parser.add_argument(
        "--anomaly-rate",
        type=float,
        default=0.02,
        help="Fraction of events that are anomalous (default: 0.02)",
    )
    parser.add_argument(
        "--real-ise-format",
        action="store_true",
        help="Emit events using real ISE syslog field names (to test normalization)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSONL output to file instead of stdout (only with --dry-run)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_info",
        help="List user profiles and anomaly scenarios, then exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the ISE auth generator."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args(argv)

    if args.list_info:
        _list_info()
        return

    generator = ISEAuthGenerator(seed=args.seed, anomaly_probability=args.anomaly_rate)
    interval = 1.0 / args.rate if args.rate > 0 else 0.1

    # Open output file if specified (only meaningful with --dry-run)
    output_fh = None
    if args.output and args.dry_run:
        output_fh = open(args.output, "w")

    # Banner → stderr so stdout stays clean for JSONL redirect
    _info = sys.stderr if args.dry_run else sys.stdout
    print(f"{'=' * 60}", file=_info)
    print("SASP ISE Auth Generator", file=_info)
    print(f"  Duration:      {args.duration_days} days", file=_info)
    print(f"  Anomaly rate:  {args.anomaly_rate:.1%}", file=_info)
    print(f"  Seed:          {args.seed}", file=_info)
    print(f"  Rate limit:    {args.rate} evt/s", file=_info)
    print(f"  Topic:         {args.topic}", file=_info)
    print(f"  Dry run:       {args.dry_run}", file=_info)
    print(f"  Real ISE fmt:  {args.real_ise_format}", file=_info)
    print(f"{'=' * 60}", file=_info)

    # Create Kafka producer (unless dry-run)
    producer = None
    if not args.dry_run:
        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=args.bootstrap.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )

    total = 0
    anomaly_count = 0
    scenario_counts: dict[str, int] = {}

    for event, is_anomaly, scenario_name in generator.generate_stream(args.duration_days):
        if args.real_ise_format:
            event = ISEAuthGenerator._to_real_ise_format(event)
        if args.dry_run:
            # Compact JSONL — one JSON object per line, suitable for piping
            line = json.dumps(event)
            if output_fh is not None:
                output_fh.write(line + "\n")
            else:
                print(line)
        elif producer is not None:
            producer.send(args.topic, value=event)

        total += 1
        if is_anomaly and scenario_name:
            anomaly_count += 1
            scenario_counts[scenario_name] = scenario_counts.get(scenario_name, 0) + 1

        # Rate limiting
        if not args.dry_run and total % 100 == 0:
            time.sleep(interval * 100)

        if total % 5000 == 0:
            logger.info("Produced %d events (%d anomalies)...", total, anomaly_count)

    if output_fh is not None:
        output_fh.close()
    if producer is not None:
        producer.flush()
        producer.close()

    action = "printed" if args.dry_run else "sent"
    _info = sys.stderr if args.dry_run else sys.stdout
    print(f"\nTotal events {action}: {total}", file=_info)
    print(f"  Normal:    {total - anomaly_count}", file=_info)
    print(f"  Anomalous: {anomaly_count}", file=_info)
    if scenario_counts:
        print("  Breakdown:", file=_info)
        for name, count in sorted(scenario_counts.items()):
            print(f"    {name}: {count}", file=_info)


if __name__ == "__main__":
    main()
