"""Diagnostic feature extraction for Decay vs Overopt classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np


@dataclass
class DiagnosticFeatures:
    ensemble_disagreement: float
    support_novelty: float
    heldout_acc: float
    onpolicy_acc: float
    fixed_ref_acc: float
    action_entropy: float
    kl_to_init: float
    proxy_return: float
    true_return: float
    hack_mass: float
    ood_mass: float
    symptom: bool
    protocol_label: str  # ground truth for evaluation only

    def classifier_vector(self) -> np.ndarray:
        """Features allowed at test time (no hack_mass / protocol)."""
        return np.array(
            [
                self.ensemble_disagreement,
                self.support_novelty,
                self.heldout_acc,
                self.onpolicy_acc,
                self.fixed_ref_acc,
                self.action_entropy,
                self.kl_to_init,
            ],
            dtype=np.float64,
        )

    def to_dict(self) -> Dict:
        return asdict(self)


def knn_novelty(query: np.ndarray, support: np.ndarray, k: int = 5) -> float:
    """Mean kNN distance from query points to preference support points."""
    if support.shape[0] == 0 or query.shape[0] == 0:
        return float("nan")
    # Use position+velocity+action dims present in both
    d = min(query.shape[1], support.shape[1])
    q = query[:, :d]
    s = support[:, :d]
    # subsample for speed
    if q.shape[0] > 256:
        idx = np.random.choice(q.shape[0], 256, replace=False)
        q = q[idx]
    if s.shape[0] > 2048:
        idx = np.random.choice(s.shape[0], 2048, replace=False)
        s = s[idx]
    # distances
    # (n_q, n_s)
    dists = np.linalg.norm(q[:, None, :] - s[None, :, :], axis=-1)
    kk = min(k, s.shape[0])
    knn = np.partition(dists, kk - 1, axis=1)[:, :kk].mean(axis=1)
    return float(knn.mean())


def symptom_from_series(
    proxy: np.ndarray, true: np.ndarray, delta: float = 5.0
) -> bool:
    """Early vs late half: proxy up, true down."""
    if len(proxy) < 4:
        return False
    mid = len(proxy) // 2
    d_proxy = float(proxy[mid:].mean() - proxy[:mid].mean())
    d_true = float(true[mid:].mean() - true[:mid].mean())
    return d_proxy > delta and d_true < -delta


def soft_symptom(proxy: np.ndarray, true: np.ndarray) -> bool:
    """Relative variant for synthetic scale."""
    if len(proxy) < 4:
        return False
    mid = len(proxy) // 2
    d_proxy = float(proxy[mid:].mean() - proxy[:mid].mean())
    d_true = float(true[mid:].mean() - true[:mid].mean())
    return d_proxy > 1.0 and d_true < -1.0
