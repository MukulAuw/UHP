"""
AmarUjala · Paywall views & clicks dashboard (app 2.0.0.37) — live from a Google Sheet.

The sheet holds one row per slice and day: each filter column is a value or ALL, and users is the exact
unique count for that slice. The dashboard looks up the one row matching the filters.

Run:   pip install -r requirements.txt
       streamlit run paywall_dashboard.py
"""
import hashlib
import hmac
import io
import os
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import altair as alt
import requests
import streamlit as st


# ---------------------------------------------------------------- settings
def secret(name: str, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


APP_TITLE = "Paywall views & clicks"
APP_SUB = "Above App Version 2.0.0.37 · unique users"
SHEET_URL = (secret("sheet_url") or os.environ.get("PAYWALL_SHEET_URL")
             or "https://docs.google.com/spreadsheets/d/PASTE_SHEET_ID/edit#gid=0")
SERVICE_ACCOUNT_JSON = Path(__file__).with_name("pw_service-account.json")
REFRESH_SECONDS = 60
LABEL_MAX_DAYS = 31
DAYFIRST = True
DIMS = ["Premium", "isGuest", "PaywallStatus", "UserType", "Category", "Sub_Category", "Magzine"]
REQUIRED = ["event_date_ist", "event_type", "Premium", "isGuest", "PaywallStatus",
            "UserType", "Category", "Sub_Category", "users"]
BLANK = "Blank"
ALL = "ALL"
FILTER_COLS = 5
_INVISIBLE = re.compile(r"[\s\u200b-\u200f\u2060\ufeff]+")
_EMPTY = {"", "nan", "none", "null", '""', "''"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

AU = {
    "red": "#E31E25", "red_deep": "#B4141A", "maroon": "#6E1826",
    "rose": "#DC8C97", "rose_pale": "#F6BFC6", "rose_wash": "#FCE6E9",
    "paper": "#FBF5F1", "ink": "#241512", "line": "#E3D2CB", "muted": "#8A6F68",
    "up": "#1B7F3B",
}
FAMILY_COLOR = {"Epaper": AU["red"], "Premium article": AU["ink"], "Adaptive": AU["rose"],
                "Other": AU["muted"], "Overall": AU["maroon"]}

TAB_TRENDS = "📈 Day on day"
TAB_WOW = "📅 Week over week"
PERSIST_KEYS = ["tab", "tr_metric", "wow_day", "wow_mode", "wow_cat_metric"]

USE_OVERALL = {"View": False, "Click": False}

_ver = tuple(int(x) for x in st.__version__.split(".")[:2])
STRETCH = {"width": "stretch"} if _ver >= (1, 49) else {"use_container_width": True}

try:
    from streamlit import config as _st_config
    for _k, _v in {
        "theme.base": "light", "theme.primaryColor": AU["red"], "theme.backgroundColor": "#FFFFFF",
        "theme.secondaryBackgroundColor": AU["paper"], "theme.textColor": AU["ink"],
        "theme.font": "sans serif", "client.toolbarMode": "viewer",
    }.items():
        if _st_config.get_option(_k) != _v:
            _st_config.set_option(_k, _v)
except Exception:
    pass

st.set_page_config(page_title="AmarUjala · Paywall dashboard", layout="wide", page_icon="📰")


# ---------------------------------------------------------------- login
LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;500;600&display=swap');
:root { --au-paper:#FBF5F1; --au-ink:#241512; --au-red:#E31E25; --au-red-deep:#B4141A;
        --au-rose:#DC8C97; --au-rose-pale:#F6BFC6; --au-line:#E3D2CB; --au-muted:#8A6F68; }
header[data-testid="stHeader"] { display: none !important; }
[data-testid="stAppViewContainer"] { background: var(--au-paper) !important; }
[data-testid="stAppViewContainer"] .block-container { padding-top: 9vh; }
.au-mast { text-align: center; margin-bottom: 2.1rem; }
.au-wordmark { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 2.8rem;
               letter-spacing: -0.01em; color: var(--au-red); line-height: 1.05; }
.au-rule { width: 56px; height: 2px; margin: 0.85rem auto 0.9rem; background: var(--au-rose); }
.au-dateline { font-family: 'Inter', sans-serif; font-size: 0.92rem; color: var(--au-muted); }
div[data-testid="stForm"] { background: #FFFFFF; border: 1px solid var(--au-line);
    border-top: 3px solid var(--au-red); border-radius: 3px; padding: 3.5rem 3rem 3.2rem; }
div[data-testid="stForm"] label p, div[data-testid="stWidgetLabel"] p {
    font-family: 'Inter', sans-serif; font-size: 0.85rem; color: var(--au-ink); font-weight: 500; }
div[data-testid="stTextInput"] { margin-bottom: 0.6rem; }
div[data-testid="stTextInput"] div[data-baseweb="base-input"],
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    background: transparent !important; border: none !important;
    border-bottom: 1.5px solid var(--au-line) !important; border-radius: 0 !important; padding-left: 2px !important; }
div[data-testid="stTextInput"]:focus-within div[data-baseweb="base-input"],
div[data-testid="stTextInput"]:focus-within div[data-baseweb="input"] { border-bottom: 1.5px solid var(--au-red) !important; }
div[data-testid="stTextInput"] input { font-family: 'Inter', sans-serif; color: var(--au-ink) !important; }
div[data-testid="stTextInput"] input:focus { outline: 2px solid var(--au-rose-pale) !important; outline-offset: 2px; }
div[data-testid="InputInstructions"] { display: none !important; }
div[data-testid="stFormSubmitButton"] { width: 100% !important; }
div[data-testid="stFormSubmitButton"] button { width: 100% !important; box-sizing: border-box !important;
    background: var(--au-red) !important; color: var(--au-paper) !important; border: none !important;
    border-radius: 3px !important; font-family: 'Inter', sans-serif; font-weight: 600;
    padding: 0.6rem 0 !important; margin-top: 1rem; }
div[data-testid="stFormSubmitButton"] button:hover { background: var(--au-red-deep) !important; }
div[data-testid="stFormSubmitButton"] button:focus-visible { outline: 2px solid var(--au-rose) !important; outline-offset: 2px; }
.au-foot { text-align: center; margin-top: 1.1rem; font-family: 'Inter', sans-serif;
           font-size: 0.78rem; color: var(--au-muted); }
</style>
"""


def _credentials():
    user, pw = secret("APP_USERNAME"), secret("APP_PASSWORD")
    if not (user and pw):
        user, pw = os.environ.get("APP_USERNAME"), os.environ.get("APP_PASSWORD")
    return (str(user), str(pw)) if user and pw else (None, None)


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_login() -> bool:
    if st.session_state.get("_authed"):
        return True
    exp_user, exp_pass = _credentials()
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        st.markdown('<div class="au-mast"><div class="au-wordmark">AmarUjala</div>'
                    '<div class="au-rule"></div>'
                    '<div class="au-dateline">Paywall insights &middot; internal access</div></div>',
                    unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", **STRETCH)
        st.markdown('<div class="au-foot">Paywall views, clicks and CTR. Every day. One view.</div>',
                    unsafe_allow_html=True)
        if exp_user is None:
            st.error("Login isn't set up: add APP_USERNAME and APP_PASSWORD to secrets.toml "
                     "(or the Streamlit Cloud Secrets box).")
            return False
        if submitted:
            if _same(user.strip(), exp_user) and _same(pw, exp_pass):
                st.session_state["_authed"] = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    return False


def _logout():
    st.session_state["_authed"] = False


# ---------------------------------------------------------------- app theme
APP_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;500;600&display=swap');
header[data-testid="stHeader"] {{ display: none !important; }}
.block-container {{ padding-top: 1.8rem; }}
html, body, [data-testid="stAppViewContainer"] {{ font-family: 'Inter', sans-serif; }}
.au-head {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; min-height: 2.6rem; }}
.au-head .mark {{ font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 2rem;
                  color: {AU["red"]}; line-height: 1.15; }}
.au-head .sep {{ width: 1px; align-self: stretch; background: {AU["line"]}; }}
.au-head .title {{ font-weight: 600; font-size: 1.2rem; color: {AU["ink"]}; line-height: 1.3; }}
.au-head .sub {{ font-size: 0.82rem; color: {AU["muted"]}; line-height: 1.3; }}
.au-rule-full {{ height: 3px; background: {AU["red"]}; margin: 0.35rem 0 0.4rem; border-radius: 2px; }}
div.st-key-logout button {{ border-color: {AU["red"]}; color: {AU["red"]}; }}
div.st-key-logout button:hover {{ background: {AU["red"]}; color: #FFFFFF; }}
h2, h3 {{ color: {AU["ink"]} !important; }}
div[data-testid="stPopover"], div[data-testid="stPopover"] > div {{ width: 100%; }}
div[data-testid="stPopover"] button {{ width: 100%; justify-content: space-between;
    border-color: {AU["line"]}; min-height: 2.5rem; }}
div[data-testid="stPopover"] button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
div[data-testid="stPopover"] button:hover {{ border-color: {AU["red"]}; color: {AU["red"]}; }}
div[data-testid="stMetric"] {{ background: {AU["paper"]}; border: 1px solid {AU["line"]};
    border-left: 4px solid {AU["red"]}; border-radius: 4px; padding: 0.7rem 1rem; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; color: {AU["ink"]}; }}
.au-mode {{ display: inline-block; font-size: 0.8rem; padding: 0.15rem 0.55rem; border-radius: 3px;
            border: 1px solid {AU["line"]}; background: {AU["paper"]}; color: {AU["ink"]}; }}
.au-mode.exact {{ border-color: {AU["up"]}; color: {AU["up"]}; background: #EEF7F1; }}
div.st-key-tab div[role="radiogroup"] {{ gap: 0.25rem; border-bottom: 1px solid {AU["line"]}; }}
div.st-key-tab div[role="radiogroup"] label {{ padding: 0.45rem 1.1rem; border-radius: 0.4rem 0.4rem 0 0; }}
div.st-key-tab div[role="radiogroup"] label:has(input:checked) {{
    background: {AU["rose_wash"]}; font-weight: 600; box-shadow: inset 0 -3px 0 {AU["red"]}; }}
</style>
"""


# ---------------------------------------------------------------- loading
def family(event_type: str) -> str:
    if event_type.startswith("OVERALL"):
        return "Overall"
    if event_type.startswith("EPAPER"):
        return "Epaper"
    if event_type.startswith("ADAPTIVE"):
        return "Adaptive"
    if event_type.startswith("HARD"):
        return "Premium article"
    return "Other"


def clean_text(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.strip()
    empty = s.str.replace(_INVISIBLE, "", regex=True).str.lower().isin(_EMPTY)
    return s.mask(empty, BLANK)


def parse_sheet_url(url: str):
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError("That isn't a Google Sheets link. Paste the link of the tab with the export.")
    g = re.search(r"[#&?]gid=(\d+)", url)
    return m.group(1), (g.group(1) if g else "0")


def key_source():
    if secret("gcp_service_account"):
        return "Streamlit secrets"
    if SERVICE_ACCOUNT_JSON.exists():
        return SERVICE_ACCOUNT_JSON.name
    return None


@st.cache_resource(show_spinner=False)
def sheets_client():
    import json
    import gspread
    info = secret("gcp_service_account")
    if info:
        info = json.loads(info) if isinstance(info, str) else dict(info)
        return gspread.service_account_from_dict(info)
    return gspread.service_account(filename=str(SERVICE_ACCOUNT_JSON))


def fetch_raw(src: str) -> pd.DataFrame:
    local = Path(src)
    if local.suffix.lower() in (".csv", ".xlsx") and local.exists():
        if local.suffix.lower() == ".csv":
            return pd.read_csv(local, dtype=str, keep_default_na=False)
        return pd.read_excel(local, sheet_name=0, dtype=str).fillna("")
    sheet_id, gid = parse_sheet_url(src)
    if key_source():
        ws = sheets_client().open_by_key(sheet_id).get_worksheet_by_id(int(gid))
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame(columns=REQUIRED)
        return pd.DataFrame(values[1:], columns=[h.strip() for h in values[0]])
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=30)
    if r.status_code != 200 or "text/csv" not in r.headers.get("Content-Type", ""):
        raise PermissionError(
            "Google didn't hand over the sheet. Share it as 'Anyone with the link – Viewer', "
            "or add pw_service-account.json next to this file and share the sheet with that account."
        )
    return pd.read_csv(io.BytesIO(r.content), dtype=str, keep_default_na=False)


def fingerprint(raw: pd.DataFrame) -> str:
    return hashlib.md5(raw.to_csv(index=False).encode("utf-8")).hexdigest()


def parse_dates(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[iso] = pd.to_datetime(s[iso].str[:10], errors="coerce", format="%Y-%m-%d")
    if (~iso).any():
        try:
            out[~iso] = pd.to_datetime(s[~iso], errors="coerce", dayfirst=DAYFIRST, format="mixed")
        except (TypeError, ValueError):
            out[~iso] = pd.to_datetime(s[~iso], errors="coerce", dayfirst=DAYFIRST)
    return out.dt.normalize()


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.rename(columns=lambda c: str(c).strip())
    if "isGuest" not in raw.columns and "LoggedIn" in raw.columns:
        raw = raw.rename(columns={"LoggedIn": "isGuest"})
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"The sheet tab is missing columns: {', '.join(missing)}. "
                         "Row 1 must be the export's header row.")
    cols = REQUIRED + (["Magzine"] if "Magzine" in raw.columns else [])
    df = raw[cols].copy()
    df["sheet_row"] = np.arange(len(df)) + 2          # row number in the Google Sheet (row 1 = header)
    df["date"] = parse_dates(df["event_date_ist"])
    df = df.dropna(subset=["date"])
    df["users"] = pd.to_numeric(df["users"].astype(str).str.replace(",", "", regex=False),
                                errors="coerce").fillna(0)
    df["event_type"] = df["event_type"].astype(str).str.strip().str.upper()
    df["action"] = np.where(df["event_type"].str.endswith("CLICK"), "Click", "View")
    df["paywall"] = df["event_type"].map(family)
    dims = [c for c in DIMS if c in df.columns]
    for c in dims:
        df[c] = clean_text(df[c])
        df.loc[df[c].str.upper() == ALL, c] = ALL
    return df


@st.cache_data(ttl=REFRESH_SECONDS * 5, show_spinner="Reading the sheet…")
def load(src: str):
    raw = fetch_raw(src)
    return fingerprint(raw), prepare(raw), time.time()


# ---------------------------------------------------------------- totals
def daily_totals(x: pd.DataFrame, by: tuple = ()) -> pd.DataFrame:
    keys = ["date", *by]
    parts = {}
    for action in ("View", "Click"):
        a = x[x["action"] == action]
        a = a[a["paywall"] == "Overall"] if USE_OVERALL[action] else a[a["paywall"] != "Overall"]
        parts[action] = a.groupby(keys)["users"].sum()
    out = pd.concat(parts, axis=1).fillna(0) if any(len(p) for p in parts.values()) else None
    if out is None:
        idx = pd.MultiIndex.from_arrays([[]] * len(keys), names=keys) if by else pd.Index([], name="date")
        return pd.DataFrame({"View": [], "Click": []}, index=idx)
    return out.reindex(columns=["View", "Click"], fill_value=0)


def totals_label() -> str:
    return "Overall (distinct)" if any(USE_OVERALL.values()) else "Total"


# ---------------------------------------------------------------- checkbox filter
def checkbox_filter(label: str, options: list, key: str) -> list:
    all_key = f"{key}__all"
    st.session_state.setdefault(all_key, True)
    for o in options:
        st.session_state.setdefault(f"{key}::{o}", st.session_state[all_key])

    def on_all():
        for o in options:
            st.session_state[f"{key}::{o}"] = st.session_state[all_key]

    def on_one():
        st.session_state[all_key] = all(st.session_state[f"{key}::{o}"] for o in options)

    chosen = [o for o in options if st.session_state[f"{key}::{o}"]]
    if st.session_state[all_key] or len(chosen) == len(options):
        summary = "All"
    elif not chosen:
        summary = "None"
    elif len(chosen) == 1:
        summary = chosen[0]
    else:
        summary = f"{len(chosen)} of {len(options)}"

    try:
        pop = st.popover(f"{label}: {summary}", **STRETCH)
    except TypeError:
        pop = st.popover(f"{label}: {summary}")
    with pop:
        st.checkbox("Select all", key=all_key, on_change=on_all)
        shown = options
        if len(options) > 10:
            q = st.text_input("Search", key=f"{key}__q", placeholder="Search…",
                              label_visibility="collapsed")
            shown = [o for o in options if q.lower() in o.lower()]
        for o in shown:
            st.checkbox(o, key=f"{key}::{o}", on_change=on_one)
    return chosen


def ordered(series: pd.Series, weights: pd.Series | None = None) -> list:
    if weights is not None:
        vals = list(weights.groupby(series).sum().sort_values(ascending=False).index)
    else:
        vals = sorted(series.unique())
    return [v for v in vals if v != BLANK] + [v for v in vals if v == BLANK]


# ---------------------------------------------------------------- chart helpers
ZOOM_HINT = ("Page scrolls normally over the charts. To zoom dates: hold Shift and scroll · drag to pan · "
             "double-click to reset · hover a day to read every value.")


def _zoom():
    return alt.selection_interval(bind="scales", encodings=["x"],
                                  zoom="wheel![event.shiftKey]")


def _x_axis(n_days: int) -> alt.Axis:
    kw = dict(format="%d %b", labelAngle=0, grid=True, title=None, labelOverlap=True)
    if n_days <= LABEL_MAX_DAYS:
        kw["tickCount"] = "day"
    return alt.Axis(**kw)


def _x_scale(days: pd.DatetimeIndex) -> alt.Scale:
    pad = pd.Timedelta(hours=14)
    return alt.Scale(domain=[(days[0] - pad).isoformat(), (days[-1] + pad).isoformat()])


def _au_look(chart, height: int):
    return (chart.properties(
                height=height, width="container",
                autosize=alt.AutoSizeParams(type="fit-x", contains="padding", resize=False))
            .configure(font="Inter, sans-serif")
            .configure_view(strokeWidth=0)
            .configure_axis(gridColor=AU["line"], gridDash=[2, 3], domainColor=AU["line"],
                            tickColor=AU["line"], labelColor=AU["muted"], titleColor=AU["ink"],
                            labelFontSize=11, titleFontSize=12, titleFontWeight=500)
            .configure_legend(orient="top", labelColor=AU["ink"], labelFontSize=12,
                              symbolType="square", symbolSize=140, columnPadding=18, labelLimit=0))


def dod_bars(d: pd.DataFrame, days: pd.DatetimeIndex, action: str, title: str, key: str,
             total: pd.Series):
    st.subheader(title)
    sub = d[d["action"] == action]
    if sub.empty:
        st.info(f"No {action.lower()} events in the selection — tick a *_{action.upper()} event type.")
        return
    stack = sub[sub["paywall"] != "Overall"]
    only_overall = stack.empty
    if only_overall:
        stack = sub
    marker = USE_OVERALL[action] and not only_overall
    piv = (stack.pivot_table(index="date", columns="event_type", values="users", aggfunc="sum", fill_value=0)
           .reindex(days, fill_value=0))
    events = list(piv.sum().sort_values(ascending=False).index)
    piv = piv[events]
    total = total.reindex(days, fill_value=0)
    change = total.pct_change().replace([np.inf, -np.inf], np.nan)

    half = pd.Timedelta(hours=9.5)
    tops = piv.cumsum(axis=1)
    long = pd.concat([pd.DataFrame({"date": days, "x0": days - half, "x1": days + half,
                                    "event_type": e, "users": piv[e].values,
                                    "y0": (tops[e] - piv[e]).values, "y1": tops[e].values})
                      for e in events], ignore_index=True)
    wide = piv.rename_axis("date").reset_index()
    wide["x0"], wide["x1"] = (days - half), (days + half)
    wide["Total"] = total.values
    wide["dod"] = change.values
    wide["DoD"] = ["–" if pd.isna(c) else f"{c:+.1%}" for c in change]
    wide["dod_color"] = [AU["muted"] if pd.isna(c) or c == 0 else AU["up"] if c > 0 else AU["red_deep"]
                         for c in change]

    axis = _x_axis(len(days))
    xs = _x_scale(days)
    x = alt.X("date:T", axis=axis, title=None, scale=xs)
    top = max(float(piv.sum(axis=1).max() or 0), float(total.max() or 0)) or 1
    y_max = top * (1.2 if len(days) <= LABEL_MAX_DAYS else 1.05)
    yscale = alt.Scale(domain=[0, y_max], nice=False)
    color = alt.Color("event_type:N", title=None, sort=events, legend=alt.Legend(orient="top"),
                      scale=alt.Scale(domain=events, range=[FAMILY_COLOR[family(e)] for e in events]))

    zoom = _zoom()
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover",
                                clear="pointerout", empty=False)

    bars = (alt.Chart(long).mark_bar(clip=True)
            .encode(x=alt.X("x0:T", axis=axis, title=None, scale=xs), x2="x1:T",
                    y=alt.Y("y0:Q", title="Users", scale=yscale, axis=alt.Axis(format="~s")), y2="y1:Q",
                    color=color)
            .add_params(zoom))
    layers = [bars]
    if marker:
        layers.append(alt.Chart(wide).mark_rule(color=AU["maroon"], strokeWidth=3, clip=True)
                      .encode(x=alt.X("x0:T", scale=xs), x2="x1:T", y=alt.Y("Total:Q", scale=yscale)))
    if len(days) <= LABEL_MAX_DAYS:
        layers.append(alt.Chart(wide).mark_text(dy=-14, baseline="bottom", fontSize=11, fontWeight=500,
                                                color=AU["ink"], clip=True)
                      .encode(x=x, y=alt.Y("label_y:Q", scale=yscale), text=alt.Text("Total:Q", format=",.0f"))
                      .transform_calculate(label_y=f"max(datum.Total, {'+'.join(f'datum[{e!r}]' for e in events)})"))
        layers.append(alt.Chart(wide).mark_text(dy=-2, baseline="bottom", fontSize=10, clip=True)
                      .encode(x=x, y=alt.Y("label_y:Q", scale=yscale), text="DoD:N",
                              color=alt.Color("dod_color:N", scale=None, legend=None))
                      .transform_calculate(label_y=f"max(datum.Total, {'+'.join(f'datum[{e!r}]' for e in events)})"))
    tlabel = "Overall (distinct)" if USE_OVERALL[action] else "Total"
    tips = ([alt.Tooltip("date:T", title="Day", format="%a, %d %b %Y")]
            + [alt.Tooltip(f"{e}:Q", title=e, format=",.0f") for e in events]
            + [alt.Tooltip("Total:Q", title=tlabel, format=",.0f"), alt.Tooltip("DoD:N", title="DoD change")])
    layers.append(alt.Chart(wide).mark_rule(color=AU["muted"], strokeWidth=1, clip=True)
                  .encode(x=x, opacity=alt.condition(hover, alt.value(0.55), alt.value(0)), tooltip=tips)
                  .add_params(hover))
    st.altair_chart(_au_look(alt.layer(*layers), 380), key=key, **STRETCH)
    if marker:
        st.caption("Dark line on each bar = overall distinct users, the number on top. Someone who met two "
                   "paywalls that day counts once, so the line can sit below the top of the stack.")


def ctr_line(d: pd.DataFrame, days: pd.DatetimeIndex, daily_tot: pd.DataFrame):
    st.subheader("Click-through rate by day")
    fam = (d[d["paywall"] != "Overall"].groupby(["date", "paywall", "action"])["users"].sum()
           .unstack(fill_value=0).reindex(columns=["View", "Click"], fill_value=0))
    series = {}
    for name in FAMILY_COLOR:
        if name == "Overall" or fam.empty or name not in fam.index.get_level_values("paywall"):
            continue
        s = fam.xs(name, level="paywall").reindex(days, fill_value=0)
        if s["View"].sum() and s["Click"].sum():
            series[name] = s
    total_name = "Overall" if all(USE_OVERALL.values()) else "All selected"
    series[total_name] = daily_tot
    names = list(series)
    colors = [FAMILY_COLOR.get(n, AU["muted"]) for n in names]

    frames, wide = [], pd.DataFrame({"date": days})
    for n, s in series.items():
        ctr = (s["Click"] / s["View"].replace(0, np.nan)).values
        frames.append(pd.DataFrame({"date": days, "series": n, "ctr": ctr}))
        wide[n] = [("–" if pd.isna(r) else f"{r:.2%}  ({c:,.0f} / {v:,.0f})")
                   for r, c, v in zip(ctr, s["Click"].values, s["View"].values)]
    long = pd.concat(frames, ignore_index=True)

    x = alt.X("date:T", axis=_x_axis(len(days)), title=None, scale=_x_scale(days))
    y = alt.Y("ctr:Q", title="CTR", axis=alt.Axis(format=".1%"), scale=alt.Scale(zero=True))
    color = alt.Color("series:N", title=None, sort=names, legend=alt.Legend(orient="top", symbolType="stroke"),
                      scale=alt.Scale(domain=names, range=colors))
    dash = alt.StrokeDash("series:N", sort=names, legend=None,
                          scale=alt.Scale(domain=names,
                                          range=[[5, 3] if n == total_name else [1, 0] for n in names]))
    zoom = _zoom()
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover",
                                clear="pointerout", empty=False)

    lines = (alt.Chart(long).mark_line(strokeWidth=2.5, clip=True, interpolate="linear")
             .encode(x=x, y=y, color=color, strokeDash=dash).add_params(zoom))
    points = (alt.Chart(long).mark_circle(size=60, clip=True)
              .encode(x=x, y=y, color=color,
                      opacity=alt.condition(hover, alt.value(1), alt.value(0))))
    tips = ([alt.Tooltip("date:T", title="Day", format="%a, %d %b %Y")]
            + [alt.Tooltip(f"{n}:N", title=n) for n in names])
    rule = (alt.Chart(wide).mark_rule(color=AU["muted"], strokeWidth=1, clip=True)
            .encode(x=x, opacity=alt.condition(hover, alt.value(0.55), alt.value(0)), tooltip=tips)
            .add_params(hover))
    st.altair_chart(_au_look(alt.layer(lines, points, rule), 340), key="ctr_line", **STRETCH)
    st.caption("Each paywall line needs both its view and click event ticked. Days with few viewers swing a lot. "
               + ZOOM_HINT)


