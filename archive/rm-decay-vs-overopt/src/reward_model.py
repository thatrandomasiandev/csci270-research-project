"""Ensemble preference reward model + preference buffer."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class RewardNet(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim + action_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, sa: torch.Tensor) -> torch.Tensor:
        return self.net(sa)


class PreferenceBuffer:
    def __init__(self):
        self.sa_1: List[np.ndarray] = []
        self.sa_2: List[np.ndarray] = []
        self.labels: List[int] = []  # 0 => seg1 preferred, 1 => seg2

    def add(self, sa_1: np.ndarray, sa_2: np.ndarray, label: int):
        self.sa_1.append(sa_1.astype(np.float32))
        self.sa_2.append(sa_2.astype(np.float32))
        self.labels.append(int(label))

    def __len__(self):
        return len(self.labels)

    def as_arrays(self):
        return (
            np.stack(self.sa_1),
            np.stack(self.sa_2),
            np.asarray(self.labels, dtype=np.int64),
        )

    def support_states(self) -> np.ndarray:
        """Flatten segment midpoints (mean over time) for novelty kNN."""
        if not self.sa_1:
            return np.zeros((0, 1), dtype=np.float32)
        pts = []
        for a, b in zip(self.sa_1, self.sa_2):
            pts.append(a.mean(axis=0))
            pts.append(b.mean(axis=0))
        return np.stack(pts).astype(np.float32)


class EnsembleRewardModel:
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        ensemble_size: int = 3,
        hidden: int = 64,
        lr: float = 1e-3,
        device: str = "cpu",
        shared_init: bool = False,
    ):
        self.device = torch.device(device)
        self.de = ensemble_size
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.models = nn.ModuleList(
            [RewardNet(obs_dim, action_dim, hidden) for _ in range(ensemble_size)]
        ).to(self.device)
        if shared_init:
            # Shared blind-spot control: identical initialization
            ref = self.models[0].state_dict()
            for m in self.models[1:]:
                m.load_state_dict(ref)
        self.optims = [
            torch.optim.Adam(m.parameters(), lr=lr) for m in self.models
        ]
        self.buffer = PreferenceBuffer()
        self.heldout = PreferenceBuffer()
        self.fixed_ref = PreferenceBuffer()

    def _seg_return(self, model: RewardNet, sa: torch.Tensor) -> torch.Tensor:
        # sa: [B, T, obs+act]
        b, t, d = sa.shape
        r = model(sa.reshape(b * t, d)).reshape(b, t)
        return r.sum(dim=1)

    def train_on_buffer(
        self,
        buffer: Optional[PreferenceBuffer] = None,
        epochs: int = 50,
        batch_size: int = 64,
    ) -> float:
        buf = buffer or self.buffer
        if len(buf) < 4:
            return float("nan")
        sa1, sa2, y = buf.as_arrays()
        n = len(y)
        accs = []
        for epoch in range(epochs):
            idx = np.random.permutation(n)
            correct = 0
            total = 0
            for start in range(0, n, batch_size):
                bi = idx[start : start + batch_size]
                x1 = torch.as_tensor(sa1[bi], device=self.device)
                x2 = torch.as_tensor(sa2[bi], device=self.device)
                labels = torch.as_tensor(y[bi], device=self.device)
                for member, optim in zip(self.models, self.optims):
                    r1 = self._seg_return(member, x1)
                    r2 = self._seg_return(member, x2)
                    logits = r2 - r1  # P(prefer 2)
                    loss = F.binary_cross_entropy_with_logits(
                        logits, labels.float()
                    )
                    optim.zero_grad()
                    loss.backward()
                    optim.step()
                    with torch.no_grad():
                        pred = (torch.sigmoid(logits) > 0.5).long()
                        correct += (pred == labels).sum().item()
                        total += len(labels)
            accs.append(correct / max(total, 1))
        return float(np.mean(accs[-5:])) if accs else float("nan")

    @torch.no_grad()
    def predict_reward(self, obs: np.ndarray, action: np.ndarray) -> Tuple[float, float]:
        sa = np.concatenate([obs, action], axis=-1).astype(np.float32)
        x = torch.as_tensor(sa[None], device=self.device)
        preds = torch.stack([m(x).squeeze() for m in self.models])
        return float(preds.mean().item()), float(preds.var(unbiased=False).item())

    @torch.no_grad()
    def batch_rewards(self, obs: np.ndarray, actions: np.ndarray):
        sa = np.concatenate([obs, actions], axis=-1).astype(np.float32)
        x = torch.as_tensor(sa, device=self.device)
        preds = torch.stack([m(x).squeeze(-1) for m in self.models], dim=0)
        mean = preds.mean(0).cpu().numpy()
        var = preds.var(0, unbiased=False).cpu().numpy()
        return mean, var

    @torch.no_grad()
    def preference_accuracy(self, buffer: PreferenceBuffer) -> float:
        if len(buffer) == 0:
            return float("nan")
        sa1, sa2, y = buffer.as_arrays()
        x1 = torch.as_tensor(sa1, device=self.device)
        x2 = torch.as_tensor(sa2, device=self.device)
        labels = torch.as_tensor(y, device=self.device)
        votes = []
        for m in self.models:
            r1 = self._seg_return(m, x1)
            r2 = self._seg_return(m, x2)
            votes.append((r2 > r1).long())
        pred = torch.stack(votes).float().mean(0) > 0.5
        return float((pred.long() == labels).float().mean().item())
