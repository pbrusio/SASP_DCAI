"""SASP Model Evaluation Metrics — ROC-AUC, precision-recall, and adversarial robustness scoring."""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass
class CurveData:
    """Points on a ROC or PR curve."""
    x: List[float] = field(default_factory=list)  # FPR or Recall
    y: List[float] = field(default_factory=list)  # TPR or Precision
    auc: float = 0.0


@dataclass
class AdversarialTestResult:
    """Result of a single adversarial robustness test."""
    test_name: str
    passed: bool
    detection_rate: float  # fraction of adversarial samples still detected
    threshold: float  # required minimum detection rate
    details: str = ""


@dataclass
class EvaluationReport:
    """Aggregate evaluation report."""
    model_name: str
    roc_auc: float = 0.0
    pr_auc: float = 0.0
    detection_at_fpr_001: float = 0.0  # TPR at FPR=0.01
    detection_at_fpr_005: float = 0.0  # TPR at FPR=0.05
    adversarial_results: List[AdversarialTestResult] = field(default_factory=list)
    overall_pass: bool = True


# ---------------------------------------------------------------------------
# ROC-AUC
# ---------------------------------------------------------------------------
def compute_roc_curve(
    y_true: np.ndarray, y_scores: np.ndarray, n_thresholds: int = 200
) -> CurveData:
    """Compute ROC curve and AUC from binary labels and continuous scores.

    Parameters
    ----------
    y_true : array of {0, 1}
        True binary labels.
    y_scores : array of float
        Predicted scores (higher = more anomalous).
    n_thresholds : int
        Number of threshold points for the curve.

    Returns
    -------
    CurveData with x=FPR, y=TPR, auc.
    """
    thresholds = np.linspace(y_scores.min(), y_scores.max(), n_thresholds)
    fprs, tprs = [], []

    positives = y_true.sum()
    negatives = len(y_true) - positives

    if positives == 0 or negatives == 0:
        logger.warning("Degenerate labels: %d positives, %d negatives", positives, negatives)
        return CurveData(x=[0.0, 1.0], y=[0.0, 1.0], auc=0.5)

    for t in thresholds:
        predicted_positive = y_scores >= t
        tp = (predicted_positive & (y_true == 1)).sum()
        fp = (predicted_positive & (y_true == 0)).sum()
        tpr = tp / positives
        fpr = fp / negatives
        fprs.append(float(fpr))
        tprs.append(float(tpr))

    # Sort by FPR ascending
    sorted_pairs = sorted(zip(fprs, tprs))
    fprs = [p[0] for p in sorted_pairs]
    tprs = [p[1] for p in sorted_pairs]

    # Trapezoidal AUC
    auc = float(np.trapz(tprs, fprs))

    return CurveData(x=fprs, y=tprs, auc=auc)


# ---------------------------------------------------------------------------
# Precision-Recall
# ---------------------------------------------------------------------------
def compute_pr_curve(
    y_true: np.ndarray, y_scores: np.ndarray, n_thresholds: int = 200
) -> CurveData:
    """Compute Precision-Recall curve and AUC.

    Parameters
    ----------
    y_true : array of {0, 1}
    y_scores : array of float

    Returns
    -------
    CurveData with x=Recall, y=Precision, auc.
    """
    thresholds = np.linspace(y_scores.min(), y_scores.max(), n_thresholds)
    recalls, precisions = [], []

    positives = y_true.sum()
    if positives == 0:
        return CurveData(x=[0.0, 1.0], y=[1.0, 0.0], auc=0.0)

    for t in thresholds:
        predicted_positive = y_scores >= t
        tp = (predicted_positive & (y_true == 1)).sum()
        fp = (predicted_positive & (y_true == 0)).sum()
        precision = tp / max(tp + fp, 1)
        recall = tp / positives
        recalls.append(float(recall))
        precisions.append(float(precision))

    sorted_pairs = sorted(zip(recalls, precisions))
    recalls = [p[0] for p in sorted_pairs]
    precisions = [p[1] for p in sorted_pairs]

    auc = float(np.trapz(precisions, recalls))
    return CurveData(x=recalls, y=precisions, auc=auc)