def shade_totals(styler, label="Total"):
    wash = f"background-color: {AU['rose_wash']}; font-weight: 600"
    return (styler
            .apply(lambda r: [wash] * len(r) if r.name == label else [""] * len(r), axis=1)
            .apply(lambda c: [wash] * len(c) if c.name == label else [""] * len(c), axis=0))


def category_frames(dc: pd.DataFrame):
    ct = daily_totals(dc, ("Category",))
    if ct.empty:
        return pd.DataFrame(), pd.DataFrame()
    v = ct["View"].unstack("Category", fill_value=0)
    c = ct["Click"].unstack("Category", fill_value=0)
    return v, c


# ---------------------------------------------------------------- week-over-week helpers
def growth(cur: pd.DataFrame, prev: pd.DataFrame, pct_cols: set) -> pd.DataFrame:
    prev = prev.set_axis(cur.index)
    g = cur / prev.where(prev != 0) - 1
    for c in pct_cols & set(cur.columns):
        g[c] = cur[c] - prev[c]
    return g


def wow_display(values: pd.DataFrame, g: pd.DataFrame, mode: str, pct_cols: set):
    disp = pd.DataFrame("", index=values.index, columns=values.columns, dtype=object)
    css = pd.DataFrame("", index=values.index, columns=values.columns, dtype=object)
    for c in values.columns:
        is_pct = c in pct_cols
        for i in values.index:
            v, gv = values.at[i, c], g.at[i, c]
            vtxt = "–" if pd.isna(v) else (f"{v:.2%}" if is_pct else f"{v:,.0f}")
            if pd.isna(gv):
                gtxt = "–"
            else:
                arrow = "▲" if gv > 0 else "▼" if gv < 0 else "■"
                gtxt = f"{arrow} {abs(gv) * 100:.2f} pp" if is_pct else f"{arrow} {abs(gv):.1%}"
                if mode != "Value" and gv != 0:
                    css.at[i, c] = f"color: {AU['up'] if gv > 0 else AU['red_deep']}"
            disp.at[i, c] = (vtxt if mode == "Value" else gtxt if mode == "WoW %"
                             else vtxt if pd.isna(gv) else f"{vtxt}   {gtxt}")
    return disp, css


