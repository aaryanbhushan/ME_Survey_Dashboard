{{ config(materialized='table') }}

{# Referenced by every downstream model, and the dedup window is not free. #}

/*
  Employee master for the report, restricted the way the PBIP's DIM_EMPLOYEE
  query was: `Table.SelectRows(each [isExists] = "True")`.

  latest_rating is derived from swiggydbo.pms_rating rather than read off the
  dimension -- see the note above that CTE for why the PBIP's source is
  unusable here. The join is LEFT so an employee with no rating on file keeps
  their responses and simply falls out of the "By PMS Rating" breakdown.

  Tenure is deliberately NOT computed here. It depends on current_date, and
  this model is materialised as a table, so the value would freeze at whatever
  day dbt last ran and drift silently from then on. It is computed in data.py
  at load time instead; date_of_joining, date_of_exit and employeestatus are
  carried through for that.
*/

with raw as (

    select
        e.employee_id,
        e.employee_full_name,
        lower(trim(e.employee_email))                as employee_email,
        e.manager_id,
        e.maanger_name                               as manager_name,
        lower(trim(e.manager_email))                 as manager_email,
        e.gender,
        e.bu,
        e.department,
        e.team,
        e.grade,
        e.designation,
        e.employee_type,
        e.mandate,
        e.office_city,
        e.office_state,
        e.office_region,
        e.group_company,
        e.employeestatus,
        e.date_of_joining,
        -- Tenure with the GROUP, which survives an internal transfer. The
        -- PBIP measured from this; it is also what decides whether a
        -- hierarchy leader was actually in post for a given survey cycle.
        e.group_date_of_joining,
        e.date_of_exit,
        e.isexists
    from {{ source('swiggydbo', 'pg_dim_employee') }} e
    where e.isexists is true

),

/*
  ONE ROW PER EMAIL.

  1,386 emails carry more than one isExists record -- rehires and entity
  transfers, e.g. Royan Mody holds three (two Separated, one Active) across
  employee_ids 1646582 / 2017733 / 2021652.

  Note this is NOT a Postgres artefact. swiggydbo.dim_employee -- the 1:1
  mirror of the SQL Server table the PBIP read, and byte-identical to
  pg_dim_employee across 76,138 rows -- carries the same 1,386 duplicates, and
  the PBI relationship was declared many-to-many, not one-to-many. So the PBIP
  did not fan the fact out; it put each duplicated person under EVERY grade,
  BU and manager they held.

  De-duplicating is still the right call -- one person should count once -- but
  it is a deliberate improvement on the PBIP, not a repair of something
  Postgres broke.

  Only 7 survey respondents actually sit on a duplicated email, but each would
  have counted two or three times in every respondent total and pulled the
  averages with them.

  Filtering to Active would collapse all but one duplicate, but the "By Status"
  visual splits Active against Separated and needs leavers to survive. So keep
  every email once, preferring the record that best represents the person now:
  Active over Separated, then the most recent joining date, then the highest
  employee_id as a stable final tie-break.
*/
deduped as (

    select
        employee_id, employee_full_name, employee_email,
        manager_id, manager_name, manager_email,
        gender, bu, department, team, grade, designation,
        employee_type, mandate, office_city, office_state, office_region,
        group_company, employeestatus, date_of_joining, group_date_of_joining,
        date_of_exit, isexists
    from (
        select
            r.*,
            row_number() over (
                partition by r.employee_email
                order by
                    (r.employeestatus = 'Active') desc,
                    r.date_of_joining desc nulls last,
                    r.employee_id desc
            ) as rn
        from raw r
        where r.employee_email is not null
          and r.employee_email <> ''
    ) ranked
    where rn = 1

),

base as (

    select * from deduped

),

/*
  LATEST PMS RATING.

  The PBIP read DIM_EMPLOYEE[Latest_Rating] straight off the dimension. That
  column exists in swiggydbo.dim_employee too, but it is NULL for all 76,111
  rows -- Airflow never populates it -- so reading it the way the PBIP did
  leaves the "By PMS Rating" visual permanently empty.

  swiggydbo.pms_rating carries the real thing: one row per (employee, review
  cycle), 40,597 rows over 12,449 employees. "Latest" is therefore derived
  here rather than read, by taking each employee's most recent effective date.
  Covers 4,955 of the 5,019 respondents.

  Ratings outside 1-5 are dropped (blanks and in-flight cycles), matching what
  hc_marts.stg_dei_dash_pms does with the same table.

  The tie-break on final_rating only bites for 2 employees in the whole table,
  both on a 2023 cycle that was recorded twice under different names; it is
  here for determinism, not because the choice is meaningful.
*/
latest_rating as (

    select distinct on (employee_id)
        employee_id,
        final_rating::int                            as latest_rating
    from {{ source('swiggydbo', 'pms_rating') }}
    where final_rating in ('1', '2', '3', '4', '5')
    order by employee_id, rating_effective_date desc, final_rating desc

),

with_rating as (

    select
        b.*,
        r.latest_rating
    from base b
    left join latest_rating r using (employee_id)

),

derived as (

    select
        *,

        /*
          Grade_bucket. M:
            if grade in {"1","2","3"}            then "3 & Below"
            else if grade in {"4","5","6","7"}   then "4--7"
            else if grade in {"8","9","10"}      then "8--10"
            else if grade in {"11","12","12B","13"} then "11 & Above"
            else "NA"
        */
        case
            when btrim(grade) in ('1', '2', '3')                then '3 & Below'
            when btrim(grade) in ('4', '5', '6', '7')           then '4--7'
            when btrim(grade) in ('8', '9', '10')               then '8--10'
            when btrim(grade) in ('11', '12', '12B', '13')      then '11 & Above'
            else 'NA'
        end as grade_bucket,

        /*
          Tenure In Days / Tenure Bucket. M:
            Tenure In Days = (date_of_exit ?? today) - group_date_of_joining
            <=90 "0-3 Months"; <=180 "3-6 Months"; <=365 "6 Months-1 yr";
            <=730 "1-2 yr";    <=1095 "2-3 yr";    >1095 "3 yrs & Above"

          NOTE: the PBIP measures from group_date_of_joining (tenure with the
          group, which survives an internal transfer). This uses
          date_of_joining because that is the column stg_me_dim_employee
          already carries. If pg_dim_employee exposes group_date_of_joining,
          swap it in here — it is the more faithful base and the two differ
          for anyone who has moved entity.
        */
        case
            when date_of_joining is null then null
            else (coalesce(date_of_exit, current_date) - date_of_joining)
        end as tenure_in_days

    from with_rating

)

select
    d.employee_id,
    d.employee_full_name,
    d.employee_email,
    d.manager_id,
    d.manager_name,
    d.manager_email,
    d.gender,
    d.bu,
    d.department,
    d.team,
    d.grade,
    d.grade_bucket,
    d.designation,
    d.employee_type,
    d.mandate,
    d.office_city,
    d.office_state,
    d.office_region,
    d.group_company,
    d.employeestatus,
    d.date_of_joining,
    d.group_date_of_joining,
    d.date_of_exit,
    d.isexists,
    d.latest_rating,
    d.tenure_in_days,
    case
        when d.tenure_in_days is null      then null
        when d.tenure_in_days <=   90      then '0-3 Months'
        when d.tenure_in_days <=  180      then '3-6 Months'
        when d.tenure_in_days <=  365      then '6 Months-1 yr'
        when d.tenure_in_days <=  730      then '1-2 yr'
        when d.tenure_in_days <= 1095      then '2-3 yr'
        else                                    '3 yrs & Above'
    end as tenure_bucket
from derived d
