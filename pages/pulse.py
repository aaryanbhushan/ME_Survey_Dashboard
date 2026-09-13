"""Pulse — the story this cycle.

Replaces the PBIP's Executive Summary, NPS Overview and NPS Repeat Responder
pages. The hero carries one number; the insight column says what moved and
why it matters, which is the job the report's aiNarratives visual never quite
did.
"""
from dash import dcc, html

import components as C
import data as D
import page_common as PC

def layout(cycle=None, drill=None, cmp_from=None, cmp_to=None, **params):
    """Rendered server-side in one pass. State comes from the query string."""
    cycle = PC.resolve_cycle(cycle)
    filters = D.parse_filters(params)
    fk = D.filter_key(filters)
    cs = D.cycles()
    # Which two cycles the movement panels compare. Defaults to the selected
    # cycle against the one before it, which is what the report always did.
    cmp_to = cmp_to if cmp_to in cs else cycle
    default_from = D.prev_cycle(cmp_to) or cmp_to
    cmp_from = cmp_from if cmp_from in cs and cmp_from != cmp_to else default_from
    h = D.headline(cycle, fk)
    prev = D.prev_cycle(cycle)
    p = D.headline(prev, fk) if prev else None
    cycles = D.cycles()
    all_h = D.headline_all(fk)

    return html.Div([
        PC.filter_bar(cycle, filters, '/'),
        PC.active_chips(cycle, filters, '/'),
        _hero_band(cycle, h, p, cycles, all_h, fk),
        _trends(cycle, all_h, cycles, fk, cmp_from),
        _flow_and_mix(cycle, fk, cmp_from, cmp_to, filters),
        _bands_and_bu(cycle, h, fk, cmp_from, cmp_to),
        _drill_panel(drill, cycle, fk, cmp_from, cmp_to, params),
    ], className='me-root')


# ── hero ──────────────────────────────────────────────────────────────────

def _hero_band(cycle, h, p, cycles, all_h, fk=()):
    d_me = (h['me'] - p['me']) if p and h['me'] and p['me'] else None
    prev_c = D.prev_cycle(cycle)
    th = D.themes(cycle, fk)      # cached, but ask once and read twice
    strongest = th[-1] if th else None
    weakest = th[0] if th else None

    # Each is a compressed number, so each carries what it counts in a native
    # title tooltip. "BELOW GRADE P25" used to head the fifth one — a
    # percentile is not something a reader should have to decode to know
    # whether 171 is good or bad.
    mini = [
        ('MANAGER NPS', C.fmt(h['nps'], 1),
         'var(--good)' if (h['nps'] or 0) >= 40 else 'var(--bad)',
         'Promoters minus detractors, as a share of everyone who answered the '
         '0–10 "would you recommend your manager" question.'),
        ('NEGATIVE-NPS MANAGERS', C.fmt(h['neg_nps_pct'], 1) + '%',
         'var(--bad)',
         f"{C.num(h['neg_nps_managers'])} of {C.num(h['managers'])} rated "
         f"managers have more detractors than promoters."),
        ('STRONGEST THEME', C.fmt(strongest['score']) if strongest else '--',
         'var(--good)',
         f"{strongest['theme']} — the highest of the six theme scores, out "
         f"of 4." if strongest else 'No theme scores in this cycle.'),
        ('WEAKEST THEME', C.fmt(weakest['score']) if weakest else '--',
         'var(--bad)',
         f"{weakest['theme']} — the lowest of the six theme scores, out of 4."
         if weakest else 'No theme scores in this cycle.'),
        ('BOTTOM 25% OF THEIR GRADE', C.num(h['below_p25']), 'var(--warn)',
         f"{C.num(h['below_p25'])} scored managers sit in the weakest quarter "
         f"for their OWN grade. Compared within grade because 3.30 means "
         f"something different at G4 than at G11. These are the managers the "
         f"Action Queue ranks."),
        ('SCORED OF RATED',
         f"{round(h['visible_managers'] / h['managers'] * 100)}%" if h['managers'] else '--',
         'var(--warn)',
         f"{C.num(h['visible_managers'])} of {C.num(h['managers'])} rated "
         f"managers had at least 3 people rate them, which is the minimum for "
         f"a score to be shown at all."),
    ]

    hero = html.Div([
        C.ml(f"ME SCORE · ALL BUs · {D.CYCLE_LABEL.get(cycle, cycle).upper().replace(' ', '_')}"),
        html.Div([
            html.Div([C.fmt(h['me']), html.Small('/4')], className='v'),
            html.Div([C.delta(d_me),
                      html.Span(f' vs {D.CYCLE_LABEL.get(prev_c, "")}',
                                className='ml sm')]
                     if d_me is not None
                     else html.Span('first cycle', className='dlt nil')),
        ], className='hero-n'),
        html.Div(f"{C.num(h['respondents'])} respondents · "
                 f"{C.num(h['managers'])} managers rated · "
                 f"{C.num(h['visible_managers'])} scored at 3+ responses",
                 className='hero-sub'),
        PC.spark([x['me'] for x in all_h], cycles, cycle),
        html.Div(className='rule'),
        html.Div([
            html.Div([C.ml(label, small=True),
                      html.Div(value, className='v', style={'color': colour})],
                     title=tip)
            for label, value, colour, tip in mini
        ], className='mini'),
    ], className='pane')

    insights = html.Div([
        html.Div([C.ml('WHAT THIS CYCLE SAYS'),
                  html.Span(f'vs {D.CYCLE_LABEL.get(D.prev_cycle(cycle), "--")}',
                            className='ml sm')],
                 className='ins-head'),
        html.Div(_insights(cycle, h, p, fk), className='ins-list'),
    ], className='pane')

    return html.Div([hero, insights], className='band')


