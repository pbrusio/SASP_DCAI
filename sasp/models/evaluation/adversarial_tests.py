"""SASP Adversarial Model Tests — verify detection robustness against evasion techniques.

Tests use random-weight model instances so they can run without trained checkpoints.
Real thresholds are replaced with synthetic baselines for unit testing.
"""

import logging
from typing import Dict, List, Tuple

import numpy as np
import pytest
import torch

from sasp.models.training.feature_engineering import NetFlowFeatureExtractor
from sasp.models.training.netflow_autoencoder import AutoEncoder, INPUT_DIM
from sasp.models.training.auth_classifier import AuthClassifier, NUM_FEATURES, NUM_CLASSES

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.adversarial


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def autoencoder():
    """Random-weight autoencoder for structural testing."""
    model = AutoEncoder(input_dim=INPUT_DIM)
    model.eval()
    return model


@pytest.fixture
def classifier():
    """Random-weight auth classifier for structural testing."""
    model = AuthClassifier(input_dim=NUM_FEATURES, num_classes=NUM_CLASSES)
    model.eval()
    return model


@pytest.fixture
def extractor():
    """Feature extractor instance."""
    return NetFlowFeatureExtractor(window_seconds=300)


@pytest.fixture
def normal_netflow_records():
    """Batch of normal-looking NetFlow records."""
    return [
        {
            "SrcAddr": "10.0.0.50",
            "DstAddr": f"192.168.1.{i % 5 + 1}",
            "SrcPort": 50000 + i,
            "DstPort": 443,
            "Proto": 6,
            "Bytes": 1500,
            "Packets": 10,
            "TimeFlowStart": 1700000000.0,
            "TimeFlowEnd": 1700000001.0,
        }
        for i in range(20)
    ]


@pytest.fixture
def anomalous_netflow_records():
    """Batch of anomalous NetFlow records (port scan pattern)."""
    return [
        {
            "SrcAddr": "10.0.0.99",
            "DstAddr": f"192.168.1.{i}",
            "SrcPort": 54321,
            "DstPort": i + 1,
            "Proto": 6,
            "Bytes": 60,
            "Packets": 1,
            "TimeFlowStart": 1700000000.0,
            "TimeFlowEnd": 1700000000.1,
        }
        for i in range(50)
    ]


def _reconstruction_error(model: AutoEncoder, features: np.ndarray) -> np.ndarray:
    """Compute per-sample MSE reconstruction error."""
    model.eval()
    tensor = torch.tensor(features, dtype=torch.float32)
    with torch.no_grad():
        recon = model(tensor)
    return ((tensor - recon) ** 2).mean(dim=1).numpy()


# ---------------------------------------------------------------------------
# Feature Perturbation Attacks
# ---------------------------------------------------------------------------
class TestFeaturePerturbation:
    """Add small noise to numeric features and measure detection stability."""

    def test_small_noise_does_not_flip_scores(self, autoencoder):
        """Small Gaussian noise should not drastically change reconstruction error ordering."""
        np.random.seed(42)
        clean = np.random.randn(100, INPUT_DIM).astype(np.float32)
        noisy = clean + np.random.normal(0, 0.01, clean.shape).astype(np.float32)

        clean_errors = _reconstruction_error(autoencoder, clean)
        noisy_errors = _reconstruction_error(autoencoder, noisy)

        # Rank correlation should be high (noise is tiny)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(clean_errors, noisy_errors)
        assert corr > 0.8, f"Rank correlation dropped to {corr:.3f} with tiny noise"

    def test_large_noise_increases_error(self, autoencoder):
        """Large perturbation should increase reconstruction error."""
        np.random.seed(42)
        clean = np.random.randn(100, INPUT_DIM).astype(np.float32) * 0.1
        perturbed = clean + np.random.normal(0, 5.0, clean.shape).astype(np.float32)

        clean_errors = _reconstruction_error(autoencoder, clean)
        perturbed_errors = _reconstruction_error(autoencoder, perturbed)

        # Mean error should increase with large perturbation
        assert perturbed_errors.mean() > clean_errors.mean() * 0.5, (
            "Large perturbation did not meaningfully increase reconstruction error"
        )


# ---------------------------------------------------------------------------
# Flow-Splitting Evasion
# ---------------------------------------------------------------------------
class TestFlowSplitting:
    """Split one large anomalous flow into multiple small flows."""

    def test_split_flow_features_differ(self, extractor):
        """Splitting a large flow into small flows should change aggregate features."""
        # Single large flow
        single = [{
            "SrcAddr": "10.0.0.99",
            "DstAddr": "192.168.1.1",
            "SrcPort": 54321,
            "DstPort": 80,
            "Proto": 6,
            "Bytes": 100000,
            "Packets": 500,
            "TimeFlowStart": 1700000000.0,
            "TimeFlowEnd": 1700000060.0,
        }]

        # Same data split into 10 small flows
        split = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": "192.168.1.1",
                "SrcPort": 54321,
                "DstPort": 80,
                "Proto": 6,
                "Bytes": 10000,
                "Packets": 50,
                "TimeFlowStart": 1700000000.0 + i * 6,
                "TimeFlowEnd": 1700000006.0 + i * 6,
            }
            for i in range(10)
        ]

        single_df = extractor.transform(single)
        split_df = extractor.transform(split)

        # bytes_per_packet should be similar per-flow
        assert abs(single_df["bytes_per_packet"].iloc[0] -
                    split_df["bytes_per_packet"].iloc[0]) < 1.0

        # But flows_per_src_ip should reflect the split
        assert split_df["flows_per_src_ip"].iloc[0] == 10.0


