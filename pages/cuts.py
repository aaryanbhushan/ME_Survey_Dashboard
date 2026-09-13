"""Cuts — every breakdown and both hierarchy rollups.

Replaces six near-identical pivot pages in the PBIP (Summary View, Managers in
Span, ME & NPS Dimension Analysis) with one table and a dimension switcher,
plus the two hierarchy pivots the report drilled by hand.
"""
from dash import html

import components as C
import data as D
import page_common as PC

def layout(cycle=None, dim=None, fam=None, lvl=None, **params):
    cycle = PC.resolve_cycle(cycle)
    filters = D.parse_filters(params)
    fk = D.filter_key(filters)
    dim = dim if dim in D.DIMENSIONS else 'Business unit'
    fam = fam if fam in D.HIERARCHIES else 'Manager'
    levels = [l for l, _c in D.HIERARCHIES[fam]]
    lvl = lvl if lvl in levels else levels[0]
    keep = {'dim': dim, 'fam': fam, 'lvl': lvl}
    return html.Div([
        PC.filter_bar(cycle, filters, '/cuts', keep),
        PC.active_chips(cycle, filters, '/cuts', keep),
        _segments(cycle, dim, keep, fk),
        _hierarchy(cycle, fam, lvl, keep, fk),
        _matrix_and_coverage(cycle, fk, keep),
    ], className='me-root')


# ── dimension switcher ────────────────────────────────────────────────────

def _segments(cycle, dim, keep, fk=()):
    # No minimum base: a cut should show every one of its values, so the
    # reader can see the whole population rather than wonder which values
    # were dropped and why. segment() returns biggest-first, so when a cut is
    # too long to read the rows kept are the largest.
    rows_data = D.segment(cycle, dim, fk, min_n=0)
    found = len(rows_data)
    rows_data = rows_data[:D.MAX_SEGMENT_ROWS]
    capped = found > len(rows_data)
    if dim in D.ORDERED_DIMENSIONS:
        rows_data = sorted(rows_data,
                           key=lambda r: D.label_sort_key(r['label']))
    org = D.headline(cycle, fk)['me']
    against = D.CYCLE_LABEL.get(D.prev_cycle(cycle), '--')
    col = D.DIMENSIONS[dim]
    next_dim = D.DRILL_NEXT.get(dim)
    rows = []
    for r in rows_data:
        # The name cross-filters the whole page; the `+` beside it opens the
        # level below, scoped to this row. Two different jobs, so two targets
        # rather than one click that tries to guess which was meant.
        name = [PC.xfilter(r['label'], col, r['label'], cycle, fk,
                           '/cuts', keep)]
        if next_dim:
            name.append(PC.drill_link(col, r['label'], next_dim, cycle, fk,
                                      '/cuts', keep))
        rows.append(html.Tr([
            html.Td(name, style={'fontWeight': '500'}),
            html.Td(C.num(r['n']), className='r mono'),
            html.Td(C.num(r['managers']), className='r mono',
                    style={'color': 'var(--t3)'}),
            html.Td(C.me_chip(r['me']), className='r'),
            html.Td(C.bar(r['me'], 3.0, 3.9, mark=org), style={'width': '100px'}),
            html.Td(C.delta(r['me_delta']), className='r'),
            html.Td(C.nps_chip(r['nps']), className='r'),
            html.Td(C.delta(r['nps_delta'], 1), className='r'),
        ], title='\n'.join([
            f"{r['label']}",
            f"ME score {C.fmt(r['me'])} of 4"
            + (f" (was {C.fmt(r['me_prev'])})" if r.get('me_prev') else ''),
            f"Manager NPS {C.fmt(r['nps'], 1)}"
            + (f" (was {C.fmt(r['nps_prev'], 1)})" if r.get('nps_prev') else ''),
            f"{r['n']:,} respondents across {r['managers']:,} managers",
            '',
            f"Click the name to filter the page to it"
            + (f" · click + for the {next_dim.lower()}s inside it"
               if next_dim else ''),
        ])))

    picker = html.Div(
        PC.pill_links('/cuts', 'dim', [(k, k) for k in D.DIMENSIONS], dim,
                      dict({'cycle': cycle, 'fam': keep['fam'], 'lvl': keep['lvl']},
                           **PC.filter_qs(fk))),
        className='pillbtns')

    return C.section(
        'Cut the org any way you need', note=f'{len(D.DIMENSIONS)} dimensions',
        desc='One table replaces six separate pivot pages, and offers every '
             'attribute the report’s Dimension slicer did. Every cut describes '
             'the manager being rated, except reportee gender. Click a name to '
             'filter the page to it, or the + beside a business unit or '
             'department to open what sits inside it.',
        children=[
            picker,
            html.Div([
                C.table([dim, ('n', 'r'), ('Mgrs', 'r'), ('ME', 'r'), '',
                         (f'Δ ME vs {against}', 'r'), ('NPS', 'r'),
                         (f'Δ NPS vs {against}', 'r')],
                        rows, min_width=780),
                C.legend(C.ME_LEGEND, 'ME BANDS'),
                C.legend(C.NPS_LEGEND, 'NPS BANDS'),
                C.foot('bar spans 3.00–3.90 · tick is the org average'),
            ] + ([C.foot(f'{dim} has {found} values; the '
                         f'{len(rows_data)} largest are shown')]
                 if capped else []), className='box'),
        ])