def _insights(cycle, h, p, fk=()):
    """Written from the data, not hard-coded — so they stay true when the
    cycle picker moves or the next refresh lands."""
    out = []
    qs = dict({'cycle': cycle}, **PC.filter_qs(fk))

    # No theme-movement card here. Theme scores average only the statements
    # that carry a theme, while the hero above averages every rated row — and
    # since Sep_26 those are different sets, because the seven
    # psychological-safety statements have no theme. On Sep_26 that put "6 of
    # 6 themes improved" directly beneath a hero reading 0.04 down: both
    # true, computed over different bases, and irreconcilable at a glance.
    # The theme moves are on the Themes page, where the base is consistent.

    if p and h['neg_nps_managers'] and p['neg_nps_managers']:
        det_growth = ((h['detractors'] / p['detractors'] - 1) * 100
                      if p['detractors'] else None)
        base_growth = (h['respondents'] / p['respondents'] - 1) * 100
        tail = ''
        if det_growth is not None:
            tail = (f" Detractors moved {det_growth:+.0f}% while the response "
                    f"base moved {base_growth:+.0f}% — reach does not explain it.")
        out.append(_ins(
            'rail-bad' if h['neg_nps_managers'] >= p['neg_nps_managers'] else 'rail-good',
            f"{C.num(h['neg_nps_managers'])} managers sit at a negative NPS, "
            f"{'up' if h['neg_nps_managers'] >= p['neg_nps_managers'] else 'down'} "
            f"from {C.num(p['neg_nps_managers'])}",
            f"{C.fmt(h['neg_nps_pct'], 1)}% of rated managers against "
            f"{C.fmt(p['neg_nps_pct'], 1)}% last cycle.{tail}",
            'negnps', qs))

    stmts = D.questions(cycle, fk)
    if stmts:
        low = stmts[0]
        out.append(_ins('rail-warn',
                        f"The weakest behaviour is {C.fmt(low['score'])} — "
                        f"{low['theme']}",
                        f"“{low['question']}” is the lowest of {len(stmts)} statements, "
                        f"{C.fmt(low['pct'], 1)}% positive across {C.num(low['n'])} responses.",
                        'statements', qs))

    gm = D.gender_matrix(cycle, fk)
    mm = next((g for g in gm if g['manager'] == 'Male' and g['reportee'] == 'Male'), None)
    ff = next((g for g in gm if g['manager'] == 'Female' and g['reportee'] == 'Female'), None)
    if mm and ff and mm['nps'] is not None and ff['nps'] is not None:
        out.append(_ins('rail-warn',
                        f"Women rate their managers {mm['nps'] - ff['nps']:.1f} NPS "
                        f"points lower than men do",
                        f"Man→man pairings sit at {C.fmt(mm['nps'], 1)} against "
                        f"{C.fmt(ff['nps'], 1)} for woman→woman. The gap holds "
                        f"whichever gender the manager is, so it is not a "
                        f"manager-matching effect. The woman→woman cell rests on "
                        f"{C.num(ff['n'])} responses.", 'gender', qs))

    # No band-movement card. "Moved down a band" asks the reader to hold the
    # promoter/passive/detractor cut in their head before the sentence means
    # anything, and a card is the wrong place to teach a definition. The
    # promoter mix says the same thing in shares, which needs no glossary.

    share = h['visible_managers'] / h['managers'] * 100 if h['managers'] else 0
    out.append(_ins('rail-warn',
                    f"Only {share:.0f}% of rated managers clear the 3-response bar",
                    f"{C.num(h['visible_managers'])} of {C.num(h['managers'])} have "
                    f"enough responses to be scored at all; the other "
                    f"{C.num(h['managers'] - h['visible_managers'])} are suppressed.",
                    'coverage', qs))
    return out


