"""Shared UI pieces, in the house style.

The visual language is the Psychological Safety console's: warm neutrals,
IBM Plex Mono for micro-labels and figures, Instrument Sans for prose, Swiggy
orange reserved for the selected cycle and for brand chrome — never for a
data series that carries meaning on its own.
"""
from dash import dcc, html

import data as D

FMT2 = '{:.2f}'.format
FMT1 = '{:.1f}'.format


def fmt(v, digits=2, dash='--'):
    if v is None:
        return dash
    try:
        if v != v:  # NaN
            return dash
    except TypeError:
        return dash
    return f'{v:.{digits}f}'


def num(v):
    return '--' if v is None else f'{int(v):,}'


def ml(text, small=False):
    """A micro-label: mono, upper, letter-spaced. The house's section marker."""
    return html.Div(text, className='ml sm' if small else 'ml')


def delta(value, digits=2, good_is_up=True, suffix=''):
    """A movement chip. Arrow plus magnitude, coloured by whether the
    direction is good — never by sign alone, because a fall in
    'managers with negative NPS' is good news."""
    if value is None or value != value:
        return html.Span('n/a', className='dlt nil')
    r = round(value, digits)
    if r == 0:
        return html.Span(f'0.{"0" * digits}{suffix}', className='dlt nil')
    positive = r > 0
    ok = positive if good_is_up else not positive
    arrow = '▲' if positive else '▼'
    return html.Span(f'{arrow} {abs(r):.{digits}f}{suffix}',
                     className=f'dlt {"up" if ok else "dn"}')


def chip(value, bands, digits=2):
    """A RAG score chip — the PBIP's red-amber-green pivot gradient, cut into
    four legible steps instead of a continuous ramp."""
    cls = D.band_class(value, bands)
    return html.Span(fmt(value, digits), className=f'chip {cls}')


def me_chip(v):
    return chip(v, D.ME_BANDS, 2)


def nps_chip(v):
    return chip(v, D.NPS_BANDS, 1)


def tip(component, text):
    """Attach a hover explanation.

    Uses the native title attribute rather than a CSS pseudo-element: most of
    these live inside horizontally-scrolling table wrappers, and a
    ::after tooltip is clipped by the very overflow that makes those tables
    usable. The browser's own tooltip is never clipped.
    """
    if text:
        component.title = text
    return component


def side_panel(title, subtitle, close_href, body):
    """The right-hand drill panel, shared by the insight cards and the queue.

    Sits BELOW the app header rather than over it, so the dashboard title and
    the refresh control stay reachable while a panel is open.
    """
    return html.Div([
        dcc.Link('', href=close_href, className='scrim'),
        html.Div([
            html.Div([
                html.Div([html.H3(title), html.Div(subtitle, className='s')]),
                dcc.Link('\u00d7', href=close_href, className='dx', title='Close'),
            ], className='dh'),
            html.Div(body, className='db'),
        ], className='drawer'),
    ])


def stat_row(label, value, sub=None):
    return html.Div([
        html.Div(label, style={'font': '400 12px var(--sans)'}),
        html.Div([html.Span(value, className='mono',
                            style={'font': '600 12.5px var(--mono)'}),
                  html.Span(f' {sub}', className='ml sm') if sub else ''],
                 style={'textAlign': 'right'}),
    ], style={'display': 'flex', 'justifyContent': 'space-between',
              'gap': '12px', 'padding': '6px 0',
              'borderBottom': '1px solid rgba(0,0,0,.05)'})


def section(title, note=None, desc=None, children=None, alt=False):
    head = [html.H2(title)]
    if note:
        head.append(html.Span(note, className='note'))
    body = [html.Div(head, className='sh')]
    if desc:
        body.append(html.Div(desc, className='sd'))
    if children:
        body.extend(children if isinstance(children, list) else [children])
    return html.Div(html.Div(body, className='inner'),
                    className='sec alt' if alt else 'sec')


def box(title, note=None, desc=None, children=None):
    head = [html.H2(title)]
    if note:
        head.append(html.Span(note, className='note'))
    body = [html.Div(head, className='sh')]
    if desc:
        body.append(html.Div(desc, className='sd'))
    if children:
        body.extend(children if isinstance(children, list) else [children])
    return html.Div(body, className='box')


def bar(value, lo, hi, mark=None, cls=''):
    """A thin track with the value filled and an optional tick for the org
    average — so a number is readable against its benchmark, not just in
    isolation."""
    pct = 0 if value is None else max(0, min(100, (value - lo) / (hi - lo) * 100))
    kids = [html.Div(className=f'bar-fill {cls}', style={'width': f'{pct:.1f}%'})]
    if mark is not None:
        mpct = max(0, min(100, (mark - lo) / (hi - lo) * 100))
        kids.append(html.Div(className='avg-tick', style={'left': f'{mpct:.1f}%'}))
    return html.Div(kids, className='bar-track')


def table(headers, rows, className='', min_width=None):
    """A plain table in a horizontal-scroll wrapper.

    Wide tables scroll inside their own container rather than pushing the
    page sideways — a body that scrolls horizontally is the fastest way to
    make a dashboard feel broken.
    """
    thead = html.Thead(html.Tr([
        html.Th(h[0] if isinstance(h, tuple) else h,
                className=h[1] if isinstance(h, tuple) else '')
        for h in headers]))
    style = {'minWidth': f'{min_width}px'} if min_width else None
    return html.Div(
        html.Table([thead, html.Tbody(rows)], className=className, style=style),
        className='xs')


def legend(items, title=None):
    kids = []
    if title:
        kids.append(html.Span(title, className='ml sm'))
    for label, cls in items:
        kids.append(html.Span([html.I(className=cls), label]))
    return html.Div(kids, className='legend')


ME_LEGEND = [('3.60+', 'sw b-good'), ('3.46-3.59', 'sw b-ok'),
             ('3.20-3.45', 'sw b-warn'), ('under 3.20', 'sw b-bad')]
NPS_LEGEND = [('55+', 'sw b-good'), ('40-54', 'sw b-ok'),
              ('0-39', 'sw b-warn'), ('negative', 'sw b-bad')]


def cycle_picker(current, id_='cycle-picker'):
    return html.Div([
        html.Button(D.CYCLE_LABEL.get(c, c).upper().replace(' ', '_'),
                    id={'type': 'cyc', 'cycle': c},
                    className='cyc-btn' + (' on' if c == current else ''),
                    n_clicks=0)
        for c in D.cycles()
    ], className='cyc', id=id_)


def foot(text):
    return html.Div(text, className='foot')
