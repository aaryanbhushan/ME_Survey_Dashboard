-- mart_me_manager_cycle must be one row per (manager, cycle).
--
-- The realistic way it stops being that is a duplicated employee_email in
-- dim_employee: the join fans out and every count, score and NPS in the
-- dashboard inflates silently. Cheaper to fail the build than to explain a
-- 2x headcount to a stakeholder.

select manager_email, cycle, count(*) as n
from {{ ref('mart_me_manager_cycle') }}
group by 1, 2
having count(*) > 1
