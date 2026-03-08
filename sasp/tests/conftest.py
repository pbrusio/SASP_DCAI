"""Shared pytest fixtures for the SASP test suite."""

import pytest


@pytest.fixture
def sample_detection():
    """Minimal Morpheus detection event for testing."""
    return {
        "timestamp": "2025-01-01T00:00:00Z",
        "source_ip": "10.0.0.50",
        "dest_ip": "192.168.1.100",
        "anomaly_score": 0.92,
        "model": "autoencoder-netflow-v1",
        "raw_event": {"bytes_in": 500000, "bytes_out": 10},
    }


@pytest.fixture
def sample_netflow_record():
    """Valid GoFlow2 NetFlow record for testing."""
    return {
        "type": 5,
        "sampler_address": "10.0.0.1",
        "src_addr": "192.168.1.100",
        "dst_addr": "10.0.0.50",
        "src_port": 54321,
        "dst_port": 443,
        "proto": 6,
        "bytes": 1500,
        "packets": 10,
        "time_flow_start_ns": 1700000000000000000,
        "time_flow_end_ns": 1700000001000000000,
    }


@pytest.fixture
def sample_syslog_record():
    """Valid syslog record for testing."""
    return {
        "timestamp": "2026-02-28T12:00:00Z",
        "hostname": "router-01",
        "facility": 1,
        "severity": 6,
        "message": "Interface GigabitEthernet0/1 changed state to up",
    }


@pytest.fixture
def sample_ise_record():
    """Valid ISE RADIUS auth record for testing."""
    return {
        "username": "jsmith",
        "nas_ip": "10.0.0.1",
        "calling_station_id": "AA:BB:CC:DD:EE:FF",
        "called_station_id": "11:22:33:44:55:66",
        "auth_result": "PASS",
        "policy_set": "Corporate-Wired",
    }
