"""Themes — six themes, every statement, and the statement x dimension heat map.

Replaces four PBIP pages: Questions Heat Map, Questions Top vs Bottom,
Question Detailed, and the theme visuals on the Executive Summary.
"""
from dash import html

import components as C
import data as D
import page_common as PC

def layout(cycle=None, heat=None, **params):
    cycle = PC.resolve_cycle(cycle)
    dim = heat if heat in D.HEATMAP_DIMENSIONS else 'BU'
    filters = D.parse_filters(params)
    fk = D.filter_key(filters)
    return html.Div([
        PC.filter_bar(cycle, filters, '/themes', {'heat': dim}),
        PC.active_chips(cycle, filters, '/themes', {'heat': dim}),
        _theme_cards(cycle, dim, fk),
        _trend(cycle, fk),
        _top_bottom(cycle, fk),
        _all_questions(cycle, fk),
        _heatmap(cycle, dim, fk),
    ], className='me-root')


def _theme_cards(cycle, dim=None, fk=()):
    themes = D.themes(cycle, fk)
    org = D.headline(cycle, fk)['me']
    # The heat map's dimension rides in the URL as `heat`, so a theme click
    # must carry that key and not invent a `dim` the router will ignore.
    keep = {'heat': dim} if dim else {}
    cards = []
    for t in themes:
        cards.append(html.Div([
            C.ml(f"TENET {t['tenet']}" if t['tenet'] else 'THEME', small=True),
            # Click the theme name to narrow the whole page to that theme.
            PC.xfilter(t['theme'], 'theme', t['theme'], cycle, fk,
                       '/themes', keep, className='xf-name'),
            html.Div([html.Div(C.fmt(t['score']), className='s'),
                      html.Div(C.delta(t['delta']),
                               style={'paddingBottom': '3px'})], className='r'),
            C.bar(t['score'], 3.0, 3.8, mark=org,
                  cls=D.band_class(t['score'], D.ME_BANDS)),
            C.foot(f"{t['questions']} statement"
                   f"{'s' if t['questions'] != 1 else ''} · "
                   f"Δ vs {D.CYCLE_LABEL.get(D.prev_cycle(cycle), '--')} · "
                   f"tick is the org average {C.fmt(org)}"),
        ], className='tc'))
    return C.section(
        'Six themes, one direction',
        note=f'vs {D.CYCLE_LABEL.get(D.prev_cycle(cycle), "--")}',
        desc='Sorted weakest first. Tenet numbers are the organisation’s own '
             'canonical order.',
        children=[html.Div(cards, className='tgrid')])


def _trend(cycle, fk=()):
    t = D.theme_trend(fk)
    cycles = [c for c in D.cycles() if c in t.columns]
    rows = []
    for theme in t.index:
        vals = [t.loc[theme, c] if c in t.columns else None for c in cycles]
        cells = [html.Td(theme, style={'fontWeight': '500'})]
        for c, v in zip(cycles, vals):
            v = None if v != v else v
            cells.append(html.Td(C.me_chip(v), className='r',
                                 style={'opacity': '1' if c == cycle else '.72'}))
        rows.append(html.Tr(cells))
    return C.section(
        'Theme scores across every cycle', alt=True,
        desc='The selected cycle is shown at full strength.',
        children=[html.Div([
            C.table(['Theme'] + [(D.CYCLE_LABEL.get(c, c), 'r') for c in cycles],
                    rows, min_width=560),
            C.legend(C.ME_LEGEND, 'ME BANDS'),
        ], className='box')])


def _top_bottom(cycle, fk=()):
    qs = D.questions(cycle, fk)
    return C.section(
        'Weakest and strongest statements', note='top / bottom 5 by score',
        desc='The PBIP had these as two separate pages, each with a TopN filter '
             'of 5. Same rule, same cut. Δ is against the previous cycle, and '
             'is blank where the statement was not asked then.',
        children=[html.Div([
            C.box('Weakest five', desc='The behaviours to coach first.',
                  children=_q_table(qs[:5], cycle, True, fk,
                                    show_delta=True, narrow=True)),
            C.box('Strongest five', desc='What is already working.',
                  children=_q_table(list(reversed(qs[-5:])), cycle, True, fk,
                                    show_delta=True, narrow=True)),
        ], className='grid g2')])


def _all_questions(cycle, fk=()):
    qs = sorted(list(D.questions(cycle, fk)),
                key=lambda x: (x['theme'] or '', x['score']))
    return C.section(
        'Every statement, by theme', note=f'{len(qs)} statements', alt=True,
        desc='Score is the 1–4 average. % positive is the share answering Agree '
             'or Strongly agree. Δ is against the previous cycle, and is blank '
             'where the statement was not asked then. Hover a row for the grade '
             'bands it was asked of.',
        children=[html.Div([
            html.Div(_q_table(qs, cycle, True, fk, show_delta=True),
                     className='ys'),
            C.legend(C.ME_LEGEND, 'ME BANDS'),
        ], className='box')])