def show_wow(values: pd.DataFrame, g: pd.DataFrame, mode: str, pct_cols: set, fname: str, key: str):
    disp, css = wow_display(values, g, mode, pct_cols)
    labels = [f"{pd.Timestamp(i):%a, %d %b %Y}" for i in values.index]
    disp.index, css.index = labels, labels
    disp.index.name = "Date"
    st.dataframe(disp.style.apply(lambda _: css, axis=None), height=min(38 * (len(disp) + 1), 640),
                 **STRETCH)
    out = values.join(g.add_suffix(" · WoW"))
    out.index = [f"{pd.Timestamp(i):%Y-%m-%d}" for i in out.index]
    st.download_button("Download as CSV", out.to_csv(index_label="date").encode("utf-8"),
                       file_name=fname, mime="text/csv", key=f"{key}_dl")


# ---------------------------------------------------------------- views
def render_trends(d: pd.DataFrame, dc: pd.DataFrame, days: pd.DatetimeIndex, end):
    daily_tot = daily_totals(d).reindex(days, fill_value=0)
    views, clicks = daily_tot["View"].sum(), daily_tot["Click"].sum()
    ctr_daily = daily_tot["Click"] / daily_tot["View"].replace(0, np.nan)

    def dod(s: pd.Series):
        if len(s) < 2 or s.iloc[-2] == 0:
            return None
        return f"{(s.iloc[-1] / s.iloc[-2] - 1):+.1%} DoD"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Paywall viewers", f"{views:,.0f}", dod(daily_tot["View"]))
    k2.metric("Paywall clickers", f"{clicks:,.0f}", dod(daily_tot["Click"]))
    k3.metric("CTR", f"{clicks / views:.2%}" if views else "–",
              None if len(ctr_daily.dropna()) < 2
              else f"{(ctr_daily.iloc[-1] - ctr_daily.iloc[-2]) * 100:+.2f} pp DoD")
    k4.metric("Last day in range", f"{end:%d %b}")

    dod_bars(d, days, "View", "Paywall views — day on day", "bars_view", daily_tot["View"])
    dod_bars(d, days, "Click", "Paywall clicks — day on day", "bars_click", daily_tot["Click"])
    st.caption(ZOOM_HINT)
    ctr_line(d, days, daily_tot)

    st.subheader("By category and day")
    st.caption("Blank = rows where Category is empty in the data OR for e-paper")
    metric = st.radio("Show", ["Viewers", "Clickers", "CTR"], horizontal=True, key="tr_metric",
                      label_visibility="collapsed")
    v, c = category_frames(dc)
    if v.empty and c.empty:
        st.info("No category rows match these filters.")
        return
    cats = list(v.sum().add(c.sum(), fill_value=0).sort_values(ascending=False).index)
    v = v.reindex(index=days, columns=cats, fill_value=0)
    c = c.reindex(index=days, columns=cats, fill_value=0)
    if metric == "CTR":
        table = (c / v.replace(0, np.nan)) * 100
        fmt = "{:.1f}%"
    else:
        table = (v if metric == "Viewers" else c).copy()
        fmt = "{:,.0f}"
    table.index = table.index.strftime("%a, %d %b %Y")
    table.index.name = "Date"
    st.dataframe(table.style.format(fmt, na_rep="–"),
                 height=min(38 * (len(table) + 1), 760), **STRETCH)
    st.download_button("Download table as CSV", table.to_csv().encode("utf-8"),
                       file_name=f"paywall_{metric.lower()}_by_category.csv", mime="text/csv")