# ── hierarchy rollup ──────────────────────────────────────────────────────

def _hierarchy(cycle, family, level, keep, fk=()):
    levels = D.HIERARCHIES[family]
    col = dict(levels)[level]

    rows_data = D.hierarchy(cycle, family, col, fk)
    against = D.CYCLE_LABEL.get(D.prev_cycle(cycle), '--')
    rows = []
    for r in rows_data:
        # The hierarchy is today's org chart. A leader who joined after a
        # cycle ran did not lead that span then, so their name must not carry
        # its movement. Marked in the row, and the delta is withheld upstream.
        joined_later = r.get('in_post') is False
        no_prev = r.get('in_post_prev') is False
        note = []
        if joined_later:
            note.append('joined after this cycle')
        elif no_prev:
            note.append(f"joined after {against}")

        label = [PC.xfilter(r['label'], col, r['label'], cycle, fk,
                            '/cuts', keep,
                            tip=f"Filter the whole page to everyone under "
                                f"{r['label']}")]
        if note:
            label.append(html.Span('NEW IN SEAT', className='seat-tag'))

        rows.append(html.Tr([
            html.Td(label, className='mono',
                    style={'fontWeight': '500', 'fontSize': '11.5px'}),
            html.Td(C.num(r['n']), className='r mono'),
            html.Td(C.num(r['managers']), className='r mono',
                    style={'color': 'var(--t3)'}),
            html.Td(C.me_chip(r['me']), className='r'),
            html.Td(C.delta(r['me_delta']) if r['me_delta'] is not None
                    else html.Span('--', className='seat-na'), className='r'),
            html.Td(C.nps_chip(r['nps']), className='r'),
            html.Td(C.delta(r['nps_delta'], 1) if r['nps_delta'] is not None
                    else html.Span('--', className='seat-na'), className='r'),
            html.Td(C.num(r['promoters']), className='r mono',
                    style={'color': 'var(--good)'}),
            html.Td(C.num(r['passives']), className='r mono',
                    style={'color': 'var(--t3)'}),
            html.Td(C.num(r['detractors']), className='r mono',
                    style={'color': 'var(--bad)'}),
        ], title='\n'.join([
            r['label'],
            f"ME score {C.fmt(r['me'])} of 4   |   NPS {C.fmt(r['nps'], 1)}",
            f"{r['n']:,} respondents across {r['managers']:,} managers below them",
            f"{r['promoters']:,} promoters, {r['passives']:,} passive, "
            f"{r['detractors']:,} detractors",
        ] + ([
            '',
            f"Joined the group {r['joined'].date()}"
            if r.get('joined') is not None else '',
            'The hierarchy is the org as it stands today, so this span’s '
            'earlier results were earned under someone else. The change '
            'against ' + against + ' is the seat’s, not this '
            'leader’s, so it is not shown.',
        ] if note else []))))

    # Switching family resets the level: the two hierarchies do not share
    # level names, so carrying L8 into HRBP would land on nothing.
    buttons = PC.pill_links(
        '/cuts', 'fam', [(f, f + ' hierarchy') for f in D.HIERARCHIES], family,
        dict({'cycle': cycle, 'dim': keep['dim']}, **PC.filter_qs(fk)))
    buttons.append(html.Span('LEVEL', className='ml sm',
                             style={'alignSelf': 'center', 'margin': '0 4px'}))
    buttons += PC.pill_links(
        '/cuts', 'lvl', [(l, l) for l, _c in levels], level,
        dict({'cycle': cycle, 'dim': keep['dim'], 'fam': family}, **PC.filter_qs(fk)))

    return C.section(
        'Roll up the hierarchy', alt=True,
        note=f'{len(rows_data)} at {level}',
        desc='The report’s Scores by Manager Hierarchy and Scores by HR '
             'Hierarchy pivots. Every rated manager rolls up to the leader — or '
             'the HRBP — above them. Levels under 30 responses are hidden.',
        children=[
            html.Div(buttons, className='pillbtns'),
            html.Div([
                C.table([f'{"Leader" if family == "Manager" else "HRBP"} ({level})',
                         ('n', 'r'), ('Mgrs', 'r'), ('ME', 'r'),
                         (f'Δ ME vs {against}', 'r'), ('NPS', 'r'),
                         (f'Δ NPS vs {against}', 'r'), ('Prom', 'r'),
                         ('Pass', 'r'), ('Detr', 'r')], rows, min_width=900),
                C.legend(C.ME_LEGEND, 'ME BANDS'),
                C.legend(C.NPS_LEGEND, 'NPS BANDS'),
                C.foot('promoter / passive / detractor counts as the report '
                       'shows them · top 15 by response volume'),
            ], className='box'),
        ])


    if trig.get('type') == 'hierfam':
        cur['family'] = trig['family']
        # Levels differ between the two hierarchies, so reset to the top one
        # rather than carry an L8 that HRBP does not have.
        cur['level'] = D.HIERARCHIES[cur['family']][0][0]
    elif trig.get('type') == 'hierlvl':
        cur['level'] = trig['level']
    else:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
    return cur


