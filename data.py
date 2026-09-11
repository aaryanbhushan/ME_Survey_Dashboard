"""Mart reads and every aggregation the pages draw.

The two marts are pulled once into module-level frames and every page
computes from those. Nothing here goes back to the database per callback —
the tunnel makes a round trip expensive enough that a 560k-row read once at
startup beats a 5k-row read per interaction.

Every aggregation names the DAX measure it reproduces, so a number on screen
can be traced to the retired report.
"""
import functools
import threading

import numpy as np
import pandas as pd

from db import get_db

_lock = threading.RLock()
_responses = None
_managers = None
_joined = None

# Every aggregation below is a pure function of the cycle over frames that do
# not change between refreshes, and a single page render asks for the same
# ones repeatedly — the Pulse hero alone wants themes() three times. Uncached,
# one render took 36 seconds; cached it is a few hundred milliseconds after
# the first hit. flush() clears these alongside the frames.
_CACHES = []


def _cached(fn):
    wrapped = functools.lru_cache(maxsize=None)(fn)
    _CACHES.append(wrapped)
    return wrapped

# Cycles in chronological order. Aug_23 and Mar_24 are excluded upstream, as
# the PBIP's own source query excluded them.
CYCLE_ORDER = ['Sep_24', 'Mar_25', 'Sep_25', 'Mar_26', 'Sep_26']
CYCLE_LABEL = {'Sep_24': 'Sep 24', 'Mar_25': 'Mar 25', 'Sep_25': 'Sep 25',
               'Mar_26': 'Mar 26', 'Sep_26': 'Sep 26'}

_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
           'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}


def cycle_start(cycle):
    """First of the month a cycle is named for, e.g. Sep_26 -> 2026-09-01.

    Read off the cycle name rather than kept in a table, so a new cycle needs
    no maintenance. It is only ever used to ask "was this person employed
    yet?", where being a few weeks out cannot change the answer — the source
    has no reliable fieldwork date to use instead (`refreshed_date` is NULL
    for the whole of Sep_26, and `end_date` is free text in four different
    formats).
    """
    try:
        mon, yr = cycle.split('_')
        return pd.Timestamp(2000 + int(yr), _MONTHS[mon[:3].lower()], 1)
    except Exception:
        return None

# The 1-4 scale's midpoint bands, used for the RAG chips. These mirror the
# red-amber-green gradient the PBIP applied to Theme Score and NPS in its
# pivot tables, cut into four legible steps.
ME_BANDS = [(3.60, 'b-good'), (3.46, 'b-ok'), (3.20, 'b-warn'), (-1e9, 'b-bad')]
NPS_BANDS = [(55, 'b-good'), (40, 'b-ok'), (0, 'b-warn'), (-1e9, 'b-bad')]

# The recommendation question's 0-10 answer, cut into the three NPS groups.
# Straight off the PBIP's Promoter_Detractor calculated column: 9 or 10 are
# Promoters, 7 or 8 Passives, everything else a Detractor. Kept so the
# promoter-mix legend can state each range rather than assume the reader
# knows it.
#
# There were also ladder strings here ("0–6 → 7–8 → 9–10") for a
# band-movement panel that tracked repeat responders between these groups.
# That panel is gone: reading it began with learning what a band was, which
# is too much to ask of a chart. The mix shares carry the same story.
NPS_BAND_RANGE = {'Promoter': '9–10', 'Passive': '7–8',
                  'Detractor': '0–6'}
NPS_BAND_ORDER = ['Promoter', 'Passive', 'Detractor']

# The dimensions the Cuts view offers. Mirrors the allow-list on the PBIP's
# Dimension slicer, which unpivoted DIM_EMPLOYEE. Every one describes the
# MANAGER being rated except reportee gender, because DIM_EMPLOYEE's active
# relationship in the model was employee_email -> the manager column.
DIMENSIONS = {
    'Business unit':  'manager_bu',
    'Department':     'manager_department',
    'Team':           'manager_team',
    'Grade':          'manager_grade',
    'Grade bucket':   'manager_grade_bucket',
    'Manager gender': 'manager_gender',
    'PMS rating':     'manager_latest_rating',
    'Manager tenure': 'manager_tenure_bucket',
    'Mandate':        'manager_mandate',
    'Designation':    'manager_designation',
    'Reportee gender': 'reportee_gender',
}