def render_wow(dd: pd.DataFrame, ddc: pd.DataFrame, start, end):
    ss = st.session_state
    if ss.get("wow_day") not in WEEKDAYS:
        ss["wow_day"] = WEEKDAYS[pd.Timestamp(end).dayofweek]
    c1, c2 = st.columns([1, 2])
    day = c1.selectbox("Weekday", WEEKDAYS, key="wow_day")
    mode = c2.radio("Show", ["Value + WoW", "Value", "WoW %"], horizontal=True, key="wow_mode")

    rows = [x for x in pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
            if x.dayofweek == WEEKDAYS.index(day)]
    if not rows:
        st.info(f"The date range has no {day}. Widen it in the date filter above.")
        return
    rows = pd.DatetimeIndex(rows)
    prev = rows - pd.Timedelta(days=7)
    st.caption(f"Every {day} in the date range, oldest first. WoW compares each row with the "
               f"{day} one week earlier — counted even when that week is before the range. "
               "Rates (CTR) change in percentage points. Green = up, red = down.")
    act = daily_totals(dd)
    tlabel = totals_label()

    st.subheader(f"By event type · {day}s")
    ev = dd.pivot_table(index="date", columns="event_type", values="users", aggfunc="sum", fill_value=0)
    ev = ev[ev.sum().sort_values(ascending=False).index] if not ev.empty else ev

    def ev_frame(idx):
        f = ev.reindex(idx, fill_value=0).copy()
        a = act.reindex(idx, fill_value=0)
        f[f"{tlabel} views"] = a["View"].values
        f[f"{tlabel} clicks"] = a["Click"].values
        f["CTR"] = (a["Click"] / a["View"].replace(0, np.nan)).values
        return f

    cur, before = ev_frame(rows), ev_frame(prev)
    show_wow(cur, growth(cur, before, {"CTR"}), mode, {"CTR"},
             f"paywall_wow_event_type_{day.lower()}.csv", "wow_ev")

    st.subheader(f"By category · {day}s")
    metric = st.radio("Measure", ["Viewers", "Clickers", "CTR"], horizontal=True, key="wow_cat_metric")
    v, c = category_frames(ddc)
    if v.empty and c.empty:
        st.info("No category rows match these filters.")
        return
    cats = list(v.sum().add(c.sum(), fill_value=0).sort_values(ascending=False).index)

    def cat_frame(idx):
        vv = v.reindex(index=idx, columns=cats, fill_value=0)
        cc = c.reindex(index=idx, columns=cats, fill_value=0)
        a = act.reindex(idx, fill_value=0)
        if metric == "CTR":
            f = cc / vv.replace(0, np.nan)
            f["Total"] = (a["Click"] / a["View"].replace(0, np.nan)).values
        else:
            f = (vv if metric == "Viewers" else cc).copy()
            f["Total"] = (a["View"] if metric == "Viewers" else a["Click"]).values
        return f

    cur, before = cat_frame(rows), cat_frame(prev)
    pct = set(cur.columns) if metric == "CTR" else set()
    show_wow(cur, growth(cur, before, pct), mode, pct,
             f"paywall_wow_category_{metric.lower()}_{day.lower()}.csv", "wow_cat")
    st.caption("Blank = rows where Category is empty in the data. "
               "Total = the day's unique users across all categories.")


