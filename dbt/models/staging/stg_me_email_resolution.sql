{{ config(materialized='table') }}

/*
  Survey email -> employee-master email, so a person who changed email domain
  still finds their own record in DIM_EMPLOYEE.

  ── Why this exists ────────────────────────────────────────────────────────
  Two email domains appear for the first time in Sep_26 (instamart.in,
  swiggyimnet.in). The survey fact keeps whatever address a person held when
  they answered, but pg_dim_employee only ever holds their CURRENT one — so a
  direct join on email fails for every cycle before the move, and the manager
  silently loses BU, department, team, grade, gender and their whole place in
  both hierarchies.

  The shape of it, from a real case: a manager rated in all five cycles, on
  the swiggy.in domain up to Mar_26 and on instamart.in in Sep_26, with an
  unchanged manager_name throughout. The master holds only the newer address,
  so Sep_24 through Mar_26 showed no BU and — worse — a NULL grade, which
  drops them out of the grade-relative percentile population entirely and
  makes it impossible for them to appear in the Action Queue for those cycles.

  It is not a handful of people. Managers with no BU, before this model:
      Sep_24 185 · Mar_25 204 · Sep_25 226 · Mar_26 357 of 1,241 · Sep_26 2
  Nearly every one is recoverable. Sep_26 is already clean, because its survey
  addresses are the current ones.

  This corrects a standing note in the knowledge base, which read the missing
  BU as a gap in pg_dim_employee. It is not a gap; it is a stale join key.

  ── What this model does NOT do ────────────────────────────────────────────
  It resolves ATTRIBUTE LOOKUP only. It deliberately does not rewrite
  identity: email_address and manager_email keep their as-answered values, so
  respondent and manager COUNTS are untouched and the four cycles that
  reconcile to the retired PBIP still reconcile exactly.

  Collapsing the two addresses into one person would change those counts —
  measured: Mar_26 respondents 4,257 -> 4,256, Sep_24 managers 970 -> 969,
  and one or two elsewhere. It would also fix the 651 repeat responders that
  the cross-cycle movement panel currently loses. That is a separate change
  with a real trade-off against the reconciliation, and it is not made here.

  ── Matching rule ──────────────────────────────────────────────────────────
  1. exact     — the address is in the master as-is. Always preferred.
  2. localpart — the part before the @ matches exactly ONE address belonging
                 to exactly ONE named person in the master.
  3. otherwise unresolved, and the attributes stay NULL as before.

  The local-part rule is deliberately strict. Of 59,044 distinct local parts
  in the master, 1,223 sit on more than one address; 1,112 of those are one
  person across domains, but 111 are genuinely different people who happen to
  share a local part. Requiring a single address AND a single name excludes
  all 111 rather than silently merging two colleagues into one record.
*/

with employee as (

    -- Already one row per email: stg_me_dim_employee collapses the 1,386
    -- rehire/transfer duplicates.
    select
        employee_email,
        split_part(employee_email, '@', 1)                  as localpart,
        lower(btrim(coalesce(employee_full_name, '')))      as full_name
    from {{ ref('stg_me_dim_employee') }}
    where employee_email is not null

),

/*
  Local parts that identify one person beyond doubt. Both conditions are
  load-bearing: one address rules out a person who still holds both, where the
  exact match would have won anyway; one name rules out the 111 collisions.
*/
unambiguous_localpart as (

    select
        localpart,
        min(employee_email) as employee_email
    from employee
    group by localpart
    having count(distinct employee_email) = 1
       and count(distinct full_name)      = 1
       and min(btrim(full_name)) <> ''

),

survey_emails as (

    select distinct email
    from (
        select email_address as email from {{ ref('stg_me_survey_responses') }}
        union
        select manager_email as email from {{ ref('stg_me_survey_responses') }}
    ) e
    where email is not null

)

select
    s.email                                          as survey_email,
    coalesce(x.employee_email, u.employee_email)     as employee_email,
    case
        when x.employee_email is not null then 'exact'
        when u.employee_email is not null then 'localpart'
        else 'unresolved'
    end                                              as match_type
from survey_emails s
left join employee x
    on x.employee_email = s.email
left join unambiguous_localpart u
    on  u.localpart = split_part(s.email, '@', 1)
    and x.employee_email is null