def _ins(rail, title, body, drill=None, qs=None):
    """An insight card. Clicking one opens the evidence behind it.

    A headline number with no way to ask "which ones?" invites a stakeholder
    to either take it on faith or ignore it; the drill is what makes it
    checkable.
    """
    card = html.Div([
        html.Div(className=f'rail {rail}'),
        html.Div([html.H3(title), html.P(body)]
                 + ([html.Div('See the evidence \u2192', className='drill-cue')]
                    if drill else [])),
    ], className='ins')
    if not drill:
        return card
    params = dict(qs or {}); params['drill'] = drill
    href = '/?' + '&'.join(f'{k}={v}' for k, v in params.items() if v)
    return dcc.Link(card, href=href, className='ins-link')


# ── trends ────────────────────────────────────────────────────────────────

def _trends(cycle, all_h, cycles, fk=(), cmp_from=None):
    return C.section(
        'The two headline measures, cycle by cycle', note='scale 1–4 and NPS',
        desc='Both charts show every cycle, with the selected one picked out.',
        alt=True,
        children=[
            html.Div([
                C.box('ME score across cycles', note='scale 1–4',
                      desc='Average of every rated statement.',
                      children=_cycle_bars(all_h, cycles, cycle, 'me', 2)),
                C.box('Manager NPS across cycles',
                      note='% promoters − % detractors',
                      desc='One response per employee to the recommendation question.',
                      children=_cycle_bars(all_h, cycles, cycle, 'nps', 1)),
            ], className='grid g2'),
        ])