# ---------------------------------------------------------------------------
# Detection at specific FPR
# ---------------------------------------------------------------------------
def detection_at_fpr(
    y_true: np.ndarray, y_scores: np.ndarray, target_fpr: float = 0.01
) -> float:
    """Find the true positive rate at a given false positive rate.

    Parameters
    ----------
    y_true : array of {0, 1}
    y_scores : array of float
    target_fpr : float
        Target false positive rate.

    Returns
    -------
    float : TPR at the closest FPR <= target_fpr.
    """
    roc = compute_roc_curve(y_true, y_scores)
    best_tpr = 0.0
    for fpr, tpr in zip(roc.x, roc.y):
        if fpr <= target_fpr:
            best_tpr = max(best_tpr, tpr)
    return best_tpr


# ---------------------------------------------------------------------------
# Adversarial robustness assessment
# ---------------------------------------------------------------------------
def assess_adversarial_robustness(
    test_results: List[AdversarialTestResult],
) -> Tuple[bool, str]:
    """Evaluate whether all adversarial tests pass.

    Parameters
    ----------
    test_results : list of AdversarialTestResult

    Returns
    -------
    (overall_pass, summary_string)
    """
    passed = all(r.passed for r in test_results)
    lines = []
    for r in test_results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"  [{status}] {r.test_name}: "
            f"detection_rate={r.detection_rate:.1%} "
            f"(threshold={r.threshold:.1%})"
        )
    summary = "\n".join(lines)
    return passed, summary


def run_perturbation_test(
    original_scores: np.ndarray,
    perturbed_scores: np.ndarray,
    threshold: float,
    min_detection_rate: float = 0.80,
    test_name: str = "perturbation",
) -> AdversarialTestResult:
    """Check that detection rate stays above minimum under perturbation.

    Parameters
    ----------
    original_scores : array
        Anomaly scores on original data.
    perturbed_scores : array
        Anomaly scores on perturbed data.
    threshold : float
        Score threshold for anomaly detection.
    min_detection_rate : float
        Required minimum fraction of samples still detected.
    test_name : str
        Name for the test result.

    Returns
    -------
    AdversarialTestResult
    """
    original_detected = (original_scores >= threshold).sum()
    perturbed_detected = (perturbed_scores >= threshold).sum()

    if original_detected == 0:
        detection_rate = 1.0
    else:
        detection_rate = perturbed_detected / original_detected

    passed = detection_rate >= min_detection_rate
    return AdversarialTestResult(
        test_name=test_name,
        passed=passed,
        detection_rate=float(detection_rate),
        threshold=min_detection_rate,
        details=f"original_detected={original_detected}, perturbed_detected={perturbed_detected}",
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_evaluation_report(
    model_name: str,
    y_true: np.ndarray,
    y_scores: np.ndarray,
    adversarial_results: Optional[List[AdversarialTestResult]] = None,
) -> EvaluationReport:
    """Generate a full evaluation report for a model.

    Parameters
    ----------
    model_name : str
    y_true : binary labels
    y_scores : anomaly scores
    adversarial_results : optional list of adversarial test results

    Returns
    -------
    EvaluationReport
    """
    roc = compute_roc_curve(y_true, y_scores)
    pr = compute_pr_curve(y_true, y_scores)
    det_001 = detection_at_fpr(y_true, y_scores, 0.01)
    det_005 = detection_at_fpr(y_true, y_scores, 0.05)

    adv_results = adversarial_results or []
    adv_pass = all(r.passed for r in adv_results) if adv_results else True

    report = EvaluationReport(
        model_name=model_name,
        roc_auc=roc.auc,
        pr_auc=pr.auc,
        detection_at_fpr_001=det_001,
        detection_at_fpr_005=det_005,
        adversarial_results=adv_results,
        overall_pass=adv_pass,
    )

    logger.info(
        "Evaluation report for %s: ROC-AUC=%.4f PR-AUC=%.4f det@FPR=0.01=%.4f pass=%s",
        model_name, roc.auc, pr.auc, det_001, adv_pass,
    )
    return report


def save_report(report: EvaluationReport, path: str) -> None:
    """Save evaluation report to a JSON file."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(asdict(report), fh, indent=2)
    logger.info("Saved evaluation report to %s", out)
