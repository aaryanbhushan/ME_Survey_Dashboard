{{ config(materialized='table') }}

/*
  One row per (manager, cycle) — the grain every manager-level visual in the
  report needs, and the replacement for four DAX SUMMARIZE tables at once:
  ManagerNPS, SummaryThemeScore, Theme Driver and Percentile25_*.

  Measures reproduced here, with their DAX originals:

    Total Responses Recieved = DISTINCTCOUNTNOBLANK(Email_Address)
    Theme Score              = AVERAGE(Rating)
    Promoters / Passive /
      Detractor              = DISTINCTCOUNTNOBLANK(Email_Address) filtered to
                               Promoter_Detractor = X on the NPS question
    ME NPS                   = DIVIDE(Promoters - Detractor,
                                      Promoters + Passive + Detractor)
    Positive / Negative      = DISTINCTCOUNTNOBLANK(Email_Address) filtered to
                               Positive_Negative = X
    % positive response      = DIVIDE(Positive, Positive + Negative)
    ME%                      = DIVIDE(Theme Score, 4)
    ME_Bucket                = SWITCH(TRUE(), ME% >= 0.9, "90% & Above",
                                              ME% >= 0.7, "70%-90%",
                                              "Below 70%")
*/

with responses as (

    select * from {{ ref('int_me_responses_scored') }}

),

/*
  The NPS question. The PBIP's Promoters/Passive/Detractor measures filter on
  the literal question text; the mapping table carries the same thing as
  Category = 'NPS', which survives a re-wording of the question. Both select
  the same rows today — tests/assert_me_single_nps_question.sql fails the
  build if that stops being true.
*/
nps_rows as (

    select
        manager_email,
        cycle,
        email_address,
        promoter_detractor
    from responses
    where category = 'NPS'

),

nps as (

    select
        manager_email,
        cycle,
        count(distinct email_address)
            filter (where promoter_detractor = 'Promoter')  as promoters,
        count(distinct email_address)
            filter (where promoter_detractor = 'Passive')   as passives,
        count(distinct email_address)
            filter (where promoter_detractor = 'Detractor') as detractors
    from nps_rows
    group by 1, 2

),

scores as (

    select
        manager_email,
        cycle,
        max(manager_bu)     as manager_bu,
        max(manager_grade)  as manager_grade,
        max(manager_gender) as manager_gender,

        count(distinct email_address)              as total_responses,
        avg(rating)                                as theme_score,

        count(distinct email_address)
            filter (where positive_negative = 'Positive') as positive_responses,
        count(distinct email_address)
            filter (where positive_negative = 'Negative') as negative_responses,

        max(distinct_emp_count)                    as distinct_emp_count,
        max(cycle_visibility)                      as cycle_visibility

    from responses
    group by 1, 2

),

combined as (

    select
        s.manager_email,
        s.cycle,
        s.manager_bu,
        s.manager_grade,
        s.manager_gender,
        s.total_responses,
        round(s.theme_score::numeric, 4) as theme_score,
        s.positive_responses,
        s.negative_responses,
        s.distinct_emp_count,
        s.cycle_visibility,

        coalesce(n.promoters, 0)  as promoters,
        coalesce(n.passives, 0)   as passives,
        coalesce(n.detractors, 0) as detractors,

        -- ME NPS, as a percentage. DIVIDE() returns BLANK on a zero
        -- denominator, which is NULL here — not 0. The report's ME_NPS
        -- measure wraps that in IF(ISBLANK(...),0,...) for display only; the
        -- distinction matters because "no NPS responses" and "NPS of zero"
        -- are different things when you average managers.
        case
            when coalesce(n.promoters, 0) + coalesce(n.passives, 0)
               + coalesce(n.detractors, 0) > 0
            then round(
                (coalesce(n.promoters, 0) - coalesce(n.detractors, 0))::numeric
                / (coalesce(n.promoters, 0) + coalesce(n.passives, 0)
                   + coalesce(n.detractors, 0)) * 100, 2)
        end as me_nps,

        -- % positive response
        case
            when s.positive_responses + s.negative_responses > 0
            then round(s.positive_responses::numeric
                       / (s.positive_responses + s.negative_responses) * 100, 2)
        end as pct_positive

    from scores s
    left join nps n
        on n.manager_email = s.manager_email
       and n.cycle         = s.cycle

),

banded as (

    select
        c.*,

        -- ME%  =  DIVIDE(Theme Score, 4)
        round(c.theme_score / 4, 4) as me_pct,

        case
            when c.theme_score / 4 >= 0.9 then '90% & Above'
            when c.theme_score / 4 >= 0.7 then '70%-90%'
            when c.theme_score is not null then 'Below 70%'
        end as me_bucket,

        case
            when c.theme_score / 4 >= 0.9 then 1
            when c.theme_score / 4 >= 0.7 then 2
            when c.theme_score is not null then 3
        end as me_bucket_sort

    from combined c

),

/*
  Grade-relative 25th percentile — the report's own "needs support" rule.

  DAX equivalent: SummaryThemeScore[Percentile25_<cycle>_Grade], compared in
  IsBottomPercentile / Bottom25PercentileSep24Check.

  Two things the DAX does that are easy to lose:
    - the percentile is taken over MANAGERS, not over responses, so it is
      computed on this grain and not on the fact;
    - only visible managers (3+ responses) enter the population, otherwise a
      one-response manager drags the bar down for their whole grade.
*/
percentiles as (

    select
        cycle,
        manager_grade,
        percentile_cont(0.25) within group (order by theme_score)
            as p25_theme_score,
        count(*) as managers_in_grade
    from banded
    where cycle_visibility = 'Yes'
      and manager_grade is not null
      and theme_score is not null
    group by 1, 2

)

select
    b.manager_email,
    b.cycle,
    b.manager_bu,
    b.manager_grade,
    b.manager_gender,
    b.total_responses,
    b.theme_score,
    b.me_pct,
    b.me_bucket,
    b.me_bucket_sort,
    b.promoters,
    b.passives,
    b.detractors,
    b.me_nps,
    b.positive_responses,
    b.negative_responses,
    b.pct_positive,
    b.distinct_emp_count,
    b.cycle_visibility,

    round(p.p25_theme_score::numeric, 4) as grade_p25_theme_score,
    p.managers_in_grade,

    -- Below their own grade's bar this cycle.
    case
        when b.cycle_visibility = 'Yes'
         and b.theme_score is not null
         and p.p25_theme_score is not null
         and b.theme_score < p.p25_theme_score
        then true else false
    end as is_below_grade_p25,

    -- Negative NPS. DAX: [Negative NPS] counts managers whose NPS < 0.
    case when b.me_nps < 0 then true else false end as has_negative_nps

from banded b
left join percentiles p
    on p.cycle         = b.cycle
   and p.manager_grade = b.manager_grade
