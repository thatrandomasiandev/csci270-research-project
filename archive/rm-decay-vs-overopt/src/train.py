"""Main training loop: frozen-proxy SAC under causal induction protocols."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diagnostics import DiagnosticFeatures, knn_novelty, soft_symptom
from envs.point_mass import PointMassConfig, PointMassEnv, make_env
from protocols import Protocol, build_protocol, fill_preferences
from reward_model import EnsembleRewardModel
from sac import ReplayBuffer, SAC


def random_policy(env: PointMassEnv):
    low, high = env.action_range

    def _fn(_obs):
        return env.rng.uniform(low, high, size=env.action_dim)

    return _fn


def run_experiment(args) -> Dict:
    rng = np.random.default_rng(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = build_protocol(args.protocol)
    # Resolve proxy source for airtight overopt induction
    if args.proxy_source == "auto":
        if cfg.protocol in (Protocol.OVEROPT, Protocol.SHARED_BLINDSPOT):
            args.proxy_source = "wrong"
        else:
            args.proxy_source = "rm"
    # Mitigation overrides
    if args.more_prefs:
        cfg.n_pref_pairs = int(cfg.n_pref_pairs * 2.5)
        cfg.mistake_eps = 0.0 if args.protocol == "decay" else cfg.mistake_eps
        cfg.restrict_support = False if args.protocol == "decay" else cfg.restrict_support

    env = make_env(args.env, seed=args.seed)
    device = args.device
    rm = EnsembleRewardModel(
        env.obs_dim,
        env.action_dim,
        ensemble_size=args.ensemble_size,
        device=device,
        shared_init=cfg.shared_init_ensemble or args.shared_init,
    )
    agent = SAC(
        env.obs_dim,
        env.action_dim,
        device=device,
        uncertainty_penalty=args.uncertainty_penalty,
        kl_coef=args.kl_coef,
    )
    replay = ReplayBuffer(env.obs_dim, env.action_dim)

    # --- Preference phase (behavioral policy ≈ random / exploratory) ---
    fill_preferences(env, rm, random_policy(env), cfg, rng, target=rm.buffer)

    # Held-out split
    n = len(rm.buffer)
    idx = rng.permutation(n)
    split = max(1, int(0.2 * n))
    for i in idx[:split]:
        rm.heldout.add(rm.buffer.sa_1[i], rm.buffer.sa_2[i], rm.buffer.labels[i])
    # Rebuild train buffer without heldout
    train_sa1 = [rm.buffer.sa_1[i] for i in idx[split:]]
    train_sa2 = [rm.buffer.sa_2[i] for i in idx[split:]]
    train_y = [rm.buffer.labels[i] for i in idx[split:]]
    rm.buffer.sa_1, rm.buffer.sa_2, rm.buffer.labels = train_sa1, train_sa2, train_y

    # Fixed reference from early (oracle-labeled) probes on support
    from protocols import ProtocolConfig, collect_segment, label_pair

    ref_cfg = ProtocolConfig(
        n_pref_pairs=64,
        segment_len=cfg.segment_len,
        mistake_eps=0.0,
        restrict_support=True,
        teacher="star",
    )
    fill_preferences(env, rm, random_policy(env), ref_cfg, rng, target=rm.fixed_ref)

    train_acc = rm.train_on_buffer(rm.buffer, epochs=args.rm_epochs)
    heldout_acc = rm.preference_accuracy(rm.heldout)
    fixed_ref_acc = rm.preference_accuracy(rm.fixed_ref)

    agent.snapshot_init_policy()

    # --- Frozen RM RL phase ---
    window_rows = []
    proxy_series = []
    true_series = []
    feature_snapshots: List[DiagnosticFeatures] = []

    obs = env.reset()
    ep_proxy, ep_true = 0.0, 0.0
    ep_hack, ep_ood, ep_steps = 0, 0, 0
    ep_obs = []
    updates_per_step = args.updates_per_step

    for step in range(1, args.num_steps + 1):
        if step < args.warmup:
            action = env.rng.uniform(*env.action_range, size=env.action_dim)
        else:
            action = agent.act(obs)

        next_obs, r_star, done, info = env.step(action)
        if args.proxy_source == "wrong":
            proxy_r = float(info["r_wrong"])
            # disagreement still from ensemble for diagnostics
            _, unc = rm.predict_reward(obs, action)
        elif args.proxy_source == "star":
            proxy_r = float(info["r_star"])
            _, unc = rm.predict_reward(obs, action)
        else:
            proxy_r, unc = rm.predict_reward(obs, action)

        # Train on proxy (frozen)
        replay.add(obs, action, proxy_r, next_obs, done)
        if args.uncertainty_penalty > 0:
            # store unc via rewriting last reward already set; handled in update batch
            pass

        ep_proxy += proxy_r
        ep_true += info["r_star"]
        ep_hack += int(info["on_hack_manifold"])
        ep_ood += int(not info["in_preference_support"])
        ep_steps += 1
        ep_obs.append(obs)

        obs = next_obs
        if step >= args.warmup and replay.size >= args.batch_size:
            for _ in range(updates_per_step):
                batch = replay.sample(args.batch_size, agent.device)
                unc_t = None
                if args.uncertainty_penalty > 0:
                    o, a, _, _, _ = batch
                    with torch.no_grad():
                        sa = torch.cat([o, a], dim=-1)
                        preds = torch.stack(
                            [m(sa).squeeze(-1) for m in rm.models], dim=0
                        )
                        unc_t = preds.var(0, unbiased=False).unsqueeze(-1)
                agent.update(batch, uncertainty=unc_t)

        if done:
            proxy_series.append(ep_proxy)
            true_series.append(ep_true)
            row = {
                "step": step,
                "proxy_return": ep_proxy,
                "true_return": ep_true,
                "hack_frac": ep_hack / max(ep_steps, 1),
                "ood_frac": ep_ood / max(ep_steps, 1),
            }
            window_rows.append(row)

            # Periodic diagnostic snapshot (every N episodes) after warmup
            ep_count = len(proxy_series)
            if (
                step >= args.warmup
                and len(ep_obs) > 0
                and ep_count % args.diag_every == 0
            ):
                obs_batch = np.stack(ep_obs)
                # sample actions from current policy for disagreement on on-policy states
                acts = np.stack([agent.act(o) for o in obs_batch])
                means, vars_ = rm.batch_rewards(obs_batch, acts)
                support = rm.buffer.support_states()
                sa_query = np.concatenate([obs_batch, acts], axis=-1)
                novelty = knn_novelty(sa_query, support, k=5)
                ent, kl = agent.policy_stats(obs_batch)

                # On-policy preference accuracy with oracle labels
                from reward_model import PreferenceBuffer
                from protocols import collect_segment, label_pair

                onbuf = PreferenceBuffer()
                pol = lambda o: agent.act(o)
                for _ in range(args.onpolicy_pairs):
                    sa1, rs1, _, _ = collect_segment(env, pol, cfg.segment_len)
                    sa2, rs2, _, _ = collect_segment(env, pol, cfg.segment_len)
                    onbuf.add(sa1, sa2, label_pair(rs1, rs2, 0.0, rng))
                on_acc = rm.preference_accuracy(onbuf)

                feats = DiagnosticFeatures(
                    ensemble_disagreement=float(np.mean(vars_)),
                    support_novelty=float(novelty),
                    heldout_acc=float(heldout_acc),
                    onpolicy_acc=float(on_acc),
                    fixed_ref_acc=float(fixed_ref_acc),
                    action_entropy=float(ent),
                    kl_to_init=float(kl),
                    proxy_return=float(ep_proxy),
                    true_return=float(ep_true),
                    hack_mass=float(ep_hack / max(ep_steps, 1)),
                    ood_mass=float(ep_ood / max(ep_steps, 1)),
                    symptom=False,
                    protocol_label=cfg.protocol.value,
                )
                feature_snapshots.append(feats)

            obs = env.reset()
            ep_proxy = ep_true = 0.0
            ep_hack = ep_ood = ep_steps = 0
            ep_obs = []

    # Final symptom on last window of episodes
    symptom = soft_symptom(np.array(proxy_series), np.array(true_series))
    if feature_snapshots:
        # Mark late snapshots
        mid = len(feature_snapshots) // 2
        for i, f in enumerate(feature_snapshots):
            if i >= mid:
                f.symptom = symptom

    # Aggregate late features
    late = feature_snapshots[len(feature_snapshots) // 2 :] or feature_snapshots
    def mean_field(name):
        vals = [getattr(f, name) for f in late]
        vals = [v for v in vals if v == v]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {
        "protocol": cfg.protocol.value,
        "env": args.env,
        "seed": args.seed,
        "train_acc": train_acc,
        "heldout_acc": heldout_acc,
        "fixed_ref_acc": fixed_ref_acc,
        "final_proxy_mean20": float(np.mean(proxy_series[-20:])) if proxy_series else None,
        "final_true_mean20": float(np.mean(true_series[-20:])) if true_series else None,
        "symptom": symptom,
        "ensemble_disagreement": mean_field("ensemble_disagreement"),
        "support_novelty": mean_field("support_novelty"),
        "onpolicy_acc": mean_field("onpolicy_acc"),
        "action_entropy": mean_field("action_entropy"),
        "kl_to_init": mean_field("kl_to_init"),
        "hack_mass": mean_field("hack_mass"),
        "ood_mass": mean_field("ood_mass"),
        "proxy_source": args.proxy_source,
        "uncertainty_penalty": args.uncertainty_penalty,
        "kl_coef": args.kl_coef,
        "more_prefs": args.more_prefs,
        "mitigation": args.mitigation,
    }

    # Ground-truth mode validation checks
    summary["gt_decay_checks"] = {
        "high_novelty": summary["support_novelty"] > 0.4,
        "low_onpolicy_acc": summary["onpolicy_acc"] < 0.7,
        "high_disagreement": summary["ensemble_disagreement"] > 1e-4,
        "high_ood_mass": summary["ood_mass"] > 0.3,
    }
    summary["gt_overopt_checks"] = {
        "high_hack_mass": summary["hack_mass"] > 0.25,
        "low_novelty": summary["support_novelty"] < 1.0,
        "high_heldout": summary["heldout_acc"] > 0.7,
        "true_collapsed": (summary["final_true_mean20"] or 0) < -50,
    }

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    with open(out_dir / "window.csv", "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "step",
                "proxy_return",
                "true_return",
                "hack_frac",
                "ood_frac",
            ],
        )
        w.writeheader()
        w.writerows(window_rows)

    with open(out_dir / "features.jsonl", "w") as f:
        for feat in feature_snapshots:
            f.write(json.dumps(feat.to_dict()) + "\n")

    print(json.dumps(summary, indent=2))
    return summary


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RM Decay vs Overopt experiment")
    p.add_argument("--protocol", type=str, default="oracle",
                   choices=["oracle", "decay", "overopt", "shared_blindspot"])
    p.add_argument("--env", type=str, default="point_mass",
                   choices=["point_mass", "point_mass_tight", "point_mass_wide"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-steps", type=int, default=30_000)
    p.add_argument("--warmup", type=int, default=1_000)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--updates-per-step", type=int, default=1)
    p.add_argument("--ensemble-size", type=int, default=3)
    p.add_argument("--rm-epochs", type=int, default=40)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--out-dir", type=str, default="results/raw/run")
    p.add_argument("--uncertainty-penalty", type=float, default=0.0)
    p.add_argument("--kl-coef", type=float, default=0.0)
    p.add_argument("--more-prefs", action="store_true")
    p.add_argument("--shared-init", action="store_true")
    p.add_argument("--mitigation", type=str, default="none")
    p.add_argument("--diag-every", type=int, default=5)
    p.add_argument("--onpolicy-pairs", type=int, default=12)
    p.add_argument(
        "--proxy-source",
        type=str,
        default="auto",
        choices=["auto", "rm", "wrong", "star"],
        help="auto: wrong for overopt/shared_blindspot, else rm",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    run_experiment(parse_args())