# ── matrix + coverage ─────────────────────────────────────────────────────

def _matrix_and_coverage(cycle, fk=(), keep=None):
    return C.section(
        'Two views the report could not show together', None,
        'The gender pairing matrix, and how many rated managers actually clear '
        'the three-response bar.',
        children=[html.Div([
            C.box('Manager gender × reportee gender',
                  note=D.CYCLE_LABEL.get(cycle),
                  desc='Manager NPS in each pairing, with the ME score and base '
                       'beneath it. Click a cell to filter the page to it.',
                  children=_matrix(cycle, fk, keep)),
            C.box('Coverage by cycle',
                  desc='A manager is only scored once at least 3 people have '
                       'rated them.',
                  children=_coverage(cycle, fk)),
        ], className='grid g23')])


def _matrix(cycle, fk=(), keep=None):
    gm = D.gender_matrix(cycle, fk)
    cells = [html.Div(className='mx-h'),
             html.Div('Reportee: man', className='mx-h'),
             html.Div('Reportee: woman', className='mx-h')]
    small = None
    for mg in ['Male', 'Female']:
        cells.append(html.Div(f'Manager: {"man" if mg == "Male" else "woman"}',
                              className='mx-r'))
        for rg in ['Male', 'Female']:
            c = next(x for x in gm if x['manager'] == mg and x['reportee'] == rg)
            if mg == 'Female' and rg == 'Female':
                small = c['n']
            cells.append(PC.xfilter(
                html.Div([
                    html.Div(C.fmt(c['nps'], 1), className='v'),
                    html.Div(f"ME {C.fmt(c['me'])} · n={C.num(c['n'])}",
                             className='s'),
                ], className=f"mx-c {D.band_class(c['nps'], D.NPS_BANDS)}"),
                'manager_gender', mg, cycle, fk, '/cuts', keep,
                className='xf-cell',
                also={'reportee_gender': rg},
                tip='\n'.join([
                    f"{'Man' if mg == 'Male' else 'Woman'} manager rated by a "
                    f"{'man' if rg == 'Male' else 'woman'}",
                    f"Manager NPS {C.fmt(c['nps'], 1)}",
                    f"ME score {C.fmt(c['me'])} of 4",
                    f"{c['n']:,} respondents",
                    '',
                    'Click to filter the whole page to this pairing',
                ])))
    return html.Div([
        html.Div(cells, className='mx'),
        C.legend(C.NPS_LEGEND, 'NPS BANDS'),
        html.P(f'The women–women cell rests on {C.num(small)} responses; treat '
               f'the exact figure with care. The pattern across all four cells '
               f'holds on much larger bases.', className='note-p'),
    ])


def _coverage(cycle, fk=()):
    rows = []
    for c in D.coverage(fk):
        cur = c['cycle'] == cycle
        rows.append(html.Tr([
            html.Td(D.CYCLE_LABEL.get(c['cycle'], c['cycle']), className='mono',
                    style={'fontWeight': '600' if cur else '400',
                           'color': 'var(--orange-deep)' if cur else 'inherit'}),
            html.Td(C.num(c['respondents']), className='r mono'),
            html.Td(C.num(c['managers']), className='r mono'),
            html.Td(C.num(c['visible']), className='r mono'),
            # share is None when the filtered population has no managers in
            # this cycle at all — which happens the moment you filter to a
            # single manager who did not appear in every cycle. Formatting
            # that with ':.0f' raised "unsupported format string passed to
            # NoneType.__format__" and took the whole page down. A dash, and
            # no chip colour, because there is nothing to rate.
            html.Td(html.Span(
                '--' if c['share'] is None else f"{c['share']:.0f}%",
                className='chip ' + ('b-none' if c['share'] is None
                                     else 'b-ok' if c['share'] >= 60
                                     else 'b-warn')),
                className='r'),
        ], title='\n'.join([
            D.CYCLE_LABEL.get(c['cycle'], c['cycle']),
            f"{c['respondents']:,} respondents",
            f"{c['visible']:,} of {c['managers']:,} managers had 3+ responses "
            f"and could be scored",
        ])))
    return html.Div([
        C.table(['Cycle', ('Respondents', 'r'), ('Managers rated', 'r'),
                 ('Scored (3+)', 'r'), ('Share', 'r')], rows, min_width=460),
    ])