def _cycle_bars(all_h, cycles, current, key, digits):
    """Bars, current cycle in orange, the rest grey. Emphasis rather than a
    categorical palette: there is one series and one number that matters."""
    vals = [x[key] for x in all_h]
    present = [v for v in vals if v is not None]
    if not present:
        return html.Div('No data', className='sd')
    lo, hi = min(present), max(present)
    pad = (hi - lo) * 0.25 or 0.1
    lo, hi = lo - pad, hi + pad
    rows = []
    for c, v in zip(cycles, vals):
        pct = 0 if v is None else (v - lo) / (hi - lo) * 100
        rows.append(html.Div([
            html.Div(D.CYCLE_LABEL.get(c, c),
                     style={'width': '62px', 'font': '500 10px var(--mono)',
                            'color': 'var(--ink)' if c == current else 'var(--t3)'}),
            html.Div(html.Div(className='bar-fill',
                              style={'width': f'{pct:.1f}%',
                                     'background': 'var(--orange)' if c == current
                                                   else 'var(--grey)'}),
                     className='bar-track', style={'flex': '1', 'height': '18px'}),
            html.Div(C.fmt(v, digits),
                     className='mono',
                     style={'width': '52px', 'textAlign': 'right',
                            'font': f'600 12.5px var(--mono)'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px',
                  'padding': '5px 0'}))
    return html.Div(rows + [
        C.foot('selected cycle in orange · bars scaled to the observed range, '
               'not to zero, because these scores live in a narrow band')])


# ── flow + mix ────────────────────────────────────────────────────────────

def _flow_and_mix(cycle, fk, cmp_from, cmp_to, filters):
    """How the promoter mix differs between any two cycles.

    The "where the same people moved" panel that used to sit beside this is
    gone. It tracked repeat responders across the promoter / passive /
    detractor bands, and every reading of it started with explaining what a
    band was \u2014 a footnote defining the 0-10 cut, then three rows of "moved up
    at least one band". The mix below carries the same story as plain shares
    of the base, which needs no definition to read.
    """
    return C.section(
        'What changed between two cycles', None,
        'Pick the pair to compare. Shares are of everyone who answered the '
        'recommendation question in each cycle.',
        children=[
            _compare_picker(cycle, cmp_from, cmp_to, fk),
            C.box('Promoter mix',
                  note=f'{D.CYCLE_LABEL.get(cmp_from)} \u2192 '
                       f'{D.CYCLE_LABEL.get(cmp_to)}',
                  desc='Every respondent to the recommendation question.',
                  children=_mix(cmp_from, cmp_to, fk)),
        ])


def _compare_picker(cycle, cmp_from, cmp_to, fk):
    """Two link rows: which cycle to compare from, and to."""
    base = dict({'cycle': cycle}, **PC.filter_qs(fk))
    return html.Div([
        html.Span('COMPARE', className='ml'),
        html.Div(PC.pill_links('/', 'cmp_from',
                               [(c, D.CYCLE_LABEL.get(c, c)) for c in D.cycles()
                                if c != cmp_to],
                               cmp_from, dict(base, cmp_to=cmp_to)),
                 style={'display': 'flex', 'gap': '6px'}),
        html.Span('\u2192', style={'color': 'var(--t3)', 'margin': '0 4px'}),
        html.Div(PC.pill_links('/', 'cmp_to',
                               [(c, D.CYCLE_LABEL.get(c, c)) for c in D.cycles()
                                if c != cmp_from],
                               cmp_to, dict(base, cmp_from=cmp_from)),
                 style={'display': 'flex', 'gap': '6px'}),
    ], className='cmp')


def _mix(cmp_from, cmp_to, fk):
    rows = []
    for c in [cmp_from, cmp_to]:
        x = D.headline(c, fk)
        tot = x['promoters'] + x['passives'] + x['detractors']
        if not tot:
            continue
        segs = []
        for key, label, cls in [('promoters', 'Promoter', 'm-p'),
                                ('passives', 'Passive', 'm-a'),
                                ('detractors', 'Detractor', 'm-d')]:
            pct = x[key] / tot * 100
            segs.append(C.tip(
                html.Div(f'{pct:.0f}%' if pct > 8 else '', className=cls,
                         style={'flex': str(x[key])}),
                f'{label} (scored {D.NPS_BAND_RANGE[label]}): {x[key]:,} of '
                f'{tot:,} ({pct:.1f}%) in {D.CYCLE_LABEL.get(c)}'))
        rows.append(html.Div([
            html.Div([C.ml(D.CYCLE_LABEL.get(c, '').upper()),
                      html.Span(f' {C.num(tot)} responses',
                                style={'font': '400 11.5px var(--sans)',
                                       'color': 'var(--t3)'})]),
            html.Div(segs, className='mix'),
        ], style={'marginBottom': '16px'}))

    a, b = D.headline(cmp_from, fk), D.headline(cmp_to, fk)
    note = ''
    if a['detractors'] and a['respondents']:
        note = (f"Detractors moved {(b['detractors'] / a['detractors'] - 1) * 100:+.0f}% "
                f"while the response base moved "
                f"{(b['respondents'] / a['respondents'] - 1) * 100:+.0f}%.")
    swatch = {'Promoter': 'sw b-good', 'Passive': 'sw b-none',
              'Detractor': 'sw b-bad'}
    return html.Div(rows + [
        C.legend([(f'{b.lower()} {D.NPS_BAND_RANGE[b]}', swatch[b])
                  for b in D.NPS_BAND_ORDER]),
        html.P(note, className='note-p') if note else html.Div(),
    ])


# ── bands + BU ────────────────────────────────────────────────────────────

def _bands_and_bu(cycle, h, fk=(), cmp_from=None, cmp_to=None):
    """Both panels read the COMPARE PAIR, not the cycle dropdown.

    They used to take "now" from the Survey-cycle dropdown and "then" from
    the compare-from picker — two separate controls. Setting them to the same
    cycle made every delta zero or n/a, which looked like broken data rather
    than a self-comparison. Reading both ends from the one pair makes that
    impossible: the picker never offers the same cycle on both sides.
    """
    to_h = D.headline(cmp_to, fk)
    return C.section(
        'Where the score is concentrated',
        note=f'{D.CYCLE_LABEL.get(cmp_from, "--")} \u2192 '
             f'{D.CYCLE_LABEL.get(cmp_to, "--")}',
        desc='Both panels compare the pair selected below, and every delta '
             'names the cycle it is measured against.',
        alt=True,
        children=[
            _compare_picker(cycle, cmp_from, cmp_to, fk),
            html.Div([
                C.box('Managers by ME band',
                      note=f"{C.num(to_h['visible_managers'])} scored in "
                           f"{D.CYCLE_LABEL.get(cmp_to, '--')}",
                      desc='ME% = score ÷ 4. Only managers with 3+ responses '
                           'are scored, so this counts the scored half.',
                      children=_bands(cmp_to, fk, cmp_from)),
                C.box('Business units',
                      note=f'{D.CYCLE_LABEL.get(cmp_to, "--")}, '
                           f'\u0394 vs {D.CYCLE_LABEL.get(cmp_from, "--")}',
                      desc='Every business unit, sorted by NPS movement.',
                      children=_bu_table(cmp_to, fk, cmp_from)),
            ], className='grid g32'),
        ])


# The last field is whether MORE managers in this band is good news. It is
# not for the bottom band: a rise there is the thing you least want to see,
# and colouring it green because the number went up would say the opposite.
BANDS = [('Below 70%', 'under 2.80', 'bucket_below70', 'b-bad', False),
         ('70% – 90%', '2.80 – 3.59', 'bucket_70_90', 'b-warn', None),
         ('90% & above', '3.60 – 4.00', 'bucket_90plus', 'b-good', True)]


def _bands(cycle, fk=(), cmp_from=None):
    """Band counts, with the movement and a shape-of-history sparkline.

    A single cycle's split says how managers are distributed; it does not say
    whether the distribution is drifting. The sparkline is what turns three
    static numbers into a trend, and the delta names the cycle it is measured
    against rather than leaving the reader to guess.
    """
    now = D.headline(cycle, fk)
    then = D.headline(cmp_from, fk) if cmp_from else None
    series = {b[2]: [D.headline(c, fk)[b[2]] for c in D.cycles()] for b in BANDS}
    total = now['visible_managers'] or 1

    out = []
    for label, sub, key, cls, up_is_good in BANDS:
        n = now[key]
        d = (n - then[key]) if then else None
        vals = series[key]
        hi = max(max(vals), 1)
        spark = html.Div(
            [html.Div(className='sp-bar' + (' cur' if c == cycle else ''),
                      style={'height': f'{max(6, v / hi * 100):.0f}%'},
                      title=f'{D.CYCLE_LABEL.get(c)}: {v:,} managers')
             for c, v in zip(D.cycles(), vals)],
            className='sp')
        out.append(html.Div([
            html.Div([html.Div(label, style={'font': '600 12.5px var(--sans)'}),
                      html.Div(sub, className='ml sm')],
                     style={'width': '118px'}),
            html.Div(html.Div(className=f'bar-fill {cls}',
                              style={'width': f'{n / total * 100:.1f}%'}),
                     className='bar-track', style={'flex': '1', 'height': '18px'}),
            spark,
            html.Div(C.num(n), className='mono',
                     style={'width': '48px', 'textAlign': 'right',
                            'font': '600 12.5px var(--mono)'}),
            html.Div(
                (html.Span(f'{d:+,}', className='dlt nil') if up_is_good is None
                 else C.delta(d, digits=0, good_is_up=up_is_good))
                if d is not None else html.Span('', className='dlt nil'),
                style={'width': '74px', 'textAlign': 'right'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px',
                  'padding': '7px 0'},
            title=f'{label} ({sub}) — {n:,} of {total:,} scored managers'
                  + (f'; {d:+,} against {D.CYCLE_LABEL.get(cmp_from)}'
                     if d is not None else '')))

    return html.Div(out + [
        C.foot(f'bar = share of scored managers \u00b7 sparkline = every cycle, '
               f'{D.CYCLE_LABEL.get(cycle)} highlighted \u00b7 '
               f'\u0394 vs {D.CYCLE_LABEL.get(cmp_from, "--")}'),
        html.P('Nearly every manager lands in the middle band, so the '
               'report\u2019s own three-way split does not separate them. The '
               'action queue uses the grade-relative bottom quartile instead.',
               className='note-p')])


def _bu_table(cycle, fk=(), cmp_from=None):
    # Every unit, however small. A hidden row is worse than a small one: the
    # column stops adding up to the headline and the reader cannot tell which
    # units are missing or why.
    rows_data = sorted(
        D.segment(cycle, 'Business unit', fk, cmp_from, min_n=0),
        key=lambda r: (r['nps_delta'] is None, r['nps_delta'] or 0))
    against = D.CYCLE_LABEL.get(cmp_from, '--')
    keep = {}
    if cmp_from:
        keep['cmp_from'] = cmp_from
    rows = []
    for r in rows_data:
        rows.append(html.Tr([
            # Click a BU to narrow the whole page to it.
            html.Td(PC.xfilter(r['label'], 'manager_bu', r['label'],
                               cycle, fk, '/', keep),
                    style={'fontWeight': '500'}),
            html.Td(C.num(r['n']), className='r mono'),
            html.Td(C.num(r['managers']), className='r mono',
                    style={'color': 'var(--t3)'}),
            html.Td(C.me_chip(r['me']), className='r'),
            html.Td(C.delta(r['me_delta']), className='r'),
            html.Td(C.nps_chip(r['nps']), className='r'),
            html.Td(C.delta(r['nps_delta'], 1), className='r'),
        ], title='\n'.join([
            r['label'],
            f"ME score {C.fmt(r['me'])} of 4 (was {C.fmt(r['me_prev'])} "
            f"in {against})",
            f"Manager NPS {C.fmt(r['nps'], 1)} (was {C.fmt(r['nps_prev'], 1)} "
            f"in {against})",
            f"{r['n']:,} respondents across {r['managers']:,} managers",
            '',
            'Click the name to filter the whole page to this BU',
        ])))
    return html.Div([
        C.table(['Business unit', ('n', 'r'), ('Mgrs', 'r'), ('ME', 'r'),
                 (f'\u0394 ME vs {against}', 'r'), ('NPS', 'r'),
                 (f'\u0394 NPS vs {against}', 'r')], rows, min_width=720),
        # Both chip colours need their ranges spelled out. Only the ME scale
        # was listed, which left the NPS colours meaning nothing.
        C.legend(C.ME_LEGEND, 'ME BANDS'),
        C.legend(C.NPS_LEGEND, 'NPS BANDS'),
    ])


# ── drill panel ───────────────────────────────────────────────────────────

def _drill_panel(drill, cycle, fk, cmp_from, cmp_to, params):
    """The evidence behind an insight card.

    Every card asserts something; this is where the reader checks it. Each
    body answers the same question in its own terms: which themes, which
    managers, which statements, which business units.
    """
    if not drill:
        return html.Div()
    # Close by dropping only the drill key, so the cycle, the filters and the
    # compare pair all survive being closed.
    keep = {k: v for k, v in params.items() if k not in ('drill', '_r')}
    keep['cycle'] = cycle
    if cmp_from:
        keep['cmp_from'] = cmp_from
    if cmp_to:
        keep['cmp_to'] = cmp_to
    close = '/?' + '&'.join(f'{k}={v}' for k, v in keep.items() if v)
    builders = {
        'themes': _drill_themes,
        'negnps': _drill_negnps,
        'statements': _drill_statements,
        'gender': _drill_gender,
        'coverage': _drill_coverage,
    }
    fn = builders.get(drill)
    if fn is None:
        return html.Div()
    title, subtitle, body = fn(cycle, fk, cmp_from, cmp_to)
    return C.side_panel(title, subtitle, close, body)


def _drill_themes(cycle, fk, *_a):
    th = D.themes(cycle, fk)
    prev = D.prev_cycle(cycle)
    rows = []
    for t in th:
        rows.append(html.Tr([
            html.Td(t['theme'], style={'fontWeight': '500'}),
            html.Td(C.me_chip(t['score']), className='r'),
            html.Td(C.fmt(t['prev']), className='r mono',
                    style={'color': 'var(--t3)'}),
            html.Td(C.delta(t['delta']), className='r'),
            html.Td(C.num(t['questions']), className='r mono',
                    style={'color': 'var(--t3)'}),
        ]))
    worst = min((t for t in th if t['delta'] is not None),
                key=lambda t: t['delta'], default=None)
    body = [
        html.Div([C.ml('EVERY THEME, WEAKEST FIRST'),
                  C.table(['Theme', ('Now', 'r'),
                           (D.CYCLE_LABEL.get(prev, 'Prev'), 'r'),
                           ('\u0394', 'r'), ('Statements', 'r')], rows,
                          min_width=420)]),
        html.Div([
            C.ml('WHAT SITS UNDER THE WORST THEME'),
            _drill_theme_questions(cycle, fk, worst['theme']) if worst
            else html.Div(),
        ]),
    ]
    return ('Theme movement',
            f'{D.CYCLE_LABEL.get(cycle)} against {D.CYCLE_LABEL.get(prev, "--")}',
            body)


def _drill_theme_questions(cycle, fk, theme):
    qs = [q for q in D.questions(cycle, fk) if q['theme'] == theme]
    return html.Div([C.stat_row(q['question'], C.fmt(q['score']),
                                f"n={q['n']:,}") for q in qs] or
                    [html.Div('No rated statements.', className='sd')])


def _drill_negnps(cycle, fk, *_a):
    m = D.managers()
    mc = m[(m['cycle'] == cycle) & m['has_negative_nps']].copy()
    if fk:
        keep = D.subset(cycle, fk)['manager_email'].unique()
        mc = mc[mc['manager_email'].isin(keep)]
    total = len(mc)

    # Managers with no business unit on the employee master have to be shown,
    # not dropped: a groupby silently discards them and the column then fails
    # to add up to the headline count, which is the fastest way to lose a
    # reader's trust in the number.
    bu = mc['manager_bu'].fillna('').astype(str).str.strip()
    bu = bu.mask(bu == '', 'Not mapped to a BU')
    counts = bu.value_counts()

    rows = []
    for label, n in counts.items():
        unmapped = label == 'Not mapped to a BU'
        rows.append(html.Tr([
            html.Td(label, style={'fontWeight': '500',
                                  'color': 'var(--t3)' if unmapped else 'inherit',
                                  'fontStyle': 'italic' if unmapped else 'normal'}),
            html.Td(C.num(n), className='r mono'),
            html.Td(f'{n / total * 100:.0f}%', className='r mono',
                    style={'color': 'var(--t3)'}),
        ], title=f'{n:,} of {total:,} negative-NPS managers '
                 f'({n / total * 100:.1f}%) sit in {label}'))
    rows.append(html.Tr([
        html.Td('Total', style={'fontWeight': '600'}),
        html.Td(C.num(total), className='r mono',
                style={'fontWeight': '600'}),
        html.Td('100%', className='r mono', style={'color': 'var(--t3)'}),
    ], style={'borderTop': '2px solid var(--line2)'}))

    return ('Managers at a negative NPS',
            f'{total:,} managers \u00b7 {D.CYCLE_LABEL.get(cycle)}',
            [html.Div([
                C.ml('WHICH BUSINESS UNITS THEY SIT IN'),
                C.table(['Business unit', ('Managers', 'r'), ('Share', 'r')],
                        rows, min_width=320),
                C.foot('a negative NPS means more of the team would not '
                       'recommend the manager than would'),
            ])])


def _drill_statements(cycle, fk, *_a):
    qs = D.questions(cycle, fk)
    rows = [html.Tr([
        html.Td(q['theme'] or '--', style={'color': 'var(--t2)',
                                           'whiteSpace': 'nowrap',
                                           'fontSize': '11px'}),
        html.Td(q['question'], style={'fontSize': '11.5px'}),
        html.Td(C.me_chip(q['score']), className='r'),
        html.Td(f"{C.fmt(q['pct'], 1)}%", className='r mono'),
        html.Td(C.num(q['n']), className='r mono', style={'color': 'var(--t3)'}),
    ]) for q in qs]
    return ('Every statement, weakest first',
            f'{len(qs)} statements \u00b7 {D.CYCLE_LABEL.get(cycle)}',
            [C.table(['Theme', 'Statement', ('Score', 'r'), ('% pos', 'r'),
                      ('n', 'r')], rows, min_width=520)])


def _drill_gender(cycle, fk, *_a):
    gm = D.gender_matrix(cycle, fk)
    cells = []
    for g in gm:
        cells.append(C.stat_row(
            f"{'Man' if g['manager'] == 'Male' else 'Woman'} manager "
            f"\u2192 {'man' if g['reportee'] == 'Male' else 'woman'} reportee",
            f"NPS {C.fmt(g['nps'], 1)}",
            f"ME {C.fmt(g['me'])} \u00b7 n={g['n']:,}"))
    seg = D.segment(cycle, 'Reportee gender', fk)
    srows = [html.Tr([
        html.Td(r['label'], style={'fontWeight': '500'}),
        html.Td(C.num(r['n']), className='r mono'),
        html.Td(C.me_chip(r['me']), className='r'),
        html.Td(C.nps_chip(r['nps']), className='r'),
    ]) for r in seg]
    return ('The gender gap',
            D.CYCLE_LABEL.get(cycle),
            [html.Div([C.ml('EVERY PAIRING')] + cells),
             html.Div([C.ml('BY REPORTEE GENDER, WHOEVER THE MANAGER IS'),
                       C.table(['Reportee gender', ('n', 'r'), ('ME', 'r'),
                                ('NPS', 'r')], srows, min_width=340),
                       C.foot('the gap holds whichever gender the manager is, '
                              'so it is not a manager-matching effect')])])


def _drill_coverage(cycle, fk, *_a):
    m = D.managers()
    mc = m[m['cycle'] == cycle].copy()
    if fk:
        mc = mc[mc['manager_email'].isin(
            D.subset(cycle, fk)['manager_email'].unique())]
    g = mc.groupby('manager_bu').agg(
        rated=('manager_email', 'nunique'),
        scored=('cycle_visibility', lambda s: int((s == 'Yes').sum())))
    g = g[g['rated'] >= 5].sort_values('rated', ascending=False)
    rows = [html.Tr([
        html.Td(str(bu), style={'fontWeight': '500'}),
        html.Td(C.num(r.rated), className='r mono'),
        html.Td(C.num(r.scored), className='r mono'),
        html.Td(html.Span(f'{r.scored / r.rated * 100:.0f}%',
                          className='chip ' +
                          ('b-ok' if r.scored / r.rated >= .6 else 'b-warn')),
                className='r'),
    ]) for bu, r in g.iterrows()]
    return ('Who is missing from the scores',
            f'{D.CYCLE_LABEL.get(cycle)} \u00b7 3-response minimum',
            [C.table(['Business unit', ('Rated', 'r'), ('Scored', 'r'),
                      ('Share', 'r')], rows, min_width=380),
             C.foot('a manager below three responses is suppressed everywhere '
                    'in this dashboard, matching the report\u2019s own rule')])
