"""Tests for the anticipation-rule runner (anticip_exp.py).
Run: python -m pytest test_anticip.py"""
import numpy as np
import pandas as pd
import pytest

import anticip_exp as ax
import baselines as bl
import make_dataset as md
import oracle as orc
from baselines import make_policy
from uav_env import UAVEnv

SMALL = {"n_users": 100}
SMALL_GRID = {"grid_n": 4, "altitude_levels_m": [100, 200]}


@pytest.fixture(autouse=True)
def back_to_default():
    yield
    bl.FC_MEMO = None
    md.apply_profile("default")


def small_profiles(monkeypatch):
    real = md.apply_profile

    def small(name):
        real(name)
        if name and name != "default":
            md.CFG["baselines"].update(SMALL_GRID)
            md.CFG["n_users_choices"] = [100]
    monkeypatch.setattr(md, "apply_profile", small)


def test_new_cells_change_one_thing_each():
    md.apply_profile("sites_base")
    base = {k: dict(md.CFG[k]) for k in ("uav", "sites", "mobility", "energy", "access", "env", "baselines")}
    for c in ax.NEW_CELLS:
        md.apply_profile(c)
        assert md.CFG["mobility"]["choices"] == ["sites"] and md.CFG["env"]["access"] == "noma_opt"
        assert md.CFG["uav"]["a_max_mps2"] == 4 and md.CFG["uav"]["p_max_dbm"] == 20
        assert md.CFG["access"] == base["access"] and md.CFG["baselines"] == base["baselines"]
        assert md.CFG["sites"]["announced"] is False                # the runner sets it per pilot
        if "T600" in c:
            assert md.CFG["mobility"]["episode_steps"] == 600 and md.CFG["sites"]["t0_range_s"] == [120, 300]
        else:
            assert md.CFG["mobility"]["episode_steps"] == 300 and md.CFG["sites"]["t0_range_s"] == [60, 150]
    assert not set(ax.NEW_CELLS) & set(ax.OLD_CELLS)
    assert not set(ax.NEW_SEEDS) & set(ax.OLD_SEEDS) and not set(ax.NEW_SEEDS) & set(range(140))


def test_memo_backed_evaluate_gives_the_same_flights():
    md.apply_profile("sites_d15_t60")
    md.CFG["baselines"].update(SMALL_GRID)
    env = UAVEnv(scenario_overrides=SMALL)
    plain = {p: orc.episode_coverage(env, make_policy(p), 3)[0] for p in ("B6",)}
    md.CFG["sites"]["announced"] = True
    plain["B6dep"] = orc.episode_coverage(env, make_policy("B6dep"), 3)[0]
    ax._LAT.clear()
    env2 = UAVEnv(scenario_overrides=SMALL)
    env2.reset(seed=3)
    ax.memo_backed(env2)
    for p, want in plain.items():
        assert np.array_equal(orc.episode_coverage(env2, make_policy(p), 3)[0], want), p
    assert len(ax._LAT) > 0


def test_footprint_radius_is_physical():
    r = ax.footprint_one("sites_d15_t60", 1)
    assert 0 < r["rho_m"] < 1500 and r["cov_A0"] > 0 and r["h_star"] in md.CFG["baselines"]["altitude_levels_m"]
    assert r == ax.footprint_one("sites_d15_t60", 1)                        # deterministic


def test_cell_params_and_model():
    p = ax.cell_params("sites_v8_d15_t60", 250.0)
    assert p["T_tr_s"] == pytest.approx(1000 / 8) and p["A"] == pytest.approx((125 + 10) / 70)
    assert p["M"] == pytest.approx(125 / 300)
    p = ax.cell_params("sites_T600_d20_t0", 1200.0)                          # footprints overlap: no transit
    assert p["T_tr_s"] == 0 and p["M"] == 0
    A, M = np.array([0.5, 1.0, 4.0]), np.array([0.1, 0.2, 0.3])
    h = ax.model_h(0.2, A, M)
    assert ax.fit_k(A, M, h) == pytest.approx(0.2) and ax.r2(h, h) == 1.0
    assert np.all(np.diff(ax.model_h(0.2, np.linspace(0.1, 9, 20), 0.2)) > 0)
    assert np.all(np.diff(ax.model_h(0.2, 2.0, np.linspace(0.0, 0.5, 20))) > 0)


