"""App shell — same chrome as the Psychological Safety console.

The markup mirrors that project's sidebar and top header, so
assets/dashboard.css styles it unmodified; assets/me.css adds only what is
specific to this dashboard. No Bootstrap CDN: jsdelivr is blocked on the
corporate network, so the handful of utility classes used are defined
locally.
"""
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

import data as D
import refresh as refresher

NAV = [
    ('/', 'Pulse', 'The story this cycle', '◉'),
    ('/themes', 'Themes', 'Six themes, every statement', '▦'),
    ('/cuts', 'Cuts', 'Every breakdown and rollup', '▤'),
    ('/queue', 'Action Queue', 'Managers needing support', '⚑'),
]

# No use_pages. Its internal _pages_content callback did not dispatch on the
# first paint here, which left every page blank until something was clicked.
# An explicit router is four lines and its behaviour is inspectable.
app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title='EX — Managerial Excellence',
    update_title=None,
    meta_tags=[{'name': 'viewport',
                'content': 'width=device-width, initial-scale=1'}],
)
server = app.server


def _nav_link(href, label, sublabel, glyph):
    return html.Li(
        html.A([
            html.Span(glyph, className='sidebar-icon'),
            html.Span([
                html.Span(label, className='sidebar-label'),
                html.Span(sublabel, className='sidebar-sublabel'),
            ], className='sidebar-text'),
        ], href=href, className='sidebar-link',
            id={'type': 'nav', 'href': href}, title=label),
    )


@callback(
    Output({'type': 'nav', 'href': dash.ALL}, 'className'),
    Input('_url', 'pathname'),
)
def _highlight_nav(pathname):
    return ['sidebar-link active' if href == (pathname or '/')
            else 'sidebar-link' for href, _l, _s, _g in NAV]


# ── refresh ───────────────────────────────────────────────────────────────

