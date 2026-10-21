"""Showcase + planning dashboard for the UAV-NOMA simulation-based planning tool (thin Streamlit layer).

    pip install -r requirements-dashboard.txt
    streamlit run uav_dataset/dashboard.py

All the logic lives in dashboard_core.py (tested without Streamlit). Trained AI models are read from
UAV_MODELS_DIR (or the sidebar box), default uav_dataset/results/rl/<name>/model.zip; the app works without any.
No network calls: everything is simulated on this computer.
"""
import altair as alt
import pandas as pd
import streamlit as st

import dashboard_core as dc

st.set_page_config(page_title="UAV-NOMA planning tool", page_icon=":material/flight:", layout="wide")

# Widget start values live in session state (keys "w_..."), never in the widget calls. Streamlit forgets the values
# of widgets that are not drawn on the current page; re-assigning them keeps the controls when switching pages.
DEFAULTS = dict(w_profile="hard", w_seed=5, w_users=None, w_crowds=None, w_mobility=None, w_buildings=None,
                w_custom_bat=False, w_power=None, w_access="noma_opt", w_models=str(dc.default_models_dir()),
                w_fly_pilot="B3", w_fly_pairs=False, w_cmp_mode="Different pilots", w_cmp_pilots=["B0", "B2", "B3"],
                w_cmp_pilot="B3", w_cmp_schemes=["noma_opt", "oma_opt"], w_b_n=5, w_b_metric="coverage_full",
                w_plan_fly=False)
for _k, _v in DEFAULTS.items():
    st.session_state.setdefault(_k, _v)
for _k in list(st.session_state.keys()):
    if str(_k).startswith("w_"):
        st.session_state[_k] = st.session_state[_k]

st.markdown("""
<style>
.hero {padding: 1.6rem 1.8rem; border-radius: 14px; color: #ffffff;
       background: linear-gradient(120deg, #1d4f91 0%, #2a78d6 55%, #1baf7a 100%); margin-bottom: 1.2rem;}
.hero h1 {color: #ffffff; margin: 0 0 .3rem 0; font-size: 2.1rem;}
.hero p {color: #f0f4fa; margin: 0; font-size: 1.05rem;}
.card-value {font-size: 2.0rem; font-weight: 700; line-height: 1.2; margin: .2rem 0 .4rem 0;}
.card-title {font-size: .95rem; font-weight: 600; opacity: .85;}
</style>
""", unsafe_allow_html=True)

SEED_DECIDES = "(the scenario seed decides)"
NOTE = dict(delta_color="off", delta_arrow="off", border=True)   # a grey side note under a metric, no arrow


# ---------------------------------------------------------------- shared controls
def models_dir():
    return st.session_state.get("w_models") or str(dc.default_models_dir())