def test_shards_are_disjoint_and_cover_the_seeds():
    sh = ax.shard_seeds(ax.NEW_SEEDS, ax.NEW_CELLS, 4, set())
    flat = sorted(s for x in sh for s in x)
    assert flat == ax.NEW_SEEDS and sh == ax.shard_seeds(ax.NEW_SEEDS, ax.NEW_CELLS, 4, set())


def test_new_and_old_cell_runners(monkeypatch, tmp_path):
    small_profiles(monkeypatch)
    row = ax.newcell_one("sites_v25_d15_t60", 2000)
    for p in (*ax.NEW_PILOTS, "dp"):
        assert 0.0 <= row[p] <= 1.0 and row[f"{p}_survived"]
    assert row["v_max"] == 25 and row["teleport"] >= row["dp_model"] - 1e-12
    assert md.CFG["sites"]["announced"] == md.BASE_CFG["sites"]["announced"]
    old = ax.oldcell_one("sites_d15_t0", 1000)
    assert 0.0 <= old["B6dep"] <= 1.0
    monkeypatch.setattr(ax, "OUT", tmp_path)
    df = pd.DataFrame([dict(cell=c, seed=s, dp=0.8, B6=0.7, B6dep=0.75) for c in ("a", "b") for s in (1, 2)])
    t = ax.headroom_table(df, ["a", "b"], ("B6", "B6dep"))
    assert list(t.bar_pilot) == ["B6dep", "B6dep"] and np.allclose(t.h, 0.05)


def test_fit_and_evaluate_end_to_end_on_synthetic_rows(monkeypatch, tmp_path):
    import json

    import anticip_report as rep
    monkeypatch.setattr(ax, "OUT", tmp_path)
    monkeypatch.setattr(rep, "PREREG", tmp_path / "prereg")
    rng = np.random.default_rng(0)
    cells = ax.OLD_CELLS + ax.NEW_CELLS
    pd.DataFrame([dict(cell=c, seed=s, rho_m=600.0) for c in cells for s in (0, 1)]).to_csv(
        tmp_path / "footprint.csv", index=False)

    def rows(cs, seeds, pilots):
        out = []
        for c in cs:
            p = ax.cell_params(c, 600.0)
            for s in seeds:
                base = 0.7 + 0.01 * rng.standard_normal()
                r = dict(cell=c, seed=s, dp=base + ax.model_h(0.3, p["A"], p["M"]) + 0.002 * rng.standard_normal(),
                         teleport=base + 0.2, secs_total=1.0, dp_survived=True)
                for q in pilots:
                    r[q], r[f"{q}_survived"] = base - (0.001 if q != "B6dep" else 0.0), True
                out.append(r)
        return pd.DataFrame(out)
    old = rows(ax.OLD_CELLS, ax.OLD_SEEDS, (*ax.OLD_PILOTS, "B6dep"))
    old.drop(columns=["B6dep"]).to_csv(tmp_path / "confirm.csv", index=False)
    old.assign(B6dep_pre=0.5, B6dep_post=0.5).to_csv(tmp_path / "oldcells_episodes.csv", index=False)
    ax.fit(tmp_path / "confirm.csv")
    fit = json.loads((tmp_path / "fit.json").read_text())
    assert fit["model"] in ax.MODELS and fit["b6_rerun_max_abs_diff"] == 0.0
    assert fit["candidates"]["ratio"]["params"][0] == pytest.approx(0.3, rel=0.2)
    rows(ax.NEW_CELLS, ax.NEW_SEEDS, ax.NEW_PILOTS).to_csv(tmp_path / "newcells_episodes.csv", index=False)
    rep.evaluate(tmp_path / "confirm.csv", {})
    text = (tmp_path / "summary.md").read_text()
    assert "## Verdict" in text and (tmp_path / rep.FIG).exists() and (tmp_path / "prereg" / rep.FIG).exists()
