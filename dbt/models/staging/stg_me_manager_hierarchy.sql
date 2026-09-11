{{ config(materialized='table') }}

{# A 10-way union, a join and a group-by. int_me_avp_leaders reads it twice
   more, so as a view it was recomputed on every reference -- that alone put
   mart_ps_avp_respondents at 9 minutes. Materialised. #}

/*
  Reporting hierarchy, re-expressed in the PBIP's L-numbering.

  ORIENTATION. The two tables are mirror images of each other:

      pg_manager_hierarchy   l1_id  = CEO, descending, LEFT-aligned at the top,
                             holds EMPLOYEE IDS
      PBIP ManagerHierarchy  L9id   = CEO, descending, RIGHT-aligned at L9,
                             holds EMAILS

  Both anchor at the top, so the offset is constant and the mapping is exact:

      L{n}id  =  l{10 - n}_id        (L9<-l1, L8<-l2, ... L0<-l10)

  Verified row-by-row against the surviving SQL Server mirror
  swiggydbo."ManagerHierarchy" for employees 1010001 and 1010007, e.g. 1010007:
      pg   l1=harsha  l2=madhusudhan.rao  l3=rajeev.kumar  l4=raghuvaran.g
      PBIP L9=harsha  L8=madhusudhan.rao  L7=rajeev.kumar  L6=raghuvaran.g

  That mirror is NOT used as the source: it was last refreshed 2026-06-01 and
  covers 60,223 employees against pg_manager_hierarchy's 76,111.

  The report reads L8id..L3id, i.e. CEO-1 down to CEO-6.
*/

with unpivoted as (

    select employee_id, 1 as pg_level, l1_id as mgr_id from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  2, l2_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  3, l3_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  4, l4_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  5, l5_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  6, l6_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  7, l7_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  8, l8_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id,  9, l9_id  from {{ source('swiggydbo', 'pg_manager_hierarchy') }}
    union all select employee_id, 10, l10_id from {{ source('swiggydbo', 'pg_manager_hierarchy') }}

),

resolved as (

    select
        u.employee_id,
        10 - u.pg_level                              as pbi_level,   -- L9..L0
        lower(trim(d.employee_email))                as mgr_email,
        d.employee_full_name                         as mgr_name
    from unpivoted u
    join {{ source('swiggydbo', 'pg_dim_employee') }} d
      on d.employee_id = u.mgr_id
    where u.mgr_id is not null
      and u.mgr_id <> ''
      and d.employee_email is not null
      and d.employee_email <> ''

)

select
    employee_id,
    max(mgr_email) filter (where pbi_level = 9) as l9id,
    max(mgr_email) filter (where pbi_level = 8) as l8id,
    max(mgr_email) filter (where pbi_level = 7) as l7id,
    max(mgr_email) filter (where pbi_level = 6) as l6id,
    max(mgr_email) filter (where pbi_level = 5) as l5id,
    max(mgr_email) filter (where pbi_level = 4) as l4id,
    max(mgr_email) filter (where pbi_level = 3) as l3id,
    max(mgr_email) filter (where pbi_level = 2) as l2id,
    max(mgr_email) filter (where pbi_level = 1) as l1id,
    max(mgr_email) filter (where pbi_level = 0) as l0id,
    max(mgr_name)  filter (where pbi_level = 8) as l8_name,
    max(mgr_name)  filter (where pbi_level = 7) as l7_name,
    max(mgr_name)  filter (where pbi_level = 6) as l6_name,
    max(mgr_name)  filter (where pbi_level = 5) as l5_name,
    max(mgr_name)  filter (where pbi_level = 4) as l4_name,
    max(mgr_name)  filter (where pbi_level = 3) as l3_name
from resolved
group by employee_id