def _q_table(qs, cycle, show_theme=False, fk=(), show_delta=False,
             narrow=False):
    """One statement per row.

    `narrow` is for the weakest/strongest five, which sit two to a row. The
    same seven columns have roughly half the width there, so the floor is
    dropped and the statement text is allowed to wrap over more lines rather
    than pushing the table into a horizontal scroll.
    """
    org = D.headline(cycle, fk)['me']
    against = D.CYCLE_LABEL.get(D.prev_cycle(cycle), '--')
    rows = []
    for q in qs:
        cells = []
        if show_theme:
            cells.append(html.Td(q['theme'] or '--',
                                 style={'color': 'var(--t2)',
                                        'whiteSpace': 'nowrap'}))
        cells += [
            html.Td(q['question'], className='qtxt'),
            html.Td(C.me_chip(q['score']), className='r'),
            html.Td(C.bar(q['score'], 1, 4, mark=org), style={'width': '90px'}),
        ]
        if show_delta:
            # Blank, not a zero, when the statement was not asked last cycle —
            # a dash says "no comparison", a 0.00 would claim "no change".
            cells.append(
                html.Td(C.delta(q.get('delta')) if q.get('delta') is not None
                        else html.Span('--', className='seat-na'),
                        className='r'))
        cells += [
            html.Td(C.fmt(q['pct'], 1) + '%', className='r mono'),
            html.Td(C.num(q['n']), className='r mono',
                    style={'color': 'var(--t3)'}),
        ]
        rows.append(C.tip(html.Tr(cells), '\n'.join([
            q['question'],
            f"Score {C.fmt(q['score'])} of 4   |   "
            f"{C.fmt(q['pct'], 1)}% answered Agree or Strongly agree",
            (f"Was {C.fmt(q['prev'])} in {against}"
             if q.get('prev') is not None
             else f"Not asked in {against}, so there is nothing to compare"),
            f"{q['n']:,} respondents   |   asked of {q['asked_of']}",
            f"Theme: {q['theme'] or 'unmapped'}",
        ])))
    headers = (['Theme'] if show_theme else []) + [
        'Statement', ('Score', 'r'), ''] \
        + ([(f'Δ vs {against}', 'r')] if show_delta else []) \
        + [('% pos', 'r'), ('n', 'r')]
    if narrow:
        width = 520
    else:
        width = 720 if show_delta else 640
    return C.table(headers, rows, min_width=width)


# ── heat map ──────────────────────────────────────────────────────────────

def _heatmap(cycle, dim, fk=()):
    col = D.HEATMAP_DIMENSIONS[dim]
    f = D.subset(cycle, fk)
    f = f[f['rating'].notna()]

    # Every value of the cut is a column, as the report has it — no minimum
    # base to clear. Only the two cuts too wide for an HTML table are capped,
    # and by response volume so the biggest are the ones kept.
    # Blank is not a value. Without this, Mandate renders an empty column
    # header — matching the treatment D.options() already gives the pickers.
    have = f[f[col].notna() & (f[col].astype(str).str.strip() != '')]
    counts = (have.groupby(col, observed=True)['email_address']
              .nunique().sort_values(ascending=False))
    kept = [str(c) for c in counts.index[:D.HEATMAP_MAX_COLS]]
    capped = len(counts) > len(kept)
    cols = sorted(kept, key=D.label_sort_key)

    rows = []
    for (theme, q), g in f.groupby(['theme', 'question'], observed=True):
        overall = D.theme_score(g)
        cells = []
        for c in cols:
            s = g[g[col].astype(str) == c]
            # Blank means nobody in that column answered this statement —
            # which is common, since the questionnaire branches by grade band.
            cells.append(D.theme_score(s) if len(s) else None)
        rows.append((theme, q, overall, cells))
    rows.sort(key=lambda x: (x[2] is None, x[2]))

    trs = []
    for theme, q, overall, cells in rows:
        trs.append(html.Tr(
            [html.Td(theme or '--', style={'color': 'var(--t2)',
                                           'whiteSpace': 'nowrap',
                                           'fontSize': '11.5px'}),
             html.Td(q, className='qtxt', style={'fontSize': '11.5px'}),
             html.Td(C.me_chip(overall), className='r')]
            + [html.Td(C.me_chip(v), className='r') for v in cells]))

    picker = html.Div(
        PC.pill_links('/themes', 'heat',
                      [(k, k) for k in D.HEATMAP_DIMENSIONS],
                      dim, dict({'cycle': cycle}, **PC.filter_qs(fk))),
        className='pillbtns')

    return C.section(
        'Statement × dimension heat map', note=D.CYCLE_LABEL.get(cycle),
        children=[html.Div([
            picker,
            C.table(['Theme', 'Statement', ('All', 'r')]
                    + [(c, 'r') for c in cols], trs,
                    min_width=560 + 62 * len(cols)),
            C.legend(C.ME_LEGEND, 'ME BANDS'),
        ] + ([C.foot(f'{dim} has {len(counts)} values; the {len(cols)} with '
                     f'the most responses are shown')] if capped else []),
            className='box')])



