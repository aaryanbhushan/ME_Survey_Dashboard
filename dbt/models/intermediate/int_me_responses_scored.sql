{{ config(materialized='view') }}

/*
  Every DAX calculated column from ME_Survey_Response, in one place.

  The PBIP computed these in the model rather than in SQL, so this is the
  only file where the translation happens. Each block below names the DAX it
  replaces so the two can be diffed.

  Grain: one row per (respondent, question, cycle) — unchanged from staging.
*/

with responses as (

    select * from {{ ref('stg_me_survey_responses') }}

),

theme_map as (

    select * from {{ ref('stg_me_question_theme') }}

),

/*
  A question whose wording is used by only ONE grade band still identifies its
  theme unambiguously. That fallback matters: Mar_25 and Sep_24 carry a NULL
  target_grade on roughly a third of their rows, and without it those rows
  lose their theme and drop out of every theme score while still counting in
  the response totals — which reads as a coverage gap that is not real.

  Restricted to questions that map to exactly one theme; five questions map to
  two themes across bands and are deliberately left to the exact join.
*/
theme_by_question as (

    select
        question,
        min(theme)     as theme,
        min(sub_theme) as sub_theme,
        min(category)  as category,
        min(tenet)     as tenet
    from theme_map
    where theme is not null
    group by question
    having count(distinct theme) = 1

),

employee as (

    select employee_email, bu, gender, grade
    from {{ ref('stg_me_dim_employee') }}

),

/*
  Survey email -> master email. Needed because two domains appear for the
  first time in Sep_26, so a direct join loses the attributes of anyone who
  moved. See stg_me_email_resolution for the rule and why it resolves
  attributes only, never identity.
*/
resolution as (

    select survey_email, employee_email
    from {{ ref('stg_me_email_resolution') }}
    where employee_email is not null

),

/*
  REVERSE-CODED STATEMENTS.

  Sep_26 added the seven-item psychological-safety scale to the ME
  questionnaire. Three of its items are worded negatively, so agreement is bad
  news and disagreement is good news — the opposite of every other statement
  in this survey. Scored on the ordinary scale they invert: ~80% of people
  DISAGREE that it is difficult to ask their team for help, which is the
  healthy answer, and it was landing as a rating of 1-2 and dragging Sep_26's
  ME score from 3.55 down to 3.34.

  These three appear in Sep_26 only; every unthemed statement in the earlier
  cycles is ordinary positively-worded ME text, so this reversal cannot move
  the four cycles that reconcile to the retired PBIP.

  Matched on the full question text. If the wording is ever edited upstream
  the match silently stops applying and the score silently inverts again, so
  tests/assert_me_reverse_coded_matched.sql fails the build if any of these
  stops matching a row.
*/
reverse_coded as (

    select unnest(array[
        'It is difficult to ask other members of my team for help',
        'People on my team sometimes reject others for being different',
        'If I make a mistake in my team, it is often held against me'
    ]) as question

),

/*
  Theme / sub-theme / category / tenet.

  DAX/M equivalent: the SQL Server query's CASE ladder, which joined the
  mapping three times per cycle — once per grade band — because the question
  text differs between bands. Here the mapping is already long, so the exact
  match is one join, with the single-theme fallback above behind it.
*/
joined as (

    select
        r.respondent_id,
        r.email_address,
        r.manager_email,
        r.cycle,
        r.question,
        r.answer,
        r.target_grade,
        r.refreshed_date,

        coalesce(m.theme,     q.theme)     as theme,
        coalesce(m.sub_theme, q.sub_theme) as sub_theme,
        coalesce(m.category,  q.category)  as category,
        coalesce(m.tenet,     q.tenet)     as tenet

    from responses r
    left join theme_map m
        on  m.question     = r.question
        and m.target_grade = r.target_grade
    left join theme_by_question q
        on  q.question = r.question
        and m.question is null

),

