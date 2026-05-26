from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn


@dataclass(frozen=True)
class TransitionModelConfig:
    dim: int
    hidden_dim: int = 128
    lr: float = 1e-3
    weight_decay: float = 1e-4
    device: str = "cpu"


class TransitionModel(nn.Module):
    """Simple MLP transition model: e_t -> e_hat_{t+1}."""

    def __init__(self, cfg: TransitionModelConfig):
        super().__init__()
        self.cfg = cfg
        self.net = nn.Sequential(
            nn.Linear(cfg.dim, cfg.hidden_dim),
            nn.ReLU(),
            nn.Linear(cfg.hidden_dim, cfg.dim),
        )
        self.to(cfg.device)
        self._opt = torch.optim.AdamW(
            self.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
        )
        self._loss = nn.MSELoss()
        # Tracks how many train_batch calls have happened. Consumers can
        # check ``trained_steps > 0`` before trusting predict() — an
        # untrained MLP returns a unit-norm vector that *looks* fine but
        # is pure noise.
        self.trained_steps: int = 0

    @torch.no_grad()
    def predict(self, e_t: np.ndarray) -> np.ndarray:
        x = torch.from_numpy(e_t.astype(np.float32)).to(self.cfg.device)
        y = self.net(x)
        return y.detach().cpu().numpy()

    def train_batch(self, e_t: np.ndarray, e_next: np.ndarray) -> float:
        self.train(True)
        x = torch.from_numpy(e_t.astype(np.float32)).to(self.cfg.device)
        y_true = torch.from_numpy(e_next.astype(np.float32)).to(self.cfg.device)
        y_pred = self.net(x)
        loss = self._loss(y_pred, y_true)
        self._opt.zero_grad(set_to_none=True)
        loss.backward()
        self._opt.step()
        self.trained_steps += 1
        return float(loss.detach().cpu().item())
