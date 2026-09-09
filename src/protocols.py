"""Preference collection and causal induction protocols."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

import numpy as np

from envs.point_mass import PointMassEnv
from reward_model import EnsembleRewardModel, PreferenceBuffer


class Protocol(str, Enum):
    ORACLE = "oracle"
    DECAY = "decay"
    OVEROPT = "overopt"
    SHARED_BLINDSPOT = "shared_blindspot"


@dataclass
class ProtocolConfig:
    protocol: Protocol = Protocol.ORACLE
    segment_len: int = 10
    n_pref_pairs: int = 200
    mistake_eps: float = 0.0
    restrict_support: bool = False
    teacher: str = "star"  # star | wrong
    shared_init_ensemble: bool = False
    freeze_after_prefs: bool = True
    max_feedback: int = 200


def segment_return(rewards: List[float]) -> float:
    return float(sum(rewards))


def collect_segment(
    env: PointMassEnv,
    policy_fn: Callable[[np.ndarray], np.ndarray],
    segment_len: int,
    force_in_support: bool = False,
) -> Tuple[np.ndarray, List[float], List[float], dict]:
    """Roll a short segment; returns sa[T, obs+act], r_star list, r_wrong list."""
    obs = env.reset()
    if force_in_support:
        # Reject starts outside support box
        for _ in range(50):
            if env.in_preference_support(obs):
                break
            obs = env.reset()
    sas = []
    r_stars = []
    r_wrongs = []
    hack = 0
    ood = 0
    for _ in range(segment_len):
        action = policy_fn(obs)
        next_obs, r_star, done, info = env.step(action)
        sa = np.concatenate([obs, action], axis=-1)
        sas.append(sa)
        r_stars.append(info["r_star"])
        r_wrongs.append(info["r_wrong"])
        hack += int(info["on_hack_manifold"])
        ood += int(not info["in_preference_support"])
        obs = next_obs
        if done:
            break
    stats = {"hack_frac": hack / max(len(sas), 1), "ood_frac": ood / max(len(sas), 1)}
    return np.stack(sas), r_stars, r_wrongs, stats


def label_pair(
    r1: List[float],
    r2: List[float],
    mistake_eps: float,
    rng: np.random.Generator,
) -> int:
    """Return 1 if segment 2 preferred, else 0. Soft ties broken randomly."""
    s1, s2 = segment_return(r1), segment_return(r2)
    if abs(s1 - s2) < 1e-6:
        lab = int(rng.integers(0, 2))
    else:
        lab = int(s2 > s1)
    if rng.random() < mistake_eps:
        lab = 1 - lab
    return lab


def fill_preferences(
    env: PointMassEnv,
    rm: EnsembleRewardModel,
    policy_fn: Callable[[np.ndarray], np.ndarray],
    cfg: ProtocolConfig,
    rng: np.random.Generator,
    target: Optional[PreferenceBuffer] = None,
) -> PreferenceBuffer:
    buf = target if target is not None else rm.buffer
    teacher = cfg.teacher
    force = cfg.restrict_support
    for _ in range(cfg.n_pref_pairs):
        sa1, rs1, rw1, _ = collect_segment(
            env, policy_fn, cfg.segment_len, force_in_support=force
        )
        sa2, rs2, rw2, _ = collect_segment(
            env, policy_fn, cfg.segment_len, force_in_support=force
        )
        if teacher == "wrong":
            lab = label_pair(rw1, rw2, cfg.mistake_eps, rng)
        else:
            lab = label_pair(rs1, rs2, cfg.mistake_eps, rng)
        buf.add(sa1, sa2, lab)
    return buf


def build_protocol(name: str) -> ProtocolConfig:
    name = name.lower()
    if name == "oracle":
        return ProtocolConfig(
            protocol=Protocol.ORACLE,
            mistake_eps=0.0,
            restrict_support=False,
            teacher="star",
            shared_init_ensemble=False,
            n_pref_pairs=250,
        )
    if name == "decay":
        return ProtocolConfig(
            protocol=Protocol.DECAY,
            mistake_eps=0.2,
            restrict_support=True,
            teacher="star",
            shared_init_ensemble=False,
            n_pref_pairs=120,
        )
    if name == "overopt":
        return ProtocolConfig(
            protocol=Protocol.OVEROPT,
            mistake_eps=0.0,
            restrict_support=False,
            teacher="wrong",
            shared_init_ensemble=False,
            n_pref_pairs=250,
        )
    if name in ("shared_blindspot", "blindspot"):
        return ProtocolConfig(
            protocol=Protocol.SHARED_BLINDSPOT,
            mistake_eps=0.0,
            restrict_support=False,
            teacher="wrong",
            shared_init_ensemble=True,
            n_pref_pairs=250,
        )
    raise ValueError(f"Unknown protocol: {name}")
