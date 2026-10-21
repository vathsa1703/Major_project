"""The network that lets the agent read the two user-density maps as a picture (needs PyTorch + Stable-Baselines3).
Kept out of rl_utils.py so the simulator, the baselines and the tests do not need the heavy RL libraries."""
import torch
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.sac.policies import SACPolicy
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


# ---------------------------------------------------------------- Track 2: Dict observations, asymmetric SAC critic
def _coord_channels(grid):
    """(1, 2, grid, grid): x of every cell (map dim 0, as in the env's maps) and y (dim 1), in [-1, 1]."""
    xs, ys = torch.meshgrid(torch.linspace(-1, 1, grid), torch.linspace(-1, 1, grid), indexing="ij")
    return torch.stack([xs, ys])[None]


def _cheap_cnn(c_in, grid, out_dim, first_stride=1):
    """Two 3x3 convolutions, the second with stride 2 (and the first too if first_stride=2), so the Linear layer
    after them is 4x (16x) smaller than in CnnMapExtractor. 10x10 maps -> 32 x 5 x 5 = 800 features."""
    g = (grid + first_stride - 1) // first_stride
    g = (g + 1) // 2
    return nn.Sequential(
        nn.Conv2d(c_in, 16, 3, stride=first_stride, padding=1), nn.ReLU(),
        nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(), nn.Flatten(),
        nn.Linear(32 * g * g, out_dim), nn.ReLU())


class DictMapExtractor(BaseFeaturesExtractor):
    """Reads a Dict observation (uav_env obs_mode='dict'): the maps (C, grid, grid) through a cheap CNN with two
    coordinate channels, the scalars through a small MLP, joined.

    use_priv=False (the ACTOR, and any PPO network): only the keys "maps" and "scalars" are ever read; the
    privileged keys (any key starting with "priv") are ignored even when present, so the actor's output cannot
    depend on them (tested in test_rl_net.py). use_priv=True (only an asymmetric SAC CRITIC, training only): also reads
    the true-state maps "priv_maps" (uint8, scaled back to [0, 1] here) through a second cheap CNN, and "priv_n"."""

    def __init__(self, observation_space, features_dim=128, scalar_dim=32, use_priv=False, priv_dim=128):
        sp = observation_space.spaces
        self.has_maps, self.has_scalars, self.use_priv = "maps" in sp, "scalars" in sp, bool(use_priv)
        assert self.has_maps or self.has_scalars, "the observation needs maps or scalars"
        if self.use_priv:
            assert "priv_maps" in sp and "priv_n" in sp, "use_priv needs an env built with privileged=True"
        total = (features_dim if self.has_maps else 0) + (scalar_dim if self.has_scalars else 0)
        total += (priv_dim + sp["priv_n"].shape[0]) if self.use_priv else 0
        super().__init__(observation_space, total)
        if self.has_maps:
            c, g, _ = sp["maps"].shape
            self.map_net = _cheap_cnn(c + 2, g, features_dim)
            self.register_buffer("coords", _coord_channels(g))
        if self.has_scalars:
            self.scalar_net = nn.Sequential(nn.Linear(sp["scalars"].shape[0], scalar_dim), nn.ReLU())
        if self.use_priv:
            c, p, _ = sp["priv_maps"].shape
            self.priv_net = _cheap_cnn(c + 2, p, priv_dim, first_stride=2)
            self.register_buffer("priv_coords", _coord_channels(p))

    def forward(self, obs):
        parts = []
        if self.has_maps:
            m = obs["maps"]
            parts.append(self.map_net(torch.cat([m, self.coords.expand(len(m), -1, -1, -1)], dim=1)))
        if self.has_scalars:
            parts.append(self.scalar_net(obs["scalars"]))
        if self.use_priv:                                   # critic only
            pm = obs["priv_maps"].float() / 255.0
            parts.append(self.priv_net(torch.cat([pm, self.priv_coords.expand(len(pm), -1, -1, -1)], dim=1)))
            parts.append(obs["priv_n"].float())
        return torch.cat(parts, dim=1)


class AsymSACPolicy(SACPolicy):
    """SAC whose CRITIC may read more than the ACTOR. The actor's extractor is built from features_extractor_kwargs
    (use_priv must be False); each critic (and its target) gets its own extractor built from features_extractor_kwargs
    updated with critic_features_extractor_kwargs (e.g. use_priv=True). With no critic kwargs this is plain SAC with
    separate (unshared) extractors. Only the actor acts (SACPolicy._predict calls self.actor); the critics are used
    for training only and are not needed to fly."""

    def __init__(self, *args, critic_features_extractor_kwargs=None, **kwargs):
        self.critic_features_extractor_kwargs = dict(critic_features_extractor_kwargs or {})
        super().__init__(*args, **kwargs)
        assert not getattr(self.actor.features_extractor, "use_priv", False), "the actor must never see priv"
        assert not self.share_features_extractor, "actor and critic must have separate extractors"

    def make_critic(self, features_extractor=None):
        if features_extractor is None:
            kw = {**self.features_extractor_kwargs, **self.critic_features_extractor_kwargs}
            features_extractor = self.features_extractor_class(self.observation_space, **kw)
        return super().make_critic(features_extractor)

    def _get_constructor_parameters(self):
        data = super()._get_constructor_parameters()
        data["critic_features_extractor_kwargs"] = self.critic_features_extractor_kwargs
        return data
