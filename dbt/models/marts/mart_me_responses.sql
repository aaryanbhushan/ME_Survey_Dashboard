{{ config(materialized='table') }}

/*
  Response grain — one row per (respondent, question, cycle), with every
  attribute the dashboard slices by already joined on.

  This is the single table the app reads for the Pulse, Themes and Cuts
  views. It is deliberately wide rather than clever: the aggregations the
  report performs (theme score, NPS, % positive, every "Scores by ..." pivot)
  are all group-bys over this one table, so the app needs no joins at
  read time and no second round trip over the tunnel.

  The manager hierarchy and HRBP hierarchy columns are what make the report's
  "Scores by Manager Hierarchy" and "Scores by HR Hierarchy" pivots possible.
  Both hang off the MANAGER being rated, not the respondent.
*/

with responses as (

    select * from {{ ref('int_me_responses_scored') }}

),

employee as (

    select
        employee_email,
        employee_id,
        bu,
        department,
        team,
        grade,
        grade_bucket,
        gender,
        latest_rating,
        tenure_bucket,
        mandate,
        designation
    from {{ ref('stg_me_dim_employee') }}

),

manager_line as (

    select employee_id, l8id, l7id, l6id, l5id
    from {{ ref('stg_me_manager_hierarchy') }}

),

hrbp_line as (

    select employee_id, h3, h4, h5, hrbp_immediate
    from {{ ref('stg_me_hrbp_hierarchy') }}

),

/*
  Survey email -> master email, so a manager who changed email domain keeps
  their attributes AND their place in both hierarchies. Both hierarchy joins
  hang off e.employee_id, so resolving the employee join fixes them too.
*/
resolution as (

    select survey_email, employee_email
    from {{ ref('stg_me_email_resolution') }}
    where employee_email is not null

)

select
    r.respondent_id,
    r.email_address,
    r.manager_email,
    r.cycle,
    r.question,
    r.answer,
    r.target_grade,
    r.refreshed_date,

    r.theme,
    r.sub_theme,
    r.category,
    r.tenet,

    r.rating,
    -- True on the three negatively-worded psychological-safety statements
    -- Sep_26 introduced, whose rating is scored on the flipped scale. Carried
    -- through so a reader can tell why an "agree" on those reads as a 2.
    r.is_reverse_coded,
    r.promoter_detractor,
    r.positive_negative,
    r.distinct_emp_count,
    r.cycle_visibility,

    r.manager_gender,
    r.reportee_gender,

    -- Manager attributes. DIM_EMPLOYEE's active relationship in the PBIP is
    -- employee_email -> Custom_Data_2, so every "Scores by ..." pivot in the
    -- report describes the manager. Keeping that here means the Cuts view is
    -- a group-by and nothing more.
    e.employee_id    as manager_employee_id,
    e.bu             as manager_bu,
    e.department     as manager_department,
    e.team           as manager_team,
    e.grade          as manager_grade,
    e.grade_bucket   as manager_grade_bucket,
    e.latest_rating  as manager_latest_rating,
    e.tenure_bucket  as manager_tenure_bucket,
    e.mandate        as manager_mandate,
    e.designation    as manager_designation,

    -- Reporting line ABOVE the manager, top-down. stg_me_manager_hierarchy
    -- restates pg_manager_hierarchy in the PBIP's L-numbering (L9 = CEO), so
    -- these are the same four levels the report's "Scores by Manager
    -- Hierarchy" pivot drills: L8id > L7id > L6id > L5id.
    --
    -- Both hierarchy models are keyed on EMPLOYEE_ID, not email, so the join
    -- goes through the manager's id from dim_employee.
    ml.l8id as mgr_l8_email,
    ml.l7id as mgr_l7_email,
    ml.l6id as mgr_l6_email,
    ml.l5id as mgr_l5_email,

    -- HRBP line supporting the manager. stg_me_hrbp_hierarchy renumbers the
    -- ragged bottom-up chain top-down as h1..h8; the report's L6 > L5 > L4
    -- drill is h3 > h4 > h5 there. See that model's header for why a constant
    -- offset is not available.
    hl.h3 as hrbp_l6_email,
    hl.h4 as hrbp_l5_email,
    hl.h5 as hrbp_l4_email,
    hl.hrbp_immediate as hrbp_immediate_email

from responses r
left join resolution    rm on rm.survey_email  = r.manager_email
left join employee      e  on e.employee_email = rm.employee_email
left join manager_line  ml on ml.employee_id   = e.employee_id
left join hrbp_line     hl on hl.employee_id   = e.employee_id