def scenario_controls():
    """Sidebar controls -> dc.Settings."""
    sb = st.sidebar
    sb.header("The disaster")
    profile = sb.selectbox("Scenario type", dc.profiles(), key="w_profile",
                           format_func=lambda p: f"{p}: {dc.PROFILE_INFO.get(p, '')}")
    d = dc.profile_defaults(profile)
    seed = sb.number_input("Scenario number (seed)", 0, 1_000_000, key="w_seed",
                           help="Each number is a different random disaster. Same number = same disaster.")
    users = sb.selectbox("People", [None, 100, 200, 300, 600, 1000, 1500], key="w_users",
                         format_func=lambda v: SEED_DECIDES if v is None else f"{v} people")
    crowds = sb.selectbox("Crowds", [None, 1, 2, 3, 4, 5, 6], key="w_crowds",
                          format_func=lambda v: SEED_DECIDES if v is None else f"{v} crowds")
    mobility = sb.selectbox("How people move", [None, *dc.MOBILITY_INFO], key="w_mobility",
                            format_func=lambda v: f"{SEED_DECIDES}: {', '.join(d['mobility'])}" if v is None
                            else dc.MOBILITY_INFO[v])
    lo, hi = d["obstacles"]
    buildings = sb.selectbox("Collapsed buildings", [None, *range(0, 11)], key="w_buildings",
                             format_func=lambda v: f"{SEED_DECIDES}: {lo}-{hi}" if v is None else f"{v} buildings")
    sb.header("The drone")
    custom_bat = sb.checkbox(f"Custom battery (profile: {d['battery_wh']:g} Wh)", key="w_custom_bat")
    if not custom_bat or "w_battery" not in st.session_state:
        st.session_state["w_battery"] = float(d["battery_wh"])          # follow the profile until customised
    battery = sb.number_input("Battery (Wh)", 1.0, 100.0, step=0.5, key="w_battery",
                              disabled=not custom_bat,
                              help="Hovering needs about 14.5-14.7 Wh for the 300 s mission.")
    power = sb.selectbox("Transmit power", [None, *d["tx_levels"]], key="w_power",
                         format_func=lambda v: dbm_label(d["p_max_dbm"], "profile: ") if v is None else dbm_label(v))
    access = sb.radio("How the drone shares its radio", list(dc.ACCESS_INFO), key="w_access",
                      format_func=lambda a: dc.ACCESS_INFO[a])
    with sb.expander("Trained AI models"):
        st.text_input("Folder with <name>/model.zip", key="w_models",
                      help="Also settable with the UAV_MODELS_DIR environment variable.")
        n = len(dc.list_models(models_dir()))
        st.caption(f"{n} model(s) found." + ("" if dc.ai_available() or n == 0 else
                                             " RL libraries not installed: pip install -r requirements-rl.txt"))
    return dc.Settings(profile=profile, seed=int(seed), n_users=users, n_clusters=crowds, mobility=mobility,
                       n_obstacles=buildings, battery_wh=float(battery) if custom_bat else None, access=access,
                       p_max_dbm=power)


def keep_valid(key, options, fallback):
    """Reset a selectbox's remembered value if it is no longer one of the options (e.g. another models folder)."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = fallback


def dbm_label(dbm, prefix=""):
    return f"{prefix}{dbm:g} dBm ({10 ** ((dbm - 30) / 10):g} W)"


def pilot_label(pid, opts):
    return f"{pid}: {opts.get(pid, '')}"


def slow_note(pilots, settings):
    slow = [p for p in pilots if p in dc.SLOW_PILOTS]
    if slow and settings.profile in ("hard", "bigarea", "rl_static", "rl_static_g20"):
        st.caption(f"{', '.join(slow)} search(es) many spots: up to ~40 s per run on a 2 x 2 km map.")


def stale(key, settings, extra=None):
    if key in st.session_state and st.session_state[key] != (settings, extra):
        st.info("The settings changed since this result was computed. Press the button again to update it.")


def line_chart(df, y, title, y_title, t_now=None, by=None, y_fmt=None, height=230, y_domain=None):
    """Altair line chart over time (one axis), optional vertical rule at the current time."""
    enc = dict(x=alt.X("t:Q", title="time (s)"),
               y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format=y_fmt) if y_fmt else alt.Axis(),
                       scale=alt.Scale(domain=y_domain) if y_domain else alt.Scale()),
               tooltip=[alt.Tooltip("t:Q", title="time (s)"), alt.Tooltip(f"{y}:Q", title=y_title, format=".3f")])
    if by:
        names = list(dict.fromkeys(df[by]))
        enc["color"] = alt.Color(f"{by}:N", title=None, sort=names,
                                 scale=alt.Scale(domain=names, range=dc.SERIES[: len(names)]),
                                 legend=alt.Legend(orient="bottom", labelLimit=320))
        enc["tooltip"] = [alt.Tooltip(f"{by}:N", title="series")] + enc["tooltip"]
        chart = alt.Chart(df).mark_line(strokeWidth=2).encode(**enc)
    else:
        chart = alt.Chart(df).mark_line(strokeWidth=2, color=dc.SERIES[0]).encode(**enc)
    if t_now is not None:
        rule = alt.Chart(pd.DataFrame({"t": [t_now]})).mark_rule(color="#888888", strokeDash=[4, 3]).encode(x="t:Q")
        chart = chart + rule
    return chart.properties(title=title, height=height)


# ---------------------------------------------------------------- page 1: showcase
def page_showcase():
    st.markdown("""<div class="hero"><h1>A flying cell tower for disaster zones</h1>