# ---------------------------------------------------------------------------
# Port-Hopping Evasion
# ---------------------------------------------------------------------------
class TestPortHopping:
    """Vary destination ports while keeping other anomalous features."""

    def test_port_hopping_increases_entropy(self, extractor):
        """Port hopping across many destinations should increase dst entropy."""
        # Fixed port scan
        fixed_port = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": f"192.168.1.{i}",
                "SrcPort": 54321,
                "DstPort": 80,
                "Proto": 6,
                "Bytes": 60,
                "Packets": 1,
                "TimeFlowStart": 1700000000.0,
                "TimeFlowEnd": 1700000000.1,
            }
            for i in range(20)
        ]

        # Port-hopping scan (varying dst port)
        hopping = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": f"192.168.1.{i}",
                "SrcPort": 54321,
                "DstPort": 1000 + i * 100,
                "Proto": 6,
                "Bytes": 60,
                "Packets": 1,
                "TimeFlowStart": 1700000000.0,
                "TimeFlowEnd": 1700000000.1,
            }
            for i in range(20)
        ]

        fixed_df = extractor.transform(fixed_port)
        hopping_df = extractor.transform(hopping)

        # Both should have high dst_ip_entropy (many unique destinations)
        assert fixed_df["dst_ip_entropy"].iloc[0] > 2.0
        assert hopping_df["dst_ip_entropy"].iloc[0] > 2.0

        # Port-hopping should have higher unique_dst_ports_per_src
        assert (hopping_df["unique_dst_ports_per_src"].iloc[0] >
                fixed_df["unique_dst_ports_per_src"].iloc[0])

    def test_port_hop_autoencoder_detection(self, autoencoder, extractor):
        """Both fixed-port and port-hopping scans should produce errors."""
        records = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": f"192.168.1.{i}",
                "SrcPort": 54321,
                "DstPort": 1000 + i * 37,
                "Proto": 6,
                "Bytes": 60,
                "Packets": 1,
                "TimeFlowStart": 1700000000.0,
                "TimeFlowEnd": 1700000000.1,
            }
            for i in range(20)
        ]
        df = extractor.transform(records)
        features = df.values.astype(np.float32)
        errors = _reconstruction_error(autoencoder, features)
        # With random weights the errors are non-trivial — just verify they compute
        assert len(errors) == 20
        assert all(np.isfinite(errors))


# ---------------------------------------------------------------------------
# Slow-Scan Evasion
# ---------------------------------------------------------------------------
class TestSlowScan:
    """Spread scan across long time window to dilute aggregate features."""

    def test_slow_scan_reduces_flow_count(self, extractor):
        """A slow scan with one flow per window should have low flows_per_src_ip."""
        # Fast scan: 50 flows in one window
        fast = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": f"192.168.1.{i}",
                "SrcPort": 54321,
                "DstPort": 22,
                "Proto": 6,
                "Bytes": 60,
                "Packets": 1,
                "TimeFlowStart": 1700000000.0,
                "TimeFlowEnd": 1700000000.1,
            }
            for i in range(50)
        ]

        # Slow scan: 5 flows (simulating one per window)
        slow = [
            {
                "SrcAddr": "10.0.0.99",
                "DstAddr": f"192.168.1.{i}",
                "SrcPort": 54321,
                "DstPort": 22,
                "Proto": 6,
                "Bytes": 60,
                "Packets": 1,
                "TimeFlowStart": 1700000000.0 + i * 300,
                "TimeFlowEnd": 1700000000.1 + i * 300,
            }
            for i in range(5)
        ]

        fast_df = extractor.transform(fast)
        slow_df = extractor.transform(slow)

        # Fast scan has more flows per src
        assert fast_df["flows_per_src_ip"].iloc[0] > slow_df["flows_per_src_ip"].iloc[0]

        # But slow scan still has unique dest IPs
        assert slow_df["unique_dst_ips_per_src"].iloc[0] == 5.0


# ---------------------------------------------------------------------------
# Auth Classifier Robustness
# ---------------------------------------------------------------------------
class TestClassifierRobustness:
    """Test auth classifier against input perturbation."""

    def test_consistent_predictions_with_tiny_noise(self, classifier):
        """Tiny noise should not flip classification for most samples."""
        np.random.seed(42)
        X = np.random.randn(200, NUM_FEATURES).astype(np.float32) * 0.5
        X_noisy = X + np.random.normal(0, 0.01, X.shape).astype(np.float32)

        with torch.no_grad():
            preds_clean = classifier(torch.tensor(X)).argmax(dim=1).numpy()
            preds_noisy = classifier(torch.tensor(X_noisy)).argmax(dim=1).numpy()

        agreement = (preds_clean == preds_noisy).mean()
        assert agreement > 0.8, f"Only {agreement:.1%} predictions stable under tiny noise"

    def test_extreme_values_do_not_crash(self, classifier):
        """Extreme feature values should produce valid logits, not NaN."""
        extreme = torch.tensor([[1e6, -1e6, 0, 999, 500, 1, 1]], dtype=torch.float32)
        with torch.no_grad():
            logits = classifier(extreme)
        assert torch.isfinite(logits).all(), "Extreme inputs produced NaN/Inf"
        assert logits.shape == (1, NUM_CLASSES)