# ================================================================ page
if not require_login():
    st.stop()

for k in PERSIST_KEYS:
    if k in st.session_state:
        st.session_state[k] = st.session_state[k]

st.markdown(APP_CSS, unsafe_allow_html=True)
try:
    h1, h2 = st.columns([7, 1], vertical_alignment="center")
except TypeError:
    h1, h2 = st.columns([7, 1])
h1.markdown(f'<div class="au-head"><span class="mark">AmarUjala</span><span class="sep"></span>'
            f'<div><div class="title">{APP_TITLE}</div><div class="sub">{APP_SUB}</div></div></div>',
            unsafe_allow_html=True)
h2.button("Log out", on_click=_logout, key="logout", **STRETCH)
st.markdown('<div class="au-rule-full"></div>', unsafe_allow_html=True)

if secret("sheet_url"):
    src = SHEET_URL
else:
    with st.expander("Data source", expanded=False):
        src = st.text_input("Google Sheet link (of the tab with the export)", value=SHEET_URL,
                            help="Copy the link while the export tab is open so it ends in #gid=…")
        st.caption(f"Reading with {key_source()}." if key_source() else
                   "Private sheet? Add pw_service-account.json next to this file and share the sheet with it.")

try:
    data_hash, df, fetched_at = load(src)
except Exception as e:
    st.error(str(e))
    st.stop()
