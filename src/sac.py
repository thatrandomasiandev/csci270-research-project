"""Lightweight Soft Actor-Critic for continuous control diagnostics."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal


LOG_STD_MIN = -20
LOG_STD_MAX = 2


def mlp(sizes, activation=nn.ReLU, output_activation=nn.Identity):
    layers = []
    for i in range(len(sizes) - 1):
        act = activation if i < len(sizes) - 2 else output_activation
        layers += [nn.Linear(sizes[i], sizes[i + 1]), act()]
    return nn.Sequential(*layers)


class GaussianActor(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 128):
        super().__init__()
        self.net = mlp([obs_dim, hidden, hidden], nn.ReLU, nn.ReLU)
        self.mu = nn.Linear(hidden, action_dim)
        self.log_std = nn.Linear(hidden, action_dim)

    def forward(self, obs: torch.Tensor):
        h = self.net(obs)
        mu = self.mu(h)
        log_std = self.log_std(h).clamp(LOG_STD_MIN, LOG_STD_MAX)
        return mu, log_std

    def sample(self, obs: torch.Tensor):
        mu, log_std = self.forward(obs)
        std = log_std.exp()
        dist = Normal(mu, std)
        x = dist.rsample()
        action = torch.tanh(x)
        # tanh correction
        log_prob = dist.log_prob(x) - torch.log(1 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(-1, keepdim=True)
        return action, log_prob, torch.tanh(mu)

    def entropy_and_kl_to(self, obs: torch.Tensor, other: "GaussianActor"):
        mu, log_std = self.forward(obs)
        mu_o, log_std_o = other.forward(obs)
        std = log_std.exp()
        std_o = log_std_o.exp()
        # KL between diagonal Gaussians (pre-tanh), mean over batch/dims
        kl = (
            log_std_o
            - log_std
            + (std.pow(2) + (mu - mu_o).pow(2)) / (2 * std_o.pow(2) + 1e-8)
            - 0.5
        ).sum(-1)
        ent = (0.5 + 0.5 * np.log(2 * np.pi) + log_std).sum(-1)
        return ent.mean().item(), kl.mean().item()


class Critic(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 128):
        super().__init__()
        self.q1 = mlp([obs_dim + action_dim, hidden, hidden, 1])
        self.q2 = mlp([obs_dim + action_dim, hidden, hidden, 1])

    def forward(self, obs: torch.Tensor, action: torch.Tensor):
        x = torch.cat([obs, action], dim=-1)
        return self.q1(x), self.q2(x)


class ReplayBuffer:
    def __init__(self, obs_dim: int, action_dim: int, size: int = 200_000):
        self.obs = np.zeros((size, obs_dim), dtype=np.float32)
        self.next_obs = np.zeros((size, obs_dim), dtype=np.float32)
        self.actions = np.zeros((size, action_dim), dtype=np.float32)
        self.rewards = np.zeros((size, 1), dtype=np.float32)
        self.dones = np.zeros((size, 1), dtype=np.float32)
        self.max_size = size
        self.ptr = 0
        self.size = 0

    def add(self, obs, action, reward, next_obs, done):
        self.obs[self.ptr] = obs
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.next_obs[self.ptr] = next_obs
        self.dones[self.ptr] = float(done)
        self.ptr = (self.ptr + 1) % self.max_size
        self.size = min(self.size + 1, self.max_size)

    def sample(self, batch_size: int, device: torch.device):
        idx = np.random.randint(0, self.size, size=batch_size)
        return (
            torch.as_tensor(self.obs[idx], device=device),
            torch.as_tensor(self.actions[idx], device=device),
            torch.as_tensor(self.rewards[idx], device=device),
            torch.as_tensor(self.next_obs[idx], device=device),
            torch.as_tensor(self.dones[idx], device=device),
        )


class SAC:
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        device: str = "cpu",
        hidden: int = 128,
        lr: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        init_alpha: float = 0.2,
        uncertainty_penalty: float = 0.0,
        kl_coef: float = 0.0,
    ):
        self.device = torch.device(device)
        self.gamma = gamma
        self.tau = tau
        self.uncertainty_penalty = uncertainty_penalty
        self.kl_coef = kl_coef

        self.actor = GaussianActor(obs_dim, action_dim, hidden).to(self.device)
        self.actor_init = GaussianActor(obs_dim, action_dim, hidden).to(self.device)
        self.actor_init.load_state_dict(self.actor.state_dict())
        for p in self.actor_init.parameters():
            p.requires_grad = False

        self.critic = Critic(obs_dim, action_dim, hidden).to(self.device)
        self.critic_tgt = Critic(obs_dim, action_dim, hidden).to(self.device)
        self.critic_tgt.load_state_dict(self.critic.state_dict())

        self.log_alpha = torch.tensor(
            np.log(init_alpha), dtype=torch.float32, device=self.device, requires_grad=True
        )
        self.target_entropy = -float(action_dim)

        self.actor_opt = torch.optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(), lr=lr)
        self.alpha_opt = torch.optim.Adam([self.log_alpha], lr=lr)

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def snapshot_init_policy(self):
        self.actor_init.load_state_dict(self.actor.state_dict())

    @torch.no_grad()
    def act(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        o = torch.as_tensor(obs[None], dtype=torch.float32, device=self.device)
        action, _, mean = self.actor.sample(o)
        a = mean if deterministic else action
        return a.cpu().numpy()[0]

    def update(self, batch, uncertainty: torch.Tensor | None = None):
        obs, actions, rewards, next_obs, dones = batch

        # Optional uncertainty penalty on proxy rewards (mitigation)
        if uncertainty is not None and self.uncertainty_penalty > 0:
            rewards = rewards - self.uncertainty_penalty * uncertainty

        with torch.no_grad():
            next_actions, next_logp, _ = self.actor.sample(next_obs)
            q1_t, q2_t = self.critic_tgt(next_obs, next_actions)
            q_t = torch.min(q1_t, q2_t) - self.alpha.detach() * next_logp
            backup = rewards + (1 - dones) * self.gamma * q_t

        q1, q2 = self.critic(obs, actions)
        critic_loss = F.mse_loss(q1, backup) + F.mse_loss(q2, backup)
        self.critic_opt.zero_grad()
        critic_loss.backward()
        self.critic_opt.step()

        new_actions, logp, _ = self.actor.sample(obs)
        q1_pi, q2_pi = self.critic(obs, new_actions)
        q_pi = torch.min(q1_pi, q2_pi)
        actor_loss = (self.alpha.detach() * logp - q_pi).mean()

        if self.kl_coef > 0:
            with torch.no_grad():
                mu_i, log_std_i = self.actor_init(obs)
            mu, log_std = self.actor(obs)
            std = log_std.exp()
            std_i = log_std_i.exp()
            kl = (
                log_std_i
                - log_std
                + (std.pow(2) + (mu - mu_i).pow(2)) / (2 * std_i.pow(2) + 1e-8)
                - 0.5
            ).sum(-1).mean()
            actor_loss = actor_loss + self.kl_coef * kl

        self.actor_opt.zero_grad()
        actor_loss.backward()
        self.actor_opt.step()

        alpha_loss = -(self.log_alpha * (logp + self.target_entropy).detach()).mean()
        self.alpha_opt.zero_grad()
        alpha_loss.backward()
        self.alpha_opt.step()

        with torch.no_grad():
            for p, p_t in zip(self.critic.parameters(), self.critic_tgt.parameters()):
                p_t.data.mul_(1 - self.tau)
                p_t.data.add_(self.tau * p.data)

        return {
            "critic_loss": float(critic_loss.item()),
            "actor_loss": float(actor_loss.item()),
            "alpha": float(self.alpha.item()),
        }

    def policy_stats(self, obs_batch: np.ndarray) -> Tuple[float, float]:
        o = torch.as_tensor(obs_batch, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            return self.actor.entropy_and_kl_to(o, self.actor_init)
