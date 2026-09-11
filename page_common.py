"""Pieces every page shares: the scope bar, the cycle picker wiring, and the
hero band the Pulse page leads with.
"""
from urllib.parse import urlencode

from dash import dcc, html

import components as C
import data as D


def href(path, qs):
    """Build a URL with the query string properly encoded.

    This must not be a raw f-string join. The values that ride in here are
    real data — BU names with spaces and ampersands ("Dine Out & Lynk"),
    department names with commas, manager emails — and an unencoded `&`
    silently splits one parameter into two and drops the filter. The router
    reads the other end with parse_qsl, so encoding here round-trips exactly.
    """
    clean = {k: v for k, v in qs.items() if v not in (None, '')}
    return path + ('?' + urlencode(clean) if clean else '')


def pill_links(path, param, options, current, extra=None):
    """Selector rendered as links, not callbacks.

    State lives in the query string, so every page renders server-side in one
    pass from layout(). The earlier version pushed state through dcc.Store and
    rebuilt the page from a callback — under Dash pages the initial dispatch
    never fired, so the dashboard loaded blank until something was clicked.
    Links have no such failure mode, and the view is shareable by URL.
    """
    extra = extra or {}
    out = []
    for value, label in options:
        qs = dict(extra); qs[param] = value
        out.append(dcc.Link(label, href=href(path, qs),
                            className='pillbtn' + (' on' if value == current else '')))
    return out


def drill_link(col, value, next_dim, cycle, fkey, path='/cuts', extra=None):
    """The `+` that opens one level down, inside the value clicked.

    Distinct from xfilter in two ways that matter. It switches the dimension
    as well as narrowing, so the table below reads as the next level down; and
    it always ADDS the filter rather than toggling it, because a `+` that
    silently removed the filter it had just applied would be unusable.
    """
    qs = dict(extra or {})
    qs['cycle'] = cycle
    qs.update(filter_qs(fkey))
    qs['dim'] = next_dim
    qs[col] = '' if value is None else str(value)
    return dcc.Link(
        '+', href=href(path, qs), className='xf-plus',
        title=f'Open the {next_dim.lower()}s within {value}')


def xfilter(children, col, value, cycle, fkey, path='/', extra=None,
            className='', tip=None, also=None):
    """Render a value so that clicking it narrows the WHOLE page to it.

    Cross-filtering needs no new machinery here: every page already renders
    server-side from the query string, so "filter to this BU" is just a link
    that adds one more parameter. No callback, no store, no chart event — and
    the filtered view stays shareable and back-button-able like any other URL.

    Clicking a value that is already the only one selected clears it again,
    so a click is always its own undo and the reader is never stranded in a
    filter they cannot find in the bar.
    """
    # `also` lets one click set several columns at once — a cell in the
    # gender matrix is a manager gender AND a reportee gender, and filtering
    # to only one of them would not be the cell the reader clicked.
    pairs = {col: '' if value is None else str(value)}
    for k, v in (also or {}).items():
        pairs[k] = '' if v is None else str(v)

    qs = dict(extra or {})
    qs['cycle'] = cycle
    qs.update(filter_qs(fkey))

    have = dict(fkey or ())
    active = all(have.get(k) is not None and tuple(have[k]) == (v,)
                 for k, v in pairs.items())
    for k, v in pairs.items():
        if active:
            qs.pop(k, None)
        else:
            qs[k] = v

    shown = ' + '.join(f'{D.FILTER_LABEL.get(k, k)} = {v}'
                       for k, v in pairs.items())
    return dcc.Link(
        children, href=href(path, qs),
        className=('xf-link' + (' on' if active else '')
                   + (' ' + className if className else '')),
        title=tip or (f'Clear this filter ({shown})' if active else
                      f'Filter the whole page to {shown}'))


def cycle_links(path, current, extra=None):
    return html.Div(
        pill_links(path, 'cycle',
                   [(c, D.CYCLE_LABEL.get(c, c).upper().replace(' ', '_'))
                    for c in D.cycles()],
                   current, extra),
        className='cyc')


def filter_qs(fkey):
    """Filter selections as query-string pairs, so an in-page link (a
    dimension switch, a drill-down) does not silently drop the filters."""
    return {col: '~'.join(vals) for col, vals in (fkey or ())}


def _group(label, control):
    return html.Div([html.Label(label, className='filter-label'), control],
                    className='filter-group')