st.session_state["data_hash"] = data_hash
st.session_state["checked_at"] = max(st.session_state.get("checked_at", 0), fetched_at)
if df.empty:
    st.warning("The sheet has no rows with a valid date yet.")
    st.stop()


@st.fragment(run_every=REFRESH_SECONDS)
def live_status(source: str):
    if time.time() - st.session_state.get("checked_at", 0) >= REFRESH_SECONDS - 2:
        try:
            raw = fetch_raw(source)
            st.session_state["checked_at"] = time.time()
            if fingerprint(raw) != st.session_state.get("data_hash"):
                load.clear()
                st.rerun()
        except Exception as e:
            st.caption(f"Couldn't check the sheet just now: {e}")


# ---------------------------------------------------------------- repeated rows
# A repeat = same parsed date + event_type + every filter column (Magzine included).
KEY = ["date", "event_type", *[c for c in DIMS if c in df.columns]]
rep = df[df.duplicated(subset=KEY, keep=False)].sort_values([*KEY, "sheet_row"])
dupes = int(df.duplicated(subset=KEY).sum())
df = df.drop_duplicates(subset=KEY, keep="last")    # newest copy wins, never double-counted

top = st.columns([3, 1.6, 1])
top[0].caption(f"{len(df):,} rows · {df['date'].min():%d %b %Y} to {df['date'].max():%d %b %Y}")
with top[1]:
    live_status(src)