# The dropdowns the filter bar offers, in bar order. Column -> label. Every
# one describes the MANAGER being rated except reportee gender, because
# DIM_EMPLOYEE's active relationship in the retired model was
# employee_email -> the manager column.
FILTER_FIELDS = [
    ('manager_bu',            'BU'),
    ('manager_department',    'Department'),
    ('manager_team',          'Team'),
    ('manager_grade',         'Grade'),
    ('manager_grade_bucket',  'Grade bucket'),
    ('manager_gender',        'Manager gender'),
    ('reportee_gender',       'Reportee gender'),
    ('manager_latest_rating', 'PMS rating'),
    ('manager_tenure_bucket', 'Manager tenure'),
    ('manager_mandate',       'Mandate'),
    ('theme',                 'Theme'),
    ('manager_email',         'Manager'),
]

# The heat map's cuts, matching the PBIP's Questions Heat Map page exactly.
#
# That page pivots on Dimension[Attribute], where `Dimension` is DIM_EMPLOYEE
# unpivoted, and its slicer offers: BU, Department, Gender, grade,
# Grade_bucket, Latest_Rating, mandate, Team, Tenure Bucket. Latest_Rating is
# deliberately dropped here.
#
# "Gender" is singular and means the MANAGER's, because Dimension joins the
# fact on employee_email -> Custom_Data_2 (the manager). Reportee gender is an
# addition of ours and has no place on this page.
HEATMAP_DIMENSIONS = {
    'BU':            'manager_bu',
    'Department':    'manager_department',
    'Gender':        'manager_gender',
    'Grade':         'manager_grade',
    'Grade bucket':  'manager_grade_bucket',
    'Mandate':       'manager_mandate',
    'Team':          'manager_team',
    'Tenure bucket': 'manager_tenure_bucket',
}

# Every value of a cut becomes a column, as in the report. Six of the eight
# cuts have 14 values or fewer, so they show in full. Department (89) and Team
# (247) do not: the report is a virtualised pivot that can afford 247 columns,
# this is an HTML table that would emit ~10,000 cells. Those two are capped by
# response volume and the table says so.
HEATMAP_MAX_COLS = 30

# Tenure buckets mix months and years, so no rule derived from the text can
# order them ("3 yrs & Above" sorts before "3-6 Months" either way). This is
# the ladder from the report's own Tenure Bucket expression, in its order.
TENURE_ORDER = ['0-3 Months', '3-6 Months', '6 Months-1 yr',
                '1-2 yr', '2-3 yr', '3 yrs & Above']


def label_sort_key(label):
    """Order a cut's values the way a reader expects to see them.

    Plain text sorting reads badly on exactly the cuts people look at most:
    grade 10 lands before grade 4, and "11 & Above" before "3 & Below". The
    report solves this with hand-maintained sort columns; reading the leading
    number off the value gets the same order for grades and grade buckets with
    no table to keep in step.

    Tenure buckets are the exception that no text rule can order, because they
    mix months and years — "3 yrs & Above" sorts before "3-6 Months" whichever
    way you cut it. Those are matched against the report's own ladder first.
    """
    s = str(label)
    if s in TENURE_ORDER:
        return (0, TENURE_ORDER.index(s), '')
    head = ''
    for ch in s:
        if ch.isdigit():
            head += ch
        else:
            break
    if head:
        return (1, int(head), s.lower())
    return (2, 0, s.lower())


# Cuts whose values carry a meaningful order of their own, so the table reads
# better in it than biggest-first. Everything else (BU, Department, Team,
# gender, mandate) has no inherent order, and there the largest segments are
# the ones worth seeing first.
ORDERED_DIMENSIONS = {'Grade', 'Grade bucket', 'Manager tenure', 'PMS rating'}

# Rows shown in the Cuts table before it stops being readable. Only Team
# (247 values) and Department (89) ever reach it; the other nine cuts have
# twelve values or fewer and show in full.
MAX_SEGMENT_ROWS = 30

# The org's own containment chain, and the only dimensions where drilling
# means anything: a department sits inside a business unit and a team inside a
# department. Grade or gender have no "within", so those rows get no drill.
DRILL_NEXT = {
    'Business unit': 'Department',
    'Department':    'Team',
}

