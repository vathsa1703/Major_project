"""The network that lets the agent read the two user-density maps as a picture (needs PyTorch + Stable-Baselines3).
Kept out of rl_utils.py so the simulator, the baselines and the tests do not need the heavy RL libraries."""
import torch
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from torch import nn


class CnnMapExtractor(BaseFeaturesExtractor):
    """The two user-density maps (all users, rescue users) go through a small convolutional network as a picture,
    with two extra coordinate channels (x and y of every cell, like CoordConv), because the agent must answer
    with coordinates. The few scalar inputs go through a small MLP, and the two are joined.
    The agent still sees only the maps and the drone's own measurements: no hint is added, only the way they
    are read."""

    def __init__(self, observation_space, grid=10, features_dim=128, scalar_dim=32):
        n = int(observation_space.shape[0])
        self.grid, self.n_scalar = grid, n - 2 * grid * grid
        assert self.n_scalar >= 0, "the observation must end with the two heatmaps (groups heat_all and heat_rescue)"
        super().__init__(observation_space, features_dim + (scalar_dim if self.n_scalar else 0))
        self.cnn = nn.Sequential(
            nn.Conv2d(4, 16, 3, padding=1), nn.ReLU(), nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.Flatten(),
            nn.Linear(32 * grid * grid, features_dim), nn.ReLU())
        self.mlp = nn.Sequential(nn.Linear(self.n_scalar, scalar_dim), nn.ReLU()) if self.n_scalar else None
        ys, xs = torch.meshgrid(torch.linspace(-1, 1, grid), torch.linspace(-1, 1, grid), indexing="ij")
        self.register_buffer("coords", torch.stack([xs, ys])[None])           # (1, 2, grid, grid)

    def forward(self, obs):
        maps = obs[:, self.n_scalar:].reshape(-1, 2, self.grid, self.grid)
        img = torch.cat([maps, self.coords.expand(len(obs), -1, -1, -1)], dim=1)
        out = self.cnn(img)
        return torch.cat([out, self.mlp(obs[:, : self.n_scalar])], dim=1) if self.mlp is not None else out