<p>A simulation-based planning tool: one drone base station serves moving survivor crowds with NOMA, among collapsed
buildings, on a limited battery. Where should it fly, how high, and how should it share its radio?</p></div>""",
                unsafe_allow_html=True)
    st.subheader("Headline results (from the project book)")
    cols = st.columns(len(dc.HEADLINES))
    for col, h in zip(cols, dc.HEADLINES, strict=True):
        with col.container(border=True, height="stretch"):
            st.markdown(f'<div class="card-title">{h["title"]}</div><div class="card-value">{h["value"]}</div>',
                        unsafe_allow_html=True)
            st.write(h["detail"])
            st.caption(f"Source: {h['source']}")
    st.caption("'Share of people served' = coverage: the share of users whose data speed meets their class minimum, "
               "averaged over the 300 s mission (a drone with an empty battery serves nobody).")

    st.subheader("Try it yourself")
    c1, c2, c3, c4 = st.columns(4)
    c1.page_link(PAGES["fly"], label="Fly a disaster", icon=":material/flight_takeoff:")
    c1.caption("Pick a disaster and a pilot, then scrub through the 300 s mission.")
    c2.page_link(PAGES["compare"], label="Compare", icon=":material/compare_arrows:")
    c2.caption("Several pilots, or NOMA vs OMA, on the same disaster; over up to 20 disasters with a 95% interval.")
    c3.page_link(PAGES["plan"], label="Plan", icon=":material/map:")
    c3.caption("Where to put the drone, NOMA vs OMA, and whether the battery lasts.")
    c4.page_link(PAGES["about"], label="About", icon=":material/info:")
    c4.caption("What is simulated and which numbers are assumptions.")

    pics, gifs = dc.gallery()
    st.subheader("Gallery")
    tab_p, tab_g = st.tabs([f"Pictures ({len(pics)})", f"Animations ({len(gifs)})"])
    for tab, items in ((tab_p, pics), (tab_g, gifs)):
        with tab:
            if not items:
                st.caption("No figures found in docs/book/figures.")
            cols = st.columns(3)
            for k, (path, caption) in enumerate(items):
                cols[k % 3].image(str(path), caption=caption, width="stretch")
    pdf = dc.book_pdf()
    st.subheader("The project book")
    if pdf:
        st.write(f"Everything in detail (decisions, results with exact numbers, verification): `{pdf}`")
        st.download_button("Download the book (PDF)", pdf.read_bytes(), file_name=pdf.name, mime="application/pdf",
                           on_click="ignore", icon=":material/menu_book:")
    else:
        st.caption("Book PDF not found (docs/book/UAV-NOMA-Project-Book.pdf). Build it with docs/book/build_pdf.py.")


# ---------------------------------------------------------------- page 2: fly a disaster
def page_fly():
    settings = scenario_controls()
    opts = dc.pilot_options(models_dir())
    st.title("Fly a disaster")
    st.caption(dc.describe(dc.build_scenario(settings)))
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    keep_valid("w_fly_pilot", list(opts), "B3")
    pilot = c1.selectbox("Pilot", list(opts), key="w_fly_pilot",
                         format_func=lambda p: pilot_label(p, opts))
    go = c2.button("Fly the mission", type="primary", icon=":material/play_arrow:", width="stretch")
    if pilot.startswith(dc.AI_PREFIX):
        st.caption(f"{opts[pilot]}. It sees only its own measurements (crowd maps, position, battery), never the "
                   "true positions.")
    slow_note([pilot], settings)
    if go:
        try:
            with st.spinner("Flying the 300 s mission..."):
                ep = dc.run_pilot(settings, pilot, models_dir())
        except (RuntimeError, ValueError) as err:
            st.error(str(err))
            return
        st.session_state.update(fly_ep=ep, fly_key=(settings, pilot), fly_t=ep.steps)
        st.session_state.pop("fly_gif", None)
    if "fly_ep" not in st.session_state:
        st.info("Choose a disaster on the left and a pilot above, then press **Fly the mission**.")
        return
    ep = st.session_state["fly_ep"]
    stale("fly_key", settings, pilot)

    if "fly_t" not in st.session_state:
        st.session_state["fly_t"] = ep.steps
    t = st.slider("Time (s): drag to replay the mission", 1, ep.steps, key="fly_t")
    m = dc.metrics_at(ep, t)
    cards = st.columns(6)
    cards[0].metric("Time", f"{m['t']} s", border=True)
    cards[1].metric("People served", f"{m['coverage']:.0%}", f"{m['served_users']} of {m['n_users']}",
                    **NOTE)
    cards[2].metric("Rescue users served", f"{m['rescue_served']:.0%}", border=True)
    cards[3].metric("Total data speed", f"{m['sum_rate_mbps']:.1f} Mbps", border=True)
    cards[4].metric("Battery left", f"{m['battery_wh']:.1f} Wh" + ("" if m["alive"] else " (empty)"), border=True)
    cards[5].metric("Altitude", f"{m['h']:.0f} m", f"power {m['power_w']:g} W", **NOTE)

    left, right = st.columns([1.15, 1])
    with left:
        pairs = st.toggle("Show NOMA pairs (lines join two people sharing one channel)", key="w_fly_pairs",
                          disabled=ep.env.access not in ("noma", "noma_opt"),
                          help="The 60 pairs nearest the drone. OMA schemes have no pairs.")
        st.pyplot(dc.render_frame(ep, t, show_pairs=pairs), width="stretch")
    with right:
        tr = ep.trace
        cov = pd.concat([pd.DataFrame({"t": tr.t, "coverage": tr.coverage, "series": f"this run ({ep.env.access})"}),
                         pd.DataFrame({"t": tr.t, "coverage": tr.coverage_noma, "series": "fixed NOMA would give"}),
                         pd.DataFrame({"t": tr.t, "coverage": tr.coverage_oma, "series": "fixed OMA would give"})])
        st.altair_chart(line_chart(cov, "coverage", "Share of people served", "share served", t, by="series",
                                   y_fmt="%", y_domain=[0, 1]), width="stretch")
        st.altair_chart(line_chart(tr, "battery_wh", "Battery left", "Wh", t, height=180), width="stretch")
    c1, c2 = st.columns(2)
    c1.altair_chart(line_chart(tr, "rescue_served", "Rescue users served", "share of rescue users", t, y_fmt="%",
                               y_domain=[0, 1], height=200), width="stretch")
    c2.altair_chart(line_chart(tr, "sum_rate_mbps", "Total data speed", "Mbps", t, height=200), width="stretch")

    s = ep.summary
    life = "The battery lasted the whole mission." if s["survived"] else \
        f"The battery ran out at {s['steps']} s; from then on nobody is served."
    st.markdown(f"**Mission summary.** {s['coverage_full']:.1%} of people served on average over the "
                f"{ep.env.T} s mission, rescue users not served {s['rescue_outage']:.1%}, total data speed "
                f"{s['sum_rate_mbps']:.1f} Mbps on average. {life}")
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("Make GIF", icon=":material/movie:"):
        with st.spinner("Drawing the animation (about 10 s)..."):
            st.session_state["fly_gif"] = dc.make_gif(ep)
    c2.download_button("Download the trace (CSV)", ep.trace.to_csv(index=False).encode(),
                       file_name=f"trace_seed{ep.settings.seed}_{ep.pilot.replace(':', '').replace(' ', '_')}.csv",
                       mime="text/csv", on_click="ignore")
    if "fly_gif" in st.session_state:
        c3.download_button("Download the GIF", st.session_state["fly_gif"], file_name="mission.gif", mime="image/gif",
                           on_click="ignore", type="primary")
        st.image(st.session_state["fly_gif"], width=520)


# ---------------------------------------------------------------- page 3: compare
def page_compare():
    settings = scenario_controls()
    opts = dc.pilot_options(models_dir())
    st.title("Compare")
    st.caption(dc.describe(dc.build_scenario(settings)))
    mode = st.radio("What to compare", ["Different pilots", "Ways to share the radio (NOMA vs OMA)"],
                    horizontal=True, key="w_cmp_mode")
    if mode == "Different pilots":
        st.session_state["w_cmp_pilots"] = [p for p in st.session_state["w_cmp_pilots"] if p in opts]
        items = st.multiselect("Pilots (2-4)", list(opts), max_selections=4,
                               key="w_cmp_pilots", format_func=lambda p: pilot_label(p, opts))
        pilot = None
        slow_note(items, settings)
    else:
        c1, c2 = st.columns(2)
        keep_valid("w_cmp_pilot", list(opts), "B3")
        pilot = c1.selectbox("Pilot", list(opts), key="w_cmp_pilot",
                             format_func=lambda p: pilot_label(p, opts))
        items = c2.multiselect("Schemes (2-4)", list(dc.ACCESS_INFO), max_selections=4,
                               key="w_cmp_schemes", format_func=lambda a: dc.ACCESS_INFO[a])
        slow_note([pilot], settings)
    extra = (mode, tuple(items), pilot)
    if st.button("Run on this disaster", type="primary", icon=":material/play_arrow:", disabled=len(items) < 2):
        bar = st.progress(0.0, "starting...")
        try:
            if pilot is None:
                res = dc.compare_pilots(settings, items, models_dir(), lambda f, s: bar.progress(f, f"done: {s}"))
            else:
                res = dc.compare_access(settings, pilot, items, models_dir(),
                                        lambda f, s: bar.progress(f, f"done: {s}"))
        except (RuntimeError, ValueError) as err:
            st.error(str(err))
            return
        bar.empty()
        st.session_state.update(cmp_res=res, cmp_key=(settings, extra))
    if len(items) < 2:
        st.caption("Choose at least two.")
    if "cmp_res" in st.session_state:
        res = st.session_state["cmp_res"]
        stale("cmp_key", settings, extra)
        st.pyplot(dc.render_maps(res), width="stretch")
        st.caption("Maps show the last second: green = served, red = not served, black ring = rescue user, "
                   "grey = collapsed building, blue line = flight path (dot = start, triangle = end).")
        c1, c2 = st.columns(2)
        c1.altair_chart(line_chart(dc.long_trace(res, "coverage"), "value", "Share of people served", "share served",
                                   by="name", y_fmt="%", y_domain=[0, 1]), width="stretch")
        c2.altair_chart(line_chart(dc.long_trace(res, "rescue_served"), "value", "Rescue users served",
                                   "share of rescue users", by="name", y_fmt="%", y_domain=[0, 1]), width="stretch")
        st.dataframe(dc.summary_table(res), hide_index=True)

    with st.expander("Over several disasters (paired comparison with a 95% interval)", expanded=False):
        st.write("Runs both on N disasters (scenario numbers seed, seed+1, ...; same overrides) and reports the "
                 "average difference per disaster. One process only, so it takes a while.")
        if len(items) < 2:
            st.caption("Choose at least two above first.")
            return
        c1, c2, c3, c4 = st.columns(4)
        fmt = (lambda p: pilot_label(p, opts)) if pilot is None else (lambda a: dc.ACCESS_INFO[a])
        first, second = (items[-1], items[0]) if pilot is None else (items[0], items[1])   # usually the better first
        keep_valid("w_b_a", items, first)
        keep_valid("w_b_b", items, second)
        a = c1.selectbox("A", items, key="w_b_a", format_func=fmt)
        b = c2.selectbox("B", items, key="w_b_b", format_func=fmt)
        n = c3.slider("Number of disasters", 2, dc.MAX_BATCH, key="w_b_n")
        metric = c4.selectbox("Measure", list(dc.METRICS), key="w_b_metric", format_func=lambda k: dc.METRICS[k][0])
        bextra = (a, b, n, metric, pilot)
        if st.button("Run the batch", icon=":material/stacked_bar_chart:", disabled=a == b):
            bar = st.progress(0.0, "starting...")
            try:
                batch = dc.batch_compare(settings, a, b, n, kind="pilots" if pilot is None else "access",
                                         pilot=pilot or "B3", metric=metric, models_dir=models_dir(),
                                         progress=lambda f, s: bar.progress(f, s))
            except (RuntimeError, ValueError) as err:
                st.error(str(err))
                return
            bar.empty()
            st.session_state.update(cmp_batch=batch, cmp_bkey=(settings, bextra))
        if "cmp_batch" in st.session_state:
            bt = st.session_state["cmp_batch"]
            stale("cmp_bkey", settings, bextra)
            c1, c2, c3 = st.columns(3)
            c1.metric(f"A = {bt.a}", f"{bt.mean_a[0]:.3f}", f"+/- {bt.mean_a[1]:.3f}", **NOTE)
            c2.metric(f"B = {bt.b}", f"{bt.mean_b[0]:.3f}", f"+/- {bt.mean_b[1]:.3f}", **NOTE)
            c3.metric("A minus B (paired)", f"{bt.diff[0]:+.3f}", f"+/- {bt.diff[1]:.3f}", **NOTE)
            (st.success if bt.significant else st.info)(bt.verdict)
            d = bt.per_seed.rename(columns={"difference (A - B)": "diff"})
            bars = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=dc.SERIES[0]).encode(
                x=alt.X("scenario seed:O", title="scenario number"), y=alt.Y("diff:Q", title="A minus B"),
                tooltip=["scenario seed", "people", "movement", alt.Tooltip("diff:Q", format="+.3f")])
            zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#888888").encode(y="y:Q")
            st.altair_chart((bars + zero).properties(title="Difference per disaster", height=220), width="stretch")
            st.dataframe(bt.per_seed, hide_index=True)


# ---------------------------------------------------------------- page 4: plan
def page_plan():
    settings = scenario_controls()
    st.title("Plan a deployment")
    st.caption(dc.describe(dc.build_scenario(settings)))
    st.write("Searches every spot of a grid at five altitudes (pilot B6's search) for the crowd as it stands at the "
             "start, then reports how many people each way of sharing the radio would serve there, and whether the "
             "battery lasts the mission.")
    fly = st.checkbox("Also fly B6 for the whole mission (re-planning every 10 s; slow on 2 x 2 km maps)",
                      key="w_plan_fly")
    if st.button("Make the plan", type="primary", icon=":material/map:"):
        with st.spinner("Searching..."):
            st.session_state.update(plan=dc.recommend(settings, fly=fly), plan_key=(settings, fly))
    if "plan" not in st.session_state:
        st.info("Choose a disaster on the left and press **Make the plan**.")
        return
    p = st.session_state["plan"]
    stale("plan_key", settings, fly)
    c = st.columns(5)
    c[0].metric("Spot (east, north)", f"{p.x_m:.0f}, {p.y_m:.0f} m", border=True)
    c[1].metric("Altitude", f"{p.altitude_m:.0f} m", border=True)
    c[2].metric("Transmit power", f"{p.power_dbm:.0f} dBm", f"{p.power_w:g} W", **NOTE)
    gain = p.coverage["noma_opt"] - p.coverage["oma_opt"]
    c[3].metric("Served: adaptive NOMA", f"{p.coverage['noma_opt']:.1%}",
                f"{gain * 100:+.1f} points vs optimised OMA ({p.coverage['oma_opt']:.1%})", delta_arrow="off",
                border=True)
    c[4].metric("Rescue users served (NOMA)", f"{p.rescue_served['noma_opt']:.1%}",
                f"OMA optimised {p.rescue_served['oma_opt']:.1%}", **NOTE)
    (st.success if p.battery_ok else st.warning)(f"**Battery.** {p.battery_advice}")
    left, right = st.columns([1.15, 1])
    left.pyplot(dc.render_plan(p), width="stretch")
    with right:
        sch = pd.DataFrame({"scheme": [dc.ACCESS_INFO[s].split(":")[0] for s in p.coverage],
                            "people served": list(p.coverage.values())})
        bars = alt.Chart(sch).mark_bar(cornerRadiusEnd=4, color=dc.SERIES[0]).encode(
            y=alt.Y("scheme:N", title=None, sort=None),
            x=alt.X("people served:Q", title="share served at the spot", axis=alt.Axis(format="%"),
                    scale=alt.Scale(domain=[0, 1])),
            tooltip=["scheme", alt.Tooltip("people served:Q", format=".1%")])
        st.altair_chart(bars.properties(title="At the recommended spot, by radio-sharing scheme", height=200),
                        width="stretch")
        st.markdown(p.markdown().split("\n", 2)[2])
    st.dataframe(p.table(), hide_index=True)
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download plan (Markdown)", p.markdown().encode(), file_name=f"plan_seed{p.settings.seed}.md",
                       mime="text/markdown", on_click="ignore")
    d2.download_button("Download plan (CSV)", p.table().to_csv(index=False).encode(),
                       file_name=f"plan_seed{p.settings.seed}.csv", mime="text/csv", on_click="ignore")


# ---------------------------------------------------------------- page 5: about
def page_about():
    st.title("About this tool")
    st.markdown("""