HIERARCHIES = {
    'Manager': [('L8', 'mgr_l8_email'), ('L7', 'mgr_l7_email'),
                ('L6', 'mgr_l6_email'), ('L5', 'mgr_l5_email')],
    'HRBP':    [('L6', 'hrbp_l6_email'), ('L5', 'hrbp_l5_email'),
                ('L4', 'hrbp_l4_email')],
}

# Columns reachable by clicking a value in a table, but deliberately NOT
# offered as dropdowns in the bar. The hierarchy node columns hold ~300
# emails each; as pickers they would add seven 300-option selects to every
# page payload, but as a click target "show me everything under this leader"
# is one of the most useful cuts on the page.
XFILTER_ONLY = [
    ('mgr_l8_email',  'Leader L8'),
    ('mgr_l7_email',  'Leader L7'),
    ('mgr_l6_email',  'Leader L6'),
    ('mgr_l5_email',  'Leader L5'),
    ('hrbp_l6_email', 'HRBP L6'),
    ('hrbp_l5_email', 'HRBP L5'),
    ('hrbp_l4_email', 'HRBP L4'),
]

# Everything the query string may carry as a filter. subset() can narrow on
# any column in the frame, so the only thing that makes a column filterable
# is appearing here for parse_filters to read.
ALL_FILTER_FIELDS = FILTER_FIELDS + XFILTER_ONLY
FILTER_LABEL = dict(ALL_FILTER_FIELDS)


# ── loading ───────────────────────────────────────────────────────────────

