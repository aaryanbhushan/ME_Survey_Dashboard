"""Action Queue — managers below the 25th percentile for their own grade.

Replaces the PBIP's Individual Manager View, but inverted: rather than making
someone pick a manager from a slicer to find out whether there is a problem,
the page ranks the managers who need a conversation and opens the detail on
click.
"""
from dash import dcc, html

import components as C
import data as D
import page_common as PC

TAG_CLASS = {'PERSISTENT': 'tag-persistent', 'NEW': 'tag-new',
             'FIRST CYCLE': 'tag-first'}


def layout(cycle=None, tag=None, mgr=None, **params):
    cycle = PC.resolve_cycle(cycle)
    filters = D.parse_filters(params)
    fk = D.filter_key(filters)
    rows = D.action_queue(cycle, 25, fk)
    tags = {'ALL'} | {r['tag'] for r in rows}
    tag = tag if tag in tags else 'ALL'
    shown = [r for r in rows if tag == 'ALL' or r['tag'] == tag]

    counts = {}
    for r in rows:
        counts[r['tag']] = counts.get(r['tag'], 0) + 1
    opts = [('ALL', f'ALL {len(rows)}')] + [(k, f'{k} {v}')
                                            for k, v in counts.items()]
    pills = PC.pill_links('/queue', 'tag', opts, tag,
                          dict({'cycle': cycle}, **PC.filter_qs(fk)))

    h = D.headline(cycle, fk)
    detail = D.manager_detail(mgr, cycle) if mgr else None
    return html.Div([
        PC.filter_bar(cycle, filters, '/queue', {'tag': tag}),
        PC.active_chips(cycle, filters, '/queue', {'tag': tag}),
        C.section(
            f'Action queue · {D.CYCLE_LABEL.get(cycle, cycle)}',
            note=f"{len(rows)} of {C.num(h['below_p25'])} in the bottom quarter",
            desc='Managers in the weakest quarter for their own grade — not a '
                 'raw score cut-off, because 3.30 means something different '
                 'at grade 4 than at grade 11. Ranked by how far below the '
                 'bar they sit multiplied by how many people that affects. '
                 'Click a row for the full breakdown. The comparison is made '
                 'within grade and across scored managers only, which is '
                 'stricter than the retired report’s single org-wide cut.',
            children=[
                html.Div(pills, className='pillbtns'),
                html.Div([_row(i, r, cycle, tag) for i, r in enumerate(shown)]),
                C.foot(f'showing {len(shown)} of {len(rows)} · ranked by gap × '
                       f'people affected · a manager never sees their own '
                       f'scorecard in the live app'),
            ]),
        _drawer_body(detail, cycle, tag) if detail else html.Div(),
    ], className='me-root')


def _row(i, r, cycle, tag):
    href = f"/queue?cycle={cycle}&tag={tag}&mgr={r['manager_email']}"
    return dcc.Link(href=href, className='q-link', children=html.Div([
        html.Div(f'{i + 1:02d}', className='rank mono'),
        html.Div([
            html.Div([
                html.B(r['manager_email']),
                html.Span(r['tag'], className=f"tag {TAG_CLASS.get(r['tag'], '')}"),
                html.Span(f"{r['bu']} · GRADE {r['grade']}", className='ml sm'),
            ], className='ttl'),
            html.Div([
                f"{r['n']} people rated them. Sits ",
                html.B(f"{r['gap']:.2f}"),
                f" below the {r['p25']:.2f} bar for grade {r['grade']}",
                (f", and was at {r['prev']:.2f} last cycle."
                 if r['prev'] is not None else ', and was not scored last cycle.'),
            ], className='note'),
        ], className='main'),
        html.Div([
            html.Div(C.fmt(r['score']), className='sc',
                     style={'color': 'var(--bad)'}),
            html.Div(f"NPS {C.fmt(r['nps'], 1)}", className='sub'),
            html.Div(f"{r['n']} RESPONSES", className='sub'),
        ], className='right'),
    ], className='q'))





# ── drawer ────────────────────────────────────────────────────────────────



def _drawer_body(d, cycle, tag):
    org_themes = {t['theme']: t['score'] for t in D.themes(d['cycle'])}

    theme_rows = []
    for name, v in d['themes']:
        org = org_themes.get(name)
        theme_rows.append(html.Div([
            html.Div(name, style={'font': '400 12px var(--sans)'}),
            C.bar(v, 1, 4, mark=org, cls=D.band_class(v, D.ME_BANDS)),
            html.Div(C.fmt(v), className='mono',
                     style={'width': '46px', 'textAlign': 'right',
                            'font': '600 12px var(--mono)'}),
        ], style={'display': 'grid',
                  'gridTemplateColumns': '1fr 108px 46px',
                  'gap': '9px', 'alignItems': 'center', 'padding': '5px 0'}))

    tot = d['promoters'] + d['passives'] + d['detractors']
    mix = []
    if tot:
        for key, cls in [('promoters', 'm-p'), ('passives', 'm-a'),
                         ('detractors', 'm-d')]:
            if d[key]:
                mix.append(html.Div(str(d[key]), className=cls,
                                    style={'flex': str(d[key])}))

    verbatims = [
        html.Div([html.Span(q, className='vq'), a], className='verbatim')
        for q, a in d['verbatims']
    ] or [html.Div('No open-ended responses in this cycle.', className='sd')]

    return C.side_panel(
        d['manager_email'],
        f"{str(d['bu']).upper()} · GRADE {d['grade']} · "
        f"{d['n']} RESPONSES · {D.CYCLE_LABEL.get(d['cycle'], '').upper()}",
        f'/queue?cycle={cycle}&tag={tag}',
        [
                html.Div([
                    C.ml('THIS CYCLE'),
                    html.Div([
                        html.Div([html.Div(C.fmt(d['score']), className='v',
                                           style={'color': 'var(--bad)'}),
                                  html.Div('ME score', className='l')],
                                 className='dstat'),
                        html.Div([html.Div(C.fmt(d['nps'], 1), className='v'),
                                  html.Div('Manager NPS', className='l')],
                                 className='dstat'),
                        html.Div([html.Div(C.num(d['n']), className='v'),
                                  html.Div('Responses', className='l')],
                                 className='dstat'),
                    ], className='dstats'),
                ]),
                html.Div([C.ml('RECOMMENDATION MIX'),
                          html.Div(mix, className='mix')]) if mix else html.Div(),
                html.Div([C.ml('SCORE BY THEME'), html.Div(theme_rows),
                          C.foot('tick marks the org average for that theme')]),
                html.Div([
                    C.ml('LOWEST-SCORING STATEMENTS'),
                    html.Div([
                        html.Div([
                            html.Span(q, style={'color': 'var(--t2)'}),
                            html.Span(C.fmt(v), className='mono',
                                      style={'fontWeight': '600',
                                             'color': 'var(--bad)',
                                             'flex': 'none'}),
                        ], style={'display': 'flex', 'gap': '10px',
                                  'justifyContent': 'space-between',
                                  'padding': '6px 0',
                                  'borderBottom': '1px solid rgba(0,0,0,.05)',
                                  'font': '400 12px var(--sans)'})
                        for q, v in d['low_questions']
                    ]),
                ]),
                html.Div([C.ml('OPEN-ENDED FEEDBACK'), html.Div(verbatims)]),
        ])
