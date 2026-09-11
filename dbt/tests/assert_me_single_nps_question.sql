-- mart_me_manager_cycle identifies the NPS question by Category = 'NPS'
-- rather than by its literal text, so that a re-wording does not silently
-- zero out every NPS figure. That substitution is only safe while exactly
-- one question carries the category in each cycle.
--
-- Fails (returns rows) if a cycle ever has none, or more than one.

select
    cycle,
    count(distinct question) as nps_questions
from {{ ref('int_me_responses_scored') }}
where category = 'NPS'
group by cycle
having count(distinct question) <> 1