@callback(
    Output('refresh-poll', 'disabled', allow_duplicate=True),
    Output('refresh-status', 'children', allow_duplicate=True),
    Input('refresh-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def _start_refresh(n_clicks):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    refresher.start()
    return False, 'Building…'


@callback(
    Output('refresh-status', 'children'),
    Output('refresh-poll', 'disabled'),
    Output('refresh-btn', 'disabled'),
    Output('_reload', 'href'),
    Input('refresh-poll', 'n_intervals'),
    State('_url', 'pathname'),
    State('_url', 'search'),
    prevent_initial_call=True,
)
def _poll_refresh(_n, pathname, search):
    state = refresher.status()
    if state['state'] == 'running':
        elapsed = int(time.time() - (state['started'] or time.time()))
        return f"{state['message']} {elapsed}s", False, True, no_update
    if state['state'] == 'done':
        return (state['message'], True, False,
                _reload_href(pathname, search, state['finished']))
    if state['state'] == 'error':
        return state['message'], True, False, no_update
    return '', True, False, no_update


def _reload_href(pathname, search, stamp):
    from urllib.parse import parse_qsl, urlencode
    params = [(k, v) for k, v in parse_qsl((search or '').lstrip('?'))
              if k != '_r']
    params.append(('_r', str(int(stamp or 0))))
    return (pathname or '/') + '?' + urlencode(params)


app.layout = html.Div([
    dcc.Location(id='_url', refresh=False),
    dcc.Location(id='_reload', refresh=True),
    dcc.Interval(id='refresh-poll', interval=2000, disabled=True),
    # No selection stores: every page reads its state from the query string
    # and renders server-side, so a view is shareable by URL and there is no
    # callback graph to deadlock on first paint.


    html.Nav([
        html.Div([
            html.Img(src=dash.get_asset_url('swiggy-logo.webp'),
                     className='sidebar-logo', alt='Swiggy'),
            html.Button('❮', id='sidebarCollapseBtn',
                        className='sidebar-collapse-btn', title='Collapse'),
        ], className='sidebar-header'),
        html.Div(['Employee Experience', html.Br(), 'Reports'],
                 className='sidebar-app-name'),
        html.Div('Dashboards', className='sidebar-section-label'),
        html.Ul([_nav_link(*item) for item in NAV], className='sidebar-nav'),
    ], id='sidebar', className='sidebar'),

    html.Div([
        html.Header([
            html.Div([
                html.Button('☰', id='topHamburger', className='top-hamburger',
                            title='Toggle sidebar'),
                html.Div(className='top-divider'),
                html.H1('EX — MANAGERIAL EXCELLENCE', className='top-title mb-0'),
            ], className='d-flex align-items-center gap-3'),
            html.Div([
                # The cycle picker lives in the chrome, not in a page.
                # Inside a page it would sit inside the very container the
                # cycle callback rewrites, making the dependency graph
                # circular — Dash then registers every callback and
                # dispatches none, which reads as a blank dashboard.
                html.Span(id='refresh-status', className='refresh-status'),
                html.Button('⟳ Refresh data', id='refresh-btn',
                            className='refresh-btn', n_clicks=0,
                            title='Rebuild the dbt models and reload'),
                html.Button('☾', id='themeToggle', className='top-theme-btn',
                            title='Toggle dark mode'),
            ], className='d-flex align-items-center gap-3'),
        ], className='top-header d-flex align-items-center '
                     'justify-content-between px-3'),

        html.Main(id='page-body', className='page-content'),
    ], id='mainWrapper', className='main-wrapper'),
], className='app-shell')



# ── router ────────────────────────────────────────────────────────────────

import pages.cuts as page_cuts
import pages.pulse as page_pulse
import pages.queue as page_queue
import pages.themes as page_themes

ROUTES = {
    '/': page_pulse.layout,
    '/themes': page_themes.layout,
    '/cuts': page_cuts.layout,
    '/queue': page_queue.layout,
}


@callback(Output('page-body', 'children'),
          Input('_url', 'pathname'),
          Input('_url', 'search'))
def _route(pathname, search):
    """Render the page for the URL, server-side, in one pass.

    Query-string params become keyword arguments, so every selector on every
    page is a link and the whole view is shareable by URL.
    """
    from urllib.parse import parse_qsl
    fn = ROUTES.get(pathname or '/')
    if fn is None:
        return html.Div('Not found', className='me-root',
                        style={'padding': '40px'})
    params = dict(parse_qsl((search or '').lstrip('?')))
    params.pop('_r', None)
    try:
        return fn(**params)
    except Exception as exc:            # a bad URL must not blank the app
        logging.exception('Page render failed for %s', pathname)
        return html.Div([
            html.H2('This view could not be rendered'),
            html.P(str(exc)),
            dcc.Link('Back to Pulse', href='/'),
        ], className='me-root', style={'padding': '40px'})



# ── filter bar -> URL ─────────────────────────────────────────────────────

@callback(Output('_url', 'search'),
          Input('f-cycle', 'value'),
          Input({'type': 'f', 'field': ALL}, 'value'),
          Input('f-clear', 'n_clicks'),
          State('_url', 'search'),
          prevent_initial_call=True)
def _apply_filters(cycle, values, _clear, current):
    """Merge the bar's state into the URL, leaving everything else alone.

    An earlier version REBUILT the query string from the bar plus a
    hard-coded list of extras. Anything it did not know about was silently
    dropped — and because the bar is re-created on every page render, that
    happened on load: opening a drill panel rewrote the URL back to
    ?cycle=..., so the panel's own close link pointed at the address the
    browser was already on, Dash saw no change, and the × did nothing.

    Merging fixes the whole class: drill, mgr, tag, cmp_from and the rest
    survive a filter change without this callback having to know they exist.
    """
    from urllib.parse import parse_qsl, urlencode

    params = dict(parse_qsl((current or '').lstrip('?')))
    # Clear all must also drop cross-filters clicked from a table, not just
    # the ones the bar itself owns — otherwise a click-filter is unclearable
    # from the bar and the chip row is the only way out.
    filter_cols = {col for col, _label in D.ALL_FILTER_FIELDS}

    if ctx.triggered_id == 'f-clear':
        for col in filter_cols:
            params.pop(col, None)
    else:
        for spec, vals in zip(ctx.args_grouping[1], values):
            col = spec['id']['field']
            if vals:
                params[col] = '~'.join(vals)
            else:
                params.pop(col, None)

    params['cycle'] = cycle
    params.pop('_r', None)
    new = '?' + urlencode(params)
    # A no-op write still counts as a change to dcc.Location and would send
    # the page through a pointless re-render on every load.
    return no_update if new == (current or '') else new


if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5016)))
