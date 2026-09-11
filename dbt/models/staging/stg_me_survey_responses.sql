{{ config(materialized='view') }}

/*
  The ME survey fact, one row per (respondent, question, cycle).

  CONTRACT — columns downstream models rely on:
      respondent_id  email_address  manager_email  question  answer
      target_grade   cycle          refreshed_date

  ── Two things verified against the source, both of which change the numbers
     if got wrong ───────────────────────────────────────────────────────────

  1. THE MANAGER IS `manager_email_id`, NOT `custom_data_2`.
     The PBIP read Custom_Data_2. In this merged table that column is NULL on
     all 998,496 rows — the merge resolved it into manager_email_id. Confirmed
     by distinct counts, which match the retired report exactly:

         cycle    managers   respondents
         Sep_24        970         3,290
         Mar_25      1,001         3,214
         Sep_25        953         3,671
         Mar_26      1,241         4,257

     custom_data_4 is populated for some cycles but has only 46 distinct
     values in Mar_26 — it is not the manager.

  2. THE SOURCE IS DUPLICATED, EXACTLY.
     Every response appears 2x (Aug_23, Mar_24, Mar_26), 3x (Mar_25, Sep_24)
     or 1.18x (Sep_25); Sep_26 is clean. For Mar_25 and Sep_24 the `source`
     column explains it — the same response is present once with source NULL
     and once tagged with a grade band.

     The PBIP handled this with `SELECT DISTINCT` at the top of its source
     query. Same fix, same place. Without it every count in the dashboard
     roughly doubles.

  ── Cycle scope ────────────────────────────────────────────────────────────
  Aug_23 and Mar_24 are excluded, as the PBIP's query did
  (`where a.[Cycle] not in ('Aug_23','Mar_24')`). Their grade bands are
  labelled differently ("Grade 4-7", "Grade 10-11", "Grade 4-9") and do not
  join to the theme mapping at all — 0% coverage.

  Sep_26 IS included. It is a live cycle the retired report never saw
  (1,692 respondents, 874 managers so far, and the only cycle with no
  duplication). It is partial by definition until fieldwork closes.
*/

with source as (

    select * from {{ source('swiggydbo', 'me_survey_response_merged') }}

),

deduped as (

    -- The PBIP's `SELECT DISTINCT`. Projecting first, then DISTINCT, means
    -- the merge-artifact columns (source, manager_name, emp_grade) cannot
    -- keep a duplicate alive.
    select distinct
        nullif(btrim(respondent_id), '')            as respondent_id,
        lower(nullif(btrim(email_address), ''))     as email_address,
        lower(nullif(btrim(manager_email_id), ''))  as manager_email,
        nullif(btrim(question), '')                 as question,
        nullif(btrim(answer), '')                   as answer,
        nullif(btrim(target_grade), '')             as target_grade,
        nullif(btrim(cycle), '')                    as cycle,
        refreshed_date
    from source

)

select
    respondent_id,
    email_address,
    manager_email,
    question,
    answer,
    target_grade,
    cycle,
    refreshed_date
from deduped
where manager_email is not null
  and cycle is not null
  and question is not null
  and cycle not in ('Aug_23', 'Mar_24')