if top[2].button("Refresh now", **STRETCH):
    load.clear()
    st.rerun()
if dupes:
    st.warning(f"{dupes:,} rows repeat an earlier row for the same day and slice. Only the last copy "
               "is used, so nothing is double-counted. Delete the older copy in the sheet.")
    with st.expander("Show repeated rows"):
        st.dataframe(rep[["sheet_row", "event_date_ist", *KEY[1:], "users"]],
                     hide_index=True, **STRETCH)

tab = st.radio("View", [TAB_TRENDS, TAB_WOW], horizontal=True, key="tab", label_visibility="collapsed")

# ---------------------------------------------------------------- filters
dmin, dmax = df["date"].min().date(), df["date"].max().date()
prev_max = st.session_state.get("_dmax")
r = st.session_state.get("rng")
if isinstance(r, (tuple, list)) and len(r) == 2:
    s0, e0 = r
    if prev_max is not None and e0 == prev_max:
        e0 = dmax
    st.session_state["rng"] = (min(max(s0, dmin), dmax), min(max(e0, dmin), dmax))
elif r is None:
    st.session_state["rng"] = (dmin, dmax)
st.session_state["_dmax"] = dmax

dims = [c for c in DIMS if c in df.columns]
shown_dims = [c for c in dims if (df[c] != ALL).any()]
ev_opts = ordered(df["event_type"], df["users"])

