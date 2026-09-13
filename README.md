# ME Survey Dashboard

The Managerial Excellence survey scorecard. Replaces the retired Power BI
report *EX - Managerial Excellence Survey Dashboard*, whose figures this
reproduces exactly — see [Verification](#verification).

Dash + psycopg2 over an SSH tunnel, with dbt marts in Postgres. Four pages,
all rendered server-side in one pass from the URL.

---

## Quick start — the only thing you need to do is fill in `.env`

```bash
pip install -r requirements.txt
copy .env.example .env      # cp on macOS/Linux — then fill in the blanks
python run.py               # serves on http://127.0.0.1:5016
```

On Windows you can double-click **`run_app.bat`** instead of the last line; it
checks `.env` exists, tells you what to do if not, and keeps the console open
so you can read any error.

Nothing else in the project is environment-specific. There are no absolute
paths anywhere in the code — every path is resolved relative to the file
asking for it, so the folder works wherever you clone it.

**First run takes ~4 minutes.** It opens the tunnel, checks the two marts
exist (building them with `dbt build` if they do not), then pulls ~644k rows
once into memory. Every page after that is served from those frames and is
effectively instant.

### Requirements

- **Python 3.11+** (developed and run on 3.14)
- Network access to the SSH bastion named in your `.env`
- Postgres credentials with **read** access to `swiggydbo`, and **create**
  access on the `staging` / `intermediate` / `marts` schemas if you intend to
  run dbt

`pip install -r requirements.txt` brings in Dash, pandas, psycopg2-binary,
paramiko, sshtunnel, waitress, python-dotenv and dbt-postgres.

### If it will not start

| Symptom | Cause |
| --- | --- |
| `Authentication failed` | **The SSH password rotates often.** A rotation and a lockout look identical. Re-enter `PG_SSH_PASSWORD` in `.env` before investigating anything else. |
| `.env is missing values for:` | `run.py` lists exactly which keys are blank. |
| Page loads but errors on a number | The marts are missing or stale. Run `python run_dbt.py`. |
| Refresh button says `dbt not found` | Set `DBT_EXE` in `.env` to the output of `where dbt`. |

### Manual dbt runs (optional)

```bash
python run_dbt.py                              # build + test  (9 models, 18 tests)
python run_dbt.py run  --select mart_me_responses
python run_dbt.py test
```

`run_dbt.py` opens its own dedicated tunnel and exports `PG_TUNNEL_PORT` for
`dbt/profiles.yml` to read, so dbt never shares the app's tunnel — the app
self-heals its forwarder by restarting it, which would otherwise yank the port
out from under a multi-minute dbt run.

Two optional developer tools:

```bash
python introspect.py    # dumps the source tables to introspect_output.txt
python validate.py      # re-runs the reconciliation below against the marts
```

`introspect_output.txt` is **gitignored** — it contains sample rows including
real employee email addresses.

---

## File structure

```
app.py                  chrome, the explicit router, filter-bar → URL merge
data.py                 mart reads, every aggregation, memoised
components.py           chips, deltas, bars, tables, side panels
page_common.py          filter bar, chips, cross-filter + drill links
pages/pulse.py          Pulse — hero, insight cards, trends, bands, BU table
pages/themes.py         Themes — theme cards, statements, heat map
pages/cuts.py           Cuts — dimension table, hierarchy rollups, matrix
pages/queue.py          Action Queue — grade-relative bottom quartile
assets/me.css           house styling
assets/dashboard.css    shared chrome (copied from the sibling dashboards)
assets/chrome.js        header behaviour
assets/scroll.js        scroll-position restore across selector changes
db.py                   connection handle + cache flush
pg_connection.py        SSH tunnel management
run.py                  production entry point (waitress)
run_dbt.py              dbt runner with its own tunnel
refresh.py              the header Refresh button's worker
introspect.py           one-off source inspector
validate.py             reconciliation against the retired report
dbt/                    9 models, 18 tests
```

---

## Architecture — five rules worth keeping

These were each arrived at by hitting the failure first.

**1. No `use_pages`.** Its internal `_pages_content` callback did not dispatch
on first paint, so the app rendered blank chrome with no error anywhere.
Replaced with an explicit router on `_url.pathname` + `_url.search`.

**2. State lives in the query string, never in `dcc.Store`.** A store that is
the *output* of a callback leaves every reader blocked until that callback
fires, which deadlocked the first build. Pages render server-side in one pass
from `layout(**query_params)`, and any view is therefore shareable as a URL
and reachable with the back button.

**3. Never make a control both input and output of the same loop.** A row of
buttons writing to a store, with the store driving the buttons' `className`,
is circular — Dash registers every callback and dispatches **none**, silently.
Every selector here is a `dcc.Link`.

**4. The filter bar MERGES into the URL, it never rebuilds it.** An earlier
version rebuilt the query string from the bar plus a hard-coded extras list,
so anything it did not know about was dropped — and because the bar is
re-created on every render, that happened on load. `_apply_filters` merges and
returns `no_update` when nothing changed. This is what makes `drill`, `mgr`,
`cmp_from` and the cross-filters survive a filter change.

**5. Memoise everything.** One render asked for `themes()` three times.
Uncached, a Pulse render took **36 seconds**; `functools.lru_cache` via the
`_cached` decorator brings it to ~6s cold and ~15ms warm. `flush()` clears
frames *and* caches. Picklists are warmed in `preload()` — built lazily they
landed on the first render and put it at 28s.

Every aggregation takes `fkey`, a hashable order-stable filter signature from
`D.filter_key()`, and routes through `D.subset(cycle, fkey)`.

---

## Source tables (`swiggydbo`)

| Table | Notes |
| --- | --- |
| `me_survey_response_merged` | The fact, one row per (respondent, question). 23 columns. |
| `me_question_theme_mapping` | **Wide** — one row per concept, one column per grade band. |
| `pg_dim_employee` | Employee master. Current state only, no history. |
| `pg_manager_hierarchy` | Reporting line, **top-down** (l1 = CEO). Employee IDs. |
| `pg_hrbp_hierarchy` | HRBP line, **bottom-up**. Emails. Opposite orientation. |
| `pms_rating` | Performance ratings. `dim_employee.latest_rating` is NULL for every row, so this is the only usable source. |
| `me_survey_recipient_merged` | Declared but unused — would enable a response-rate measure. |

### Four things about the source that each change the numbers

1. **The manager is `manager_email_id`, not `custom_data_2`.** The report read
   `Custom_Data_2`; in the merged table that column is NULL on all 998,496
   rows. Confirmed by distinct counts matching the report exactly.
2. **The source is duplicated, exactly** — 2× (Mar_26), 3× (Mar_25, Sep_24),
   1.18× (Sep_25), 1× (Sep_26). The report's `SELECT DISTINCT` was
   load-bearing; `stg_me_survey_responses` reproduces it. Without it every
   count roughly doubles.
3. **The theme mapping is wide and has no cycle column.** Unpivoted in
   staging, keyed on (question, target_grade).
4. **The mapping fans out** on the open-ended prompts. Joined raw it inflated
   Mar_25 and Sep_24 by 13%. `DISTINCT ON` fixes it;
   `assert_me_theme_map_grain` guards it.

Theme text needs more cleaning than the report's M query did: the merged table
carries both `Cross the Finish Line` and `Cross the Finish line`, plus
`Fairiness and Inclusion` (sic), which reads as 11 themes instead of 6. The
cleanup order matters — the colon strip must precede the trim, or
`Drive Alignment:` keeps a trailing space and splits into a second theme.

---

## The two scales — do not conflate them

The survey asks two different kinds of question, scored differently. Getting
this wrong is the single easiest way to produce a confidently wrong number.

| Category | Questions | Answers | `rating` |
| --- | --- | --- | --- |
| *(blank)* + `DEI` | 23 + 12 | Agree / Disagree / Strongly agree / Strongly disagree | **1–4** |
| `NPS` | 1 | `0`–`10` | NULL |
| `Open Ended` | 3 | free text | NULL |

- **`Rating` is out of 4.** `Theme Score` = `AVERAGE(Rating)`; `ME%` =
  `Theme Score / 4`; `ME_Bucket` cuts at 0.9 and 0.7 of that, i.e. **3.60** and
  **2.80**. The report's own `ScoreCategoryME` writes those as `4 * 0.9` and
  `4 * 0.7`, which is the clearest statement in the model that 4 is the max.
- **Promoter / Passive / Detractor is out of 10** — a *different* question,
  and `rating` is deliberately NULL on those rows so they drop out of every
  `AVERAGE(Rating)` without a filter at the call site.

---

## DAX translated

Every measure the report's 63 visuals bind to, reproduced in
`int_me_responses_scored` and `mart_me_manager_cycle`:

| Report | Here |
| --- | --- |
| `Rating` SWITCH | `rating`, 1–4 |
| `Promoter_Detractor` | same name — note a **blank** answer counts as Passive |
| `Positive_Negative` | `rating >= 3` / `>= 1` |
| `Theme Score` = `AVERAGE(Rating)` | `avg(rating)` |
| `ME%` = `Theme Score / 4` | `me_pct` |
| `ME_Bucket` 0.9 / 0.7 | `me_bucket` |
| `Total Responses Recieved` | `DISTINCTCOUNTNOBLANK(email_address)` |
| `Unique Managers` | distinct `manager_email` |
| `ME NPS` = `DIVIDE(P−D, P+A+D)` | `me_nps`, ×100 here |
| `DistinctEmpCount` → `CycleVisibility` ≥3 | `cycle_visibility` |
| `Include` (`Sub Theme`=DE ∧ `Category`=DEI) | `include_flag` |
| `Negative NPS` | `has_negative_nps` |
| `Theme Score Org1`, `Avg_Score_BU` | the org / BU benchmark ticks |

`mart_me_manager_cycle` replaces four DAX `SUMMARIZE` tables at once —
`ManagerNPS`, `SummaryThemeScore`, `Theme Driver` and `Percentile25_*`.

**Postgres has no DISTINCT window aggregate**, so `DistinctEmpCount`'s
`ALLEXCEPT` is a pre-aggregate joined back on, not an `OVER (PARTITION BY)`.

---

## Pages

**Pulse** `/` — hero ME score with a five-cycle sparkline, six mini-KPIs, four
written insight cards each clicking through to the evidence, ME/NPS trends,
promoter mix, ME bands, BU table.

**Themes** `/themes` — theme cards with tenet numbers and org-average ticks,
theme scores across every cycle, weakest/strongest five, every statement with
its movement, and the statement × dimension heat map.

**Cuts** `/cuts` — eleven-dimension table with BU → Department → Team
drill-down, manager (L8→L5) and HRBP (L6→L4) hierarchy rollups, gender ×
gender matrix, coverage by cycle.

**Queue** `/queue` — managers below their **own grade's** 25th percentile,
ranked by gap × headcount, tagged PERSISTENT / NEW / FIRST CYCLE, with a
right-side drawer per manager.

### Cross-filtering

Click a value and the whole page narrows to it. It is a link that adds one
query parameter — no callback, no chart event — so the filtered view stays
shareable and back-button-able. Clicking an already-selected value clears it,
so a click is its own undo. Active filters appear as chips, each with its own
`×`.

Wired on: the Pulse BU table, the Cuts dimension table (all 11), the hierarchy
rollups, the gender matrix (which sets both genders at once), and the Themes
theme cards. The `+` beside a business unit or department opens the level
inside it.

### Rated vs scored

**Rated** = at least one response. **Scored** = at least three, so the number
can be shown. Below three the manager is suppressed everywhere, which is the
report's own `CycleVisibility` rule. Response counts and the org ME score use
everyone; anything per-manager can only use the scored half.

### Default cycle

`D.default_cycle()` opens on the most recent cycle whose response base is
**≥60%** of the one before it, so a half-collected cycle never becomes the
default view. `D.is_in_flight()` flags the latest cycle when it is excluded;
the picker still exposes it.

---

## Deliberate deviations from the report

Each of these is a considered departure, not an accident.

1. **The manager is `manager_email_id`** (see above). Affects every measure
   the report keyed on `Custom_Data_2`.
2. **NPS is found by `category = 'NPS'`, not the literal question text**, so a
   re-wording cannot silently zero it. `assert_me_single_nps_question` fails
   the build if more than one NPS question ever appears.
3. **`me_nps` is NULL on a zero denominator, not 0.** The report has *both*
   variants and uses both — `ME NPS` returns BLANK, `ME_NPS` returns 0. This
   follows `ME NPS`, because "no NPS responses" and "an NPS of zero" must not
   average together.
4. **Three statements are reverse-scored.** Sep_26 added the seven-item
   psychological-safety scale; three of its items are worded negatively, so
   agreement is bad news. Four in five people *disagree* that it is difficult
   to ask their team for help — the healthy answer, which on the ordinary
   scale scored 1–2 and pulled the cycle's ME down 0.108. Scored on the
   flipped scale, with `is_reverse_coded` carried through so a reader can see
   why. These three appear in Sep_26 only, so the reconciled cycles cannot
   move. `assert_me_reverse_coded_matched` fails the build if any of them
   stops matching, because the match is on question text and a reword would
   silently revert the item.
5. **`stg_me_email_resolution` resolves stale email domains.** Two domains
   appear for the first time in Sep_26. The fact keeps the address a person
   held when they answered; `pg_dim_employee` keeps only their current one, so
   a direct join lost the BU, grade and hierarchy of anyone who moved — 357 of
   1,241 managers in Mar_26. Resolution is exact-match first, then the local
   part where it identifies exactly one named person. It resolves **attributes
   only, never identity**, so no count moves.
6. **Hierarchy rows are tagged NEW IN SEAT.** Both hierarchy tables are a
   *current* snapshot, so rolling a historical cycle through today's reporting
   line credits it to whoever holds the seat now. Where the leader was not
   employed for the comparison cycle, the delta is withheld. 187 node-cycle
   rows are affected.
7. **The Queue is not the report's percentile.** The report's only live
   percentile is org-wide over all managers. This one is **per grade**, over
   **scored managers only** — a 3.30 means something different at G4 than at
   G11, and one-response managers drag a grade's bar down. Better, but ours:
   do not describe the Queue as reproducing the report.
8. **Substitutions:** 3 gauges → NPS bars (same numbers, readable scale), 2
   radar charts → theme cards, `aiNarratives` → the written insight cards.

### Not carried over

- Aug_23 and Mar_24 — excluded by the report's own source query; their grade
  bands do not join to the mapping at all (0% coverage).
- SwiggyVibes / Leena cross-survey tables — they belong in that dashboard.
- The DAX helper tables — `mart_me_manager_cycle` replaces them.
- The report's hand-maintained `template (1)` old→new email remap. See
  [Known gaps](#known-gaps) — it turns out to still be needed.
- `Theme_Check` / `Theme Final` — dead in the report. `Theme_Check` is a
  `LOOKUPVALUE` against a `Tenet Mapping` table that **does not exist in the
  model**, so `Theme Final` always falls through to `Theme`, and it is bound
  to 0 visuals against 22 for `[Theme]`.
- `Percentile25_Aug23_Per_Manager` uses **0.90** despite its name,
  `SuccessiveBottom25Percentile` uses **0.85**, and the `Percentile25_Sep_24`
  calculated table's expression is malformed. None is bound to any visual.
  Do not copy them.

---

## Verification

`python validate.py` re-runs this against the live marts. The reference
figures were read out of the retired report's own `cache.abf`, so this is a
like-for-like check.

| Cycle | Respondents | Managers | ME | NPS |
| --- | --- | --- | --- | --- |
| Sep_24 | 3,290 ✓ | 970 ✓ | 3.47 ✓ | 56.9 ✓ |
| Mar_25 | 3,214 ✓ | 1,001 ✓ | 3.48 ✓ | 57.8 ✓ |
| Sep_25 | 3,671 ✓ | 953 ✓ | 3.53 ✓ | 59.3 ✓ |
| Mar_26 | 4,257 ✓ | 1,241 ✓ | 3.46 ✓ | 52.9 ✓ |

All six Mar_26 theme scores match to 2dp with the same question counts
(10/4/6/4/4/7). Visible managers Mar_26 = 608, exact. ME bands land
30 / 332 / 246 against the report's 30 / 333 / 245 — one manager either side
of a band edge, from `numeric` rounding versus the report's float.

**Sep_26 is a live cycle the report never saw.** 4,398 respondents, 1,303
managers, 678 scored (52%), ME 3.43, NPS 60.2. Note that its headline ME
blends two instruments — the 35 ME statements at 3.53 and the psychological
safety block at 3.14. So Sep_26 vs Mar_26 is −0.04 on the headline but
**+0.06 on the ME statements alone**. Quote the like-for-like number when
comparing cycles.

---

## Known gaps

**1. Row-level security is NOT enforced. This is the blocker before anyone
outside the team gets a link.** The app reads the whole org: a manager can see
their own scorecard and everyone else's, and every manager's verbatims are
visible to any viewer. The report had 18 RLS roles — managers scoped to their
own reporting line *excluding themselves*, HRBPs to their span, six BU roles,
L&D g6-9, Overall-less-HR, and D&I. None of that is implemented here.

**2. Cross-cycle identity breaks on an email-domain change.** The Queue's
PERSISTENT / NEW tags and any manager-level trend match on the full email, so
anyone who changed domain counts as two different people. Measured Mar_26 →
Sep_26: 2,035 matched on full email against 2,686 matched on local part, so
**651 people (~24%)** are lost. Fixing it means collapsing addresses, which
*would* move the reconciled counts (Mar_26 respondents 4,257 → 4,256, Sep_24
managers 970 → 969). That trade-off has not been taken. This is what the
report's `template (1)` remap existed for. A name-verified seed is the right
shape — note that of 59,044 distinct local parts, 1,223 sit on more than one
address and **111 of those are genuinely different people**, so a blind
local-part join would merge colleagues.

**3. No point-in-time employee dimension.** Every manager attribute (BU,
department, grade, tenure, PMS rating) comes from today's `pg_dim_employee`,
so a manager who changed BU has their historical responses counted under their
current one. The report did the same, so the numbers still reconcile, but say
so if a BU trend is questioned. `EMPLOYEE_TIME_SERIES` may be a route.

**4. Startup reads ~644k rows every time**, which is still a ~3 minute cold
start over the tunnel. The *memory* half of this is fixed — see
`data.responses()` — but the read itself is unchanged, so an incremental mart
read is still the outstanding piece.

On memory, for anyone tempted to re-tune it: the frame is read **in chunks**,
each converted to categoricals against a shared category set, and only the 33
columns the pages actually use. That takes resident memory from **2.0 GB to
~200 MB**. Three things there are load-bearing and look optional:

- Converting *after* a plain `select *` read instead only saves ~10%, because
  RSS is set by the read's peak and Python never returns that to the OS.
- The category sets must be **sorted**. `groupby` on a categorical iterates in
  category order, so an unsorted set silently re-breaks ties in every
  `sorted(...)` in `data.py`.
- The text columns are read from `information_schema`, not listed by hand.
  `manager_latest_rating` is an `integer` despite its name, and building a
  categorical over it with string categories turns every value into NaN
  without raising — which empties the PMS rating picker on every page.

**5. The Manager dropdown carries ~1,700 options**, pushing each page payload
to ~250KB.

**6. `refresh.py` is wired to the header button** but a full
rebuild-and-reload has not been exercised end to end.

**7. `me_survey_recipient_merged` is unused.** It would enable a response-rate
measure the report never had — against 6,581 invitations, Sep_26's 4,398
responses are ~67%.

---

## Refresh

The header **Refresh** button runs `refresh.py`, which rebuilds the marts with
dbt and then calls `flush()` to drop the in-memory frames and every cache so
the next request re-reads. The dbt run uses its own tunnel (see above).

After a refresh the app does **not** restart — it re-reads on the next
request, which takes the ~2 minute mart read again on that one request.