scored as (

    select
        j.*,

        rc.question is not null as is_reverse_coded,

        /*
          Rating.  DAX:
            SWITCH(TRUE(),
              Category in {"NPS","Open Ended"}, BLANK(),
              Answer = "Agree",            3,
              Answer = "Strongly agree",   4,
              Answer = "Disagree",         2,
              Answer = "Strongly disagree",1,
              ISBLANK(Theme), BLANK(),
              BLANK())

          NPS and open-ended answers deliberately score NULL, so they drop out
          of every AVERAGE(Rating) without needing a filter at the call site.

          DEPARTURE FROM THE PBIP, and the only one in this column: a
          reverse-coded statement is scored on the flipped scale, so that
          "agrees my team holds mistakes against me" reads as a 2 and not as a
          3. The report predates these statements and had no such case; scored
          its way, good news on those three items records as a bad number.
          Both scales are written out in full rather than computed as 5 - x,
          because the mapping is the thing a reviewer needs to check.
        */
        case
            when j.category in ('NPS', 'Open Ended') then null
            when rc.question is not null then
                case
                    when lower(btrim(j.answer)) = 'agree'             then 2
                    when lower(btrim(j.answer)) = 'strongly agree'    then 1
                    when lower(btrim(j.answer)) = 'disagree'          then 3
                    when lower(btrim(j.answer)) = 'strongly disagree' then 4
                end
            else
                case
                    when lower(btrim(j.answer)) = 'agree'             then 3
                    when lower(btrim(j.answer)) = 'strongly agree'    then 4
                    when lower(btrim(j.answer)) = 'disagree'          then 2
                    when lower(btrim(j.answer)) = 'strongly disagree' then 1
                end
        end as rating,

        /*
          Promoter_Detractor.  DAX:
            IF(Answer="10","Promoter",IF(Answer="9","Promoter",
              IF(Answer="8","Passive",IF(Answer="7","Passive",
                IF(ISBLANK(Answer),"Passive","Detractor")))))

          Note the tail: a BLANK answer counts as Passive, not as missing.
          That is what the report does, so it is what this does. It only ever
          matters on the NPS question, which is the only place the measures
          read this column.
        */
        case
            when btrim(coalesce(j.answer, '')) in ('9', '10')  then 'Promoter'
            when btrim(coalesce(j.answer, '')) in ('7', '8')   then 'Passive'
            when btrim(coalesce(j.answer, '')) = ''            then 'Passive'
            else 'Detractor'
        end as promoter_detractor,

        /*
          Include.  M:  if [Sub Theme] = "DE" and [Category] = "DEI"
                        then "No" else "Yes"     (then filtered to "Yes")

          Kept as a column rather than a WHERE so the exclusion stays visible.
          On the current data every row is "Yes" — the DEI category is carried
          by ordinary ME statements whose sub-theme is "ME", not "DE".
        */
        case
            when btrim(coalesce(j.sub_theme, '')) = 'DE'
             and btrim(coalesce(j.category, ''))  = 'DEI'
            then 'No' else 'Yes'
        end as include_flag

    from joined j
    left join reverse_coded rc on rc.question = j.question

),

with_positive as (

    select
        s.*,

        /*
          Positive_Negative.  DAX:
            IF(Rating>=3,"Positive",IF(Rating>=1,"Negative"))
          Rating NULL stays NULL, which is why % positive response ignores
          NPS and open-ended rows without a filter.
        */
        case
            when s.rating >= 3 then 'Positive'
            when s.rating >= 1 then 'Negative'
        end as positive_negative

    from scored s

),

with_employee as (

    select
        p.*,

        -- Manager_BU. DAX: MAXX(FILTER(DIM_EMPLOYEE, email = Custom_Data_2), BU)
        mgr.bu    as manager_bu,
        mgr.grade as manager_grade,

        -- "Manager Gender" / "Reportee Gender". M: two NestedJoins onto
        -- DIM_EMPLOYEE, the first on Custom_Data_2, the second on
        -- Email_Address. Every other employee attribute in the report hangs
        -- off the MANAGER, because DIM_EMPLOYEE's active relationship is
        -- employee_email -> Custom_Data_2.
        mgr.gender as manager_gender,
        rep.gender as reportee_gender

    from with_positive p
    left join resolution r_mgr on r_mgr.survey_email  = p.manager_email
    left join employee   mgr   on mgr.employee_email  = r_mgr.employee_email
    left join resolution r_rep on r_rep.survey_email  = p.email_address
    left join employee   rep   on rep.employee_email  = r_rep.employee_email

),

visibility as (

    select
        e.*,

        /*
          DistinctEmpCount.  DAX:
            CALCULATE(DISTINCTCOUNT(Email_Address),
                      ALLEXCEPT(ME_Survey_Response, Custom_Data_2, Cycle))

          CycleVisibility.  DAX:
            SWITCH(TRUE(), DistinctEmpCount >= 3, "Yes", "No")

          This is the suppression rule the whole report runs on: a manager is
          only shown once at least three people have rated them.
        */
        d.distinct_emp_count

    from with_employee e
    left join (
        -- Postgres has no DISTINCT window aggregate, so the ALLEXCEPT is a
        -- pre-aggregate joined back on, rather than an OVER (PARTITION BY).
        select manager_email, cycle,
               count(distinct email_address) as distinct_emp_count
        from with_employee
        group by 1, 2
    ) d on d.manager_email = e.manager_email and d.cycle = e.cycle

)

select
    respondent_id,
    email_address,
    manager_email,
    cycle,
    question,
    answer,
    target_grade,
    refreshed_date,
    theme,
    sub_theme,
    category,
    tenet,
    rating,
    is_reverse_coded,
    promoter_detractor,
    positive_negative,
    include_flag,
    manager_bu,
    manager_grade,
    manager_gender,
    reportee_gender,
    distinct_emp_count,
    case when distinct_emp_count >= 3 then 'Yes' else 'No' end as cycle_visibility,

    -- keyNPS / themedriverKey. The PBIP needed these to relate its SUMMARIZE
    -- tables back to the fact; kept because they are the natural join keys
    -- for the manager-grain mart.
    manager_email || cycle  as manager_cycle_key,
    email_address  || cycle as respondent_cycle_key

from visibility
where include_flag = 'Yes'
  -- The source query ends with: where a.[Cycle] not in ('Aug_23','Mar_24')
  and cycle not in ('Aug_23', 'Mar_24')