n_rows = -(-(len(shown_dims) + 2) // FILTER_COLS)
slots = [c for _ in range(n_rows) for c in st.columns(FILTER_COLS)]
with slots[0]:
    rng = st.date_input("Date range", min_value=dmin, max_value=dmax, key="rng",
                        label_visibility="collapsed")
start, end = (rng[0], rng[-1]) if isinstance(rng, (tuple, list)) and rng else (dmin, dmax)
with slots[1]:
    sel_ev = checkbox_filter("event_type", ev_opts, "ev")

opts, sel = {}, {}
for col, box in zip(shown_dims, slots[2:]):
    pool = df[df[col] != ALL]
    if col == "Sub_Category" and "Category" in sel and set(sel["Category"]) != set(opts["Category"]):
        pool = pool[pool["Category"].isin(sel["Category"])]
    opts[col] = ordered(pool[col], pool["users"])
    with box:
        sel[col] = checkbox_filter(col, opts[col], f"f_{col}")

# which value(s) each column must have in the sheet: ALL when every box is ticked
spec = {c: ({ALL} if c not in opts or set(sel[c]) == set(opts[c]) else set(sel[c])) for c in dims}
if "Sub_Category" in spec and spec["Sub_Category"] != {ALL} and spec.get("Category") == {ALL}:
    spec["Category"] = set(opts["Category"])          # sub-category rows only exist under a category
cat_spec = dict(spec)
if cat_spec.get("Category") == {ALL}:
    cat_spec["Category"] = set(opts.get("Category", []))


def pick(s: dict) -> pd.DataFrame:
    m = df["event_type"].isin(sel_ev)
    for c in dims:
        m &= df[c].isin(s[c])
    return df[m]


def overall_ok(action: str) -> bool:
    suffix = action.upper()
    ov = [e for e in ev_opts if e.endswith(suffix) and family(e) == "Overall"]
    fams = {e for e in ev_opts if e.endswith(suffix) and family(e) != "Overall"}
    picked = {e for e in sel_ev if e in fams}
    return any(e in sel_ev for e in ov) and (not picked or picked == fams)


USE_OVERALL.update({a: overall_ok(a) for a in ("View", "Click")})

dd, ddc = pick(spec), pick(cat_spec)


def in_range(x):
    return x[x["date"].between(pd.Timestamp(start), pd.Timestamp(end))]


d, dc = in_range(dd), in_range(ddc)
days = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
exact = d.empty or d.groupby(["date", "event_type"]).size().max() <= 1

if exact:
    st.markdown('<span class="au-mode exact">Exact unique users</span>', unsafe_allow_html=True)
    st.caption("Each filter is on All or one value, so every number is read from the sheet row for exactly "
               "that slice: each user counts once per day and event type.")
else:
    st.markdown('<span class="au-mode">Several values ticked: slices added up</span>', unsafe_allow_html=True)
    st.caption("A filter has more than one (but not every) value ticked, so the rows for each value are added "
               "up: a user in two ticked values counts twice. Tick one value or All for exact unique users.")
st.caption("Across days, viewers and clickers are added up, so read multi-day totals as user-days. "
           "CTR = clickers ÷ viewers.")

if d.empty:
    st.info("No rows match these filters. Widen the date range or tick more boxes.")
    st.stop()

if tab == TAB_TRENDS:
    render_trends(d, dc, days, end)
else:
    render_wow(dd, ddc, start, end)