def marts_exist():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                select count(*) from information_schema.tables
                where table_schema = 'marts'
                  and table_name in ('mart_me_responses', 'mart_me_manager_cycle')
            """)
            return cur.fetchone()[0] == 2
    except Exception:
        return False


def preload():
    responses()
    managers()
    # Warm the picklists too. Built lazily they land on the first page render
    # instead — twelve distinct-value scans over 563k rows, which put the
    # first load at 28 seconds while every later one was instant.
    for _col, _label in FILTER_FIELDS:
        options(_col)


def responses():
    global _responses
    with _lock:
        if _responses is None:
            _responses = pd.read_sql(
                'select * from marts.mart_me_responses', get_db())
            _responses['cycle'] = pd.Categorical(
                _responses['cycle'], categories=CYCLE_ORDER, ordered=True)
    return _responses


def joined():
    """employee_email -> group_date_of_joining.

    Needed because both hierarchy tables are a CURRENT snapshot of the org.
    Rolling a historical cycle up through today's reporting line credits that
    cycle's results to whoever holds the seat now, which is wrong whenever the
    seat has changed hands — and it silently reads as that leader's own track
    record. Group joining date is the check: it survives an internal transfer,
    so a leader who moved teams is not mistaken for a new joiner.
    """
    global _joined
    with _lock:
        if _joined is None:
            df = pd.read_sql(
                'select employee_email, group_date_of_joining '
                'from staging.stg_me_dim_employee '
                'where group_date_of_joining is not null', get_db())
            _joined = pd.Series(
                pd.to_datetime(df['group_date_of_joining']).values,
                index=df['employee_email'].values)
    return _joined


def in_post(email, cycle):
    """Was this person employed by the time the cycle ran?

    None when unknown — the caller must not treat that as a No, or every
    leader missing from the employee master would be silently blanked.
    """
    start = cycle_start(cycle)
    if start is None or email is None:
        return None
    j = joined().get(email)
    if j is None or pd.isna(j):
        return None
    return bool(j <= start)


def managers():
    global _managers
    with _lock:
        if _managers is None:
            _managers = pd.read_sql(
                'select * from marts.mart_me_manager_cycle', get_db())
    return _managers


def flush():
    global _responses, _managers
    with _lock:
        _responses = None
        _managers = None
        for c in _CACHES:
            c.cache_clear()


@_cached
@_cached
def options(column):
    """Sorted, de-duplicated picklist values for one filter column."""
    s = responses()[column].dropna()
    s = s[s.astype(str).str.strip() != '']
    return sorted(s.astype(str).unique().tolist())


def parse_filters(params):
    """Pull filter selections out of the query string.

    Multi-selects arrive as a comma-joined string, which keeps the URL short
    enough to share and readable enough to debug.
    """
    out = {}
    for col, _label in ALL_FILTER_FIELDS:
        raw = params.get(col)
        if raw:
            vals = [v for v in raw.split('~') if v]
            if vals:
                out[col] = vals
    return out


def filter_key(filters):
    """A hashable, order-stable signature so the caches can key on it."""
    return tuple(sorted((k, tuple(sorted(v))) for k, v in (filters or {}).items()))


@_cached
def subset(cycle, fkey=()):
    """The response frame for one cycle with the filter bar applied.

    Cached on (cycle, fkey): a page render asks for the same slice a dozen
    times, and re-filtering 563k rows each time is what made the first build
    take 36 seconds.
    """
    f = responses()
    f = f[f['cycle'] == cycle]
    for col, vals in fkey:
        f = f[f[col].astype(str).isin(list(vals))]
    return f


@_cached
def cycles():
    """Cycles present in the data, oldest first."""
    have = set(responses()['cycle'].dropna().astype(str))
    return [c for c in CYCLE_ORDER if c in have]


def latest_cycle():
    return cycles()[-1]


@_cached
def default_cycle():
    """The cycle to open on: the most recent one that has finished collecting.

    Sep_26 is live as this is written — 1,692 responses against Mar_26's
    4,257, and only 23% of its managers clear the 3-response bar. Opening on
    it would show a sharp drop that is fieldwork, not sentiment. A cycle whose
    response base is less than 60% of the one before it is treated as still
    in flight; the picker still exposes it.
    """
    cs = cycles()
    if len(cs) < 2:
        return cs[-1]
    counts = {c: responses().loc[responses()['cycle'] == c,
                                 'email_address'].nunique() for c in cs}
    for c, prev in zip(reversed(cs), reversed(cs[:-1])):
        if counts[c] >= counts[prev] * 0.6:
            return c
    return cs[-2]


def is_in_flight(cycle):
    return cycle != default_cycle() and cycle == latest_cycle()


def prev_cycle(cycle):
    cs = cycles()
    i = cs.index(cycle)
    return cs[i - 1] if i > 0 else None


def refreshed_at():
    s = responses()['refreshed_date'].dropna()
    return s.max() if len(s) else None


# ── measures ──────────────────────────────────────────────────────────────

def nps(frame):
    """ME NPS. DAX: DIVIDE(Promoters - Detractor,
                           Promoters + Passive + Detractor)

    Counts DISTINCT respondents on the NPS question only, exactly as the
    Promoters / Passive / Detractor measures did.
    """
    n = frame[frame['category'] == 'NPS']
    if not len(n):
        return None, 0, 0, 0
    d = n.drop_duplicates('email_address')['promoter_detractor']
    p = int((d == 'Promoter').sum())
    a = int((d == 'Passive').sum())
    det = int((d == 'Detractor').sum())
    tot = p + a + det
    return ((p - det) / tot * 100 if tot else None), p, a, det


def theme_score(frame):
    """Theme Score. DAX: AVERAGE(Rating)"""
    v = frame['rating'].mean()
    return None if pd.isna(v) else float(v)


def pct_positive(frame):
    """% positive response. DAX: DIVIDE(Positive, Positive + Negative)"""
    pos = frame.loc[frame['positive_negative'] == 'Positive',
                    'email_address'].nunique()
    neg = frame.loc[frame['positive_negative'] == 'Negative',
                    'email_address'].nunique()
    return (pos / (pos + neg) * 100) if (pos + neg) else None


@_cached
def headline(cycle, fkey=()):
    """The numbers the Pulse hero and KPI strip read."""
    f = subset(cycle, fkey)
    m = managers()
    mc = m[m['cycle'] == cycle]
    if fkey:
        # Manager-grain figures follow the filtered population, otherwise the
        # KPI strip would keep quoting org-wide manager counts next to a
        # filtered score.
        mc = mc[mc['manager_email'].isin(f['manager_email'].unique())]
    n, p, a, d = nps(f)
    visible = mc[mc['cycle_visibility'] == 'Yes']
    return {
        'cycle': cycle,
        'respondents': int(f['email_address'].nunique()),
        'managers': int(f['manager_email'].nunique()),
        'me': theme_score(f),
        'nps': n,
        'promoters': p, 'passives': a, 'detractors': d,
        'visible_managers': int(len(visible)),
        'neg_nps_managers': int(mc['has_negative_nps'].sum()),
        'neg_nps_pct': (mc['has_negative_nps'].sum() / len(mc) * 100)
                       if len(mc) else None,
        'below_p25': int(mc['is_below_grade_p25'].sum()),
        'bucket_below70': int((visible['me_bucket'] == 'Below 70%').sum()),
        'bucket_70_90': int((visible['me_bucket'] == '70%-90%').sum()),
        'bucket_90plus': int((visible['me_bucket'] == '90% & Above').sum()),
    }


@_cached
def headline_all(fkey=()):
    return [headline(c, fkey) for c in cycles()]


@_cached
def themes(cycle, fkey=()):
    """Score per theme for one cycle, with the movement against the previous.

    Sorted weakest first — the report sorted alphabetically, which buried the
    finding.
    """
    cur = subset(cycle, fkey)
    cur = cur[cur['theme'].notna()]
    prev = prev_cycle(cycle)
    prv = subset(prev, fkey) if prev else None
    if prv is not None:
        prv = prv[prv['theme'].notna()]

    rows = []
    for theme, g in cur.groupby('theme', observed=True):
        score = theme_score(g)
        pscore = None
        if prv is not None:
            pg = prv[prv['theme'] == theme]
            pscore = theme_score(pg) if len(pg) else None
        rows.append({
            'theme': theme,
            'score': score,
            'prev': pscore,
            'delta': (score - pscore) if (score is not None
                                          and pscore is not None) else None,
            'questions': int(g['question'].nunique()),
            'tenet': _tenet_number(g),
        })
    return sorted(rows, key=lambda x: (x['score'] is None, x['score']))


def _tenet_number(g):
    """The canonical theme order, from the Tenet column ("Tenet 3: ...")."""
    s = g['tenet'].dropna()
    for v in s:
        if str(v).lower().startswith('tenet'):
            try:
                return int(str(v).split()[1].rstrip(':'))
            except (IndexError, ValueError):
                pass
    return None


@_cached
def theme_trend(fkey=()):
    """Every theme across every cycle — the small-multiples panel."""
    import pandas as _pd
    r = _pd.concat([subset(c, fkey) for c in cycles()]) if fkey else responses()
    t = (r[r['theme'].notna()]
         .pivot_table(index='theme', columns='cycle', values='rating',
                      aggfunc='mean', observed=True))
    return t.reindex(columns=[c for c in cycles() if c in t.columns])


@_cached
def questions(cycle, fkey=()):
    """Every statement for one cycle: score, % positive, base, grade bands.

    `asked_of` collapses the three target_grade values into one label so the
    table shows at a glance which bands saw a statement — the PBIP needed
    three separate mapping joins to know this.
    """
    f = subset(cycle, fkey)
    f = f[f['rating'].notna()]

    # Same statements one cycle back, for the movement column. Matched on the
    # question text, which is the only key the source gives — so a statement
    # that was reworded reads as new and its delta stays empty rather than
    # being compared against a different question. Mar_26 rewrote most of the
    # questionnaire, so its deltas against Sep_25 are mostly blank; Sep_26
    # kept all 35 of Mar_26's, so those are near-complete.
    prev = prev_cycle(cycle)
    prev_scores = {}
    if prev:
        p = subset(prev, fkey)
        p = p[p['rating'].notna()]
        prev_scores = p.groupby('question', observed=True)['rating'].mean().to_dict()

    rows = []
    for (theme, q), g in f.groupby(['theme', 'question'], observed=True):
        u = g.drop_duplicates('email_address')
        n = len(u)
        pos = int((u['positive_negative'] == 'Positive').sum())
        bands = sorted(g['target_grade'].dropna().unique())
        score = theme_score(g)
        was = prev_scores.get(q)
        if was is not None and pd.isna(was):
            was = None
        rows.append({
            'theme': theme,
            'question': q,
            'score': score,
            'n': n,
            'pct': (pos / n * 100) if n else None,
            'prev': None if was is None else float(was),
            'delta': (score - float(was)) if (score is not None
                                              and was is not None) else None,
            'asked_of': 'All' if len(bands) >= 3
                        else ', '.join(b.replace('Grade ', 'G') for b in bands),
        })
    return sorted(rows, key=lambda x: (x['score'] is None, x['score']))


@_cached
def segment(cycle, dimension, fkey=(), against=None, min_n=30):
    """One "Scores by ..." pivot, for any dimension.

    Replaces six near-identical pivot pages in the PBIP with one group-by.

    `min_n` defaults to 30 because below that a single strong or weak team
    moves a segment's score more than the segment means anything. The BU
    table passes 0: there are only fourteen business units, they are the
    org's own top-level split, and a reader who cannot see all of them cannot
    tell whether the column adds up to the headline.
    """
    col = DIMENSIONS[dimension]
    cur = subset(cycle, fkey)
    # `against` lets the caller pick the comparison cycle; without it the
    # baseline is the cycle immediately before, as the retired report assumed.
    prev = against or prev_cycle(cycle)
    prv = subset(prev, fkey) if prev and prev != cycle else None

    rows = []
    for key, g in cur[cur[col].notna()].groupby(col, observed=True):
        n = g['email_address'].nunique()
        if n < min_n:
            continue
        pg = prv[prv[col] == key] if prv is not None else None
        cn, *_ = nps(g)
        pn = nps(pg)[0] if pg is not None and len(pg) else None
        ps = theme_score(pg) if pg is not None and len(pg) else None
        s = theme_score(g)
        rows.append({
            'label': str(key),
            'n': int(n),
            'managers': int(g['manager_email'].nunique()),
            'me': s,
            'me_prev': ps,
            'me_delta': (s - ps) if (s is not None and ps is not None) else None,
            'nps': cn,
            'nps_prev': pn,
            'nps_delta': (cn - pn) if (cn is not None and pn is not None) else None,
        })
    return sorted(rows, key=lambda x: -x['n'])


@_cached
def hierarchy(cycle, family, level_col, fkey=()):
    """Roll every rated manager up to the leader — or HRBP — above them.

    Reproduces the PBIP's "Scores by Manager Hierarchy" and "Scores by HR
    Hierarchy" pivots, including the promoter / passive / detractor counts
    they carried.
    """
    cur = subset(cycle, fkey)
    prev = prev_cycle(cycle)
    prv = subset(prev, fkey) if prev else None

    rows = []
    for key, g in cur[cur[level_col].notna()].groupby(level_col, observed=True):
        n = g['email_address'].nunique()
        if n < 30:
            continue
        cn, p, a, d = nps(g)
        pg = prv[prv[level_col] == key] if prv is not None else None
        pn = nps(pg)[0] if pg is not None and len(pg) else None
        ps = theme_score(pg) if pg is not None and len(pg) else None
        s = theme_score(g)

        # Both hierarchy tables are a snapshot of the org as it stands today,
        # so a seat that changed hands credits its history to whoever holds it
        # now. Where the leader was not yet employed, the movement is the
        # seat's, not theirs — so the delta is withheld rather than shown
        # against their name. The level figures themselves stay: the span was
        # rated, and dropping the row would stop the column reconciling.
        here = in_post(str(key), cycle)
        there = in_post(str(key), prev) if prev else None
        show_delta = there is not False

        rows.append({
            'label': str(key),
            'n': int(n),
            'managers': int(g['manager_email'].nunique()),
            'me': s,
            'me_delta': (s - ps) if (show_delta and s is not None
                                     and ps is not None) else None,
            'nps': cn,
            'nps_delta': (cn - pn) if (show_delta and cn is not None
                                       and pn is not None) else None,
            'promoters': p, 'passives': a, 'detractors': d,
            # None = unknown (not in the employee master), so the page can
            # tell "joined later" apart from "cannot say".
            'in_post': here,
            'in_post_prev': there,
            'joined': joined().get(str(key)),
        })
    return sorted(rows, key=lambda x: -x['n'])


@_cached
def gender_matrix(cycle, fkey=()):
    """Manager gender x reportee gender. The PBIP had this as two pivots
    (one for NPS, one for ME score); one cell carries both."""
    f = subset(cycle, fkey)
    out = []
    for mg in ['Male', 'Female']:
        for rg in ['Male', 'Female']:
            s = f[(f['manager_gender'] == mg) & (f['reportee_gender'] == rg)]
            n, *_ = nps(s)
            out.append({'manager': mg, 'reportee': rg,
                        'nps': n, 'me': theme_score(s),
                        'n': int(s['email_address'].nunique())})
    return out


@_cached
def action_queue(cycle, limit=25, fkey=()):
    """Managers below the 25th percentile FOR THEIR OWN GRADE.

    The report's own bottom-quartile rule, not a raw score cut-off — a 3.30
    means something different at grade 4 than at grade 11. Ranked by how far
    below the bar they sit multiplied by how many people that affects, so a
    large team just under the line outranks one person far below it.

    Tagged against the previous cycle: PERSISTENT (below the bar then too),
    NEW (scored then, above the bar), FIRST CYCLE (not scored then).
    """
    m = managers()
    cur = m[(m['cycle'] == cycle) & m['is_below_grade_p25']].copy()
    if fkey:
        keep = subset(cycle, fkey)['manager_email'].unique()
        cur = cur[cur['manager_email'].isin(keep)]
    if not len(cur):
        return []
    prev = prev_cycle(cycle)
    pm = m[m['cycle'] == prev] if prev else None
    prev_below = set(pm.loc[pm['is_below_grade_p25'], 'manager_email']) if pm is not None else set()
    prev_seen = set(pm['manager_email']) if pm is not None else set()
    prev_score = dict(zip(pm['manager_email'], pm['theme_score'])) if pm is not None else {}

    cur['gap'] = cur['grade_p25_theme_score'] - cur['theme_score']
    cur['impact'] = cur['gap'] * cur['total_responses']
    cur = cur.sort_values('impact', ascending=False).head(limit)

    rows = []
    for _, x in cur.iterrows():
        email = x['manager_email']
        tag = ('PERSISTENT' if email in prev_below
               else 'NEW' if email in prev_seen else 'FIRST CYCLE')
        rows.append({
            'manager_email': email,
            'bu': x['manager_bu'] or '--',
            'grade': x['manager_grade'] or '--',
            'n': int(x['total_responses']),
            'score': float(x['theme_score']),
            'p25': float(x['grade_p25_theme_score']),
            'gap': float(x['gap']),
            'nps': None if pd.isna(x['me_nps']) else float(x['me_nps']),
            'promoters': int(x['promoters']),
            'passives': int(x['passives']),
            'detractors': int(x['detractors']),
            'prev': prev_score.get(email),
            'tag': tag,
        })
    return rows


@_cached
def manager_detail(manager_email, cycle):
    """Everything the drill-down drawer shows for one manager."""
    r = responses()
    f = r[(r['manager_email'] == manager_email) & (r['cycle'] == cycle)]
    if not len(f):
        return None
    th = (f[f['theme'].notna()].groupby('theme', observed=True)['rating']
          .mean().dropna().sort_values())
    q = (f[f['rating'].notna()].groupby('question', observed=True)['rating']
         .mean().dropna().sort_values())
    verbatims = (f[(f['category'] == 'Open Ended') & f['answer'].notna()]
                 [['question', 'answer']].values.tolist())
    n, p, a, d = nps(f)
    return {
        'manager_email': manager_email,
        'cycle': cycle,
        'bu': f['manager_bu'].dropna().iloc[0] if f['manager_bu'].notna().any() else '--',
        'grade': f['manager_grade'].dropna().iloc[0] if f['manager_grade'].notna().any() else '--',
        'n': int(f['email_address'].nunique()),
        'score': theme_score(f),
        'nps': n, 'promoters': p, 'passives': a, 'detractors': d,
        'themes': [(k, float(v)) for k, v in th.items()],
        'low_questions': [(k, float(v)) for k, v in list(q.items())[:6]],
        'verbatims': verbatims[:40],
    }


@_cached
def coverage(fkey=()):
    """How many rated managers clear the 3-response bar, by cycle.

    Not in the PBIP, and the reason it matters: reach and depth move
    independently, and only depth decides how many managers can actually be
    shown a score.
    """
    m = managers()
    out = []
    for c in cycles():
        mc = m[m['cycle'] == c]
        if fkey:
            mc = mc[mc['manager_email'].isin(
                subset(c, fkey)['manager_email'].unique())]
        vis = int((mc['cycle_visibility'] == 'Yes').sum())
        h = headline(c, fkey)
        out.append({'cycle': c, 'respondents': h['respondents'],
                    'managers': int(len(mc)), 'visible': vis,
                    'share': (vis / len(mc) * 100) if len(mc) else None})
    return out


def band_class(value, bands):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 'b-none'
    for cut, cls in bands:
        if value >= cut:
            return cls
    return bands[-1][1]