**What it is.** A *simulation-based planning tool*: rescue planners can try drone strategies in software before flying
real hardware. It is not fed live data, so it is **not** a digital twin.

**What is simulated (every second of a 300 s mission).**
- **The disaster:** survivors in crowds (plus a few scattered people) on a 1 x 1 km or 2 x 2 km map, collapsed buildings
  (rectangles that weaken any signal passing through them), and five kinds of users (rescue, video, voice, IoT, normal),
  each needing a minimum data speed.
- **How people move:** still, wandering, drifting groups, walking to shelters, sudden jumps, or a panic surge.
- **The radio:** air-to-ground path loss with a line-of-sight probability (Al-Hourani model). A user is *served* when
  their data speed reaches their class minimum.
- **Sharing the radio:** NOMA (two people share one channel; the stronger one removes the weaker one's signal first)
  vs OMA (everyone has their own slice), with the same total bandwidth and power. *Adaptive* / *optimised* versions
  give each person just their minimum speed at minimum power, so more people fit.
- **The drone:** rotary-wing energy model (Zeng-Xu-Zhang): hovering costs about 174 W, flying at about 10 m/s costs
  less. When the battery is empty the drone serves nobody.
- **Pilots:** B0 parked in the middle; B1 follow the biggest crowd; B2 k-means crowd centres; B3 grid search; B4 swarm
  search (PSO); B5 energy-aware grid search; B6 grid search with altitude; B3obs* grid search with only the AI's
  information; random; and any trained AI (it sees only its own measurements).
""")
    st.subheader("Assumptions (value, unit, where it comes from)")
    st.dataframe(dc.assumptions_table(), hide_index=True)
    st.caption("Engineering assumptions are the team's choices, not measured values. Full table with sensitivity "
               "ranges: docs/assumptions.md. Results quoted on the Showcase page come from 100-scenario runs in "
               "the project book, not from this app.")
    st.subheader("How to reproduce")
    st.code("""pip install -r requirements.txt -r requirements-dashboard.txt
streamlit run uav_dataset/dashboard.py

# the same runs from the command line
cd uav_dataset
python view_run.py --seed 5 --profile hard --policy B3
python compare_run.py --seed 5 --profile hard --policies B0,B2,B3,B4
python run_baselines.py --profile hard --seeds 20 --workers 1

# trained AI models: put <name>/model.zip + config.json in uav_dataset/results/rl, or
set UAV_MODELS_DIR=C:\\path\\to\\results\\rl     (PowerShell: $env:UAV_MODELS_DIR = "...")
pip install -r requirements-rl.txt              # only needed to fly an AI""", language="bash")
    st.caption("Every result is reproducible from config.yaml + the scenario number (seeded random numbers only).")


PAGES = {
    "showcase": st.Page(page_showcase, title="Showcase", icon=":material/star:", default=True),
    "fly": st.Page(page_fly, title="Fly a disaster", icon=":material/flight_takeoff:", url_path="fly"),
    "compare": st.Page(page_compare, title="Compare", icon=":material/compare_arrows:", url_path="compare"),
    "plan": st.Page(page_plan, title="Plan", icon=":material/map:", url_path="plan"),
    "about": st.Page(page_about, title="About", icon=":material/info:", url_path="about"),
}
st.navigation(list(PAGES.values())).run()