def filter_bar(cycle, filters, path='/', extra=None):
    """Cycle picker plus one dropdown per filterable attribute.

    Same shape as the Psychological Safety console's bar — label above
    control, multi-selects defaulting to "All", a Clear all at the end — so
    the shared stylesheet carries over and the two dashboards feel like one
    product.

    The controls write to the query string rather than to a Store, which is
    what lets every page render server-side in a single pass and makes any
    filtered view shareable as a URL.
    """
    extra = extra or {}
    controls = [
        _group('Survey cycle', dcc.Dropdown(
            id='f-cycle',
            options=[{'label': D.CYCLE_LABEL.get(c, c), 'value': c}
                     for c in D.cycles()],
            value=cycle, clearable=False, className='ps-select')),
    ]
    for col, label in D.FILTER_FIELDS:
        controls.append(_group(label, dcc.Dropdown(
            id={'type': 'f', 'field': col},
            options=[{'label': v, 'value': v} for v in D.options(col)],
            value=filters.get(col, []),
            multi=True, placeholder='All',
            className='ps-select ps-select--wide')))

    controls.append(html.Div(
        html.Button('Clear all', id='f-clear', className='ps-clear',
                    n_clicks=0),
        className='filter-group filter-group--action'))

    # The page path and any non-filter state (which dimension a page is
    # showing) ride along so the apply-callback can rebuild the whole URL.
    controls.append(dcc.Store(id='f-context',
                              data={'path': path, 'extra': extra}))
    return html.Div(controls, className='ps-filter-bar filter-bar')


def active_chips(cycle, filters, path, extra=None):
    """What is currently narrowing the view, stated in words.

    A filter bar with eleven collapsed dropdowns hides its own state; a chip
    row does not, and it is the difference between a stakeholder trusting a
    number and quietly mistrusting it.
    """
    extra = extra or {}
    chips = [html.Span([html.B(D.CYCLE_LABEL.get(cycle, cycle)), ' cycle'],
                       className='xf-chip xf-chip--cycle')]
    if D.is_in_flight(cycle):
        chips.append(html.Span('STILL IN FIELDWORK', className='tag tag-new'))

    fkey = D.filter_key(filters)
    qs_all = filter_qs(fkey)
    base = dict(extra); base['cycle'] = cycle

    for col, vals in filters.items():
        shown = ', '.join(vals[:2]) + (f' +{len(vals) - 2}' if len(vals) > 2 else '')
        label = D.FILTER_LABEL.get(col, col)
        # Every chip carries its own remove link. A cross-filter clicked from a
        # table can land on a column the bar has no dropdown for (a hierarchy
        # leader), so without this there is no way to undo one short of
        # editing the URL by hand.
        rest = {c: v for c, v in qs_all.items() if c != col}
        chips.append(html.Span([
            html.B(label), ': ', shown,
            dcc.Link('×', href=href(path, dict(base, **rest)),
                     className='xf-chip-x',
                     title=f'Remove this {label} filter'),
        ], className='xf-chip'))

    if filters:
        chips.append(dcc.Link('clear all', href=href(path, base),
                              className='xf-clear-link'))
    else:
        chips.append(html.Span('no filters — showing the whole org',
                               className='xf-none'))
    return html.Div(chips, className='ps-xf-bar')


def resolve_cycle(store_value):
    cs = D.cycles()
    return store_value if store_value in cs else D.default_cycle()


def spark(values, cycles, current):
    """A four-bar sparkline with the selected cycle picked out in orange.

    Scaled to the observed range rather than to zero: these scores live in a
    0.3-wide band on a 1-4 scale, and a zero baseline would flatten every
    move the dashboard exists to show. The axis labels carry the values so
    the compressed scale cannot mislead.
    """
    vals = [v for v in values if v is not None]
    if not vals:
        return html.Div()
    lo, hi = min(vals) - 0.06, max(vals) + 0.02
    bars = []
    for c, v in zip(cycles, values):
        pct = 6 if v is None else max(6, (v - lo) / (hi - lo) * 100)
        bars.append(html.Div(className='cur' if c == current else '',
                             style={'height': f'{pct:.0f}%'}))
    return html.Div([
        html.Div(bars, className='spark'),
        html.Div([html.Span(f'{D.CYCLE_LABEL.get(c, c).upper().replace(" ", "_")} '
                            f'{C.fmt(v)}') for c, v in zip(cycles, values)],
                 className='spark-x'),
    ])
