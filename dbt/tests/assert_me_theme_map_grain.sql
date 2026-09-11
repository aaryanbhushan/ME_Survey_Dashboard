-- The theme mapping must be unique on (question, target_grade).
--
-- The source is WIDE and does duplicate: the open-ended prompts appear on
-- more than one row, as does one real statement. stg_me_question_theme
-- de-duplicates with DISTINCT ON; this test is what proves that guard is
-- still doing its job.
--
-- Left unguarded, int_me_responses_scored's join duplicates response rows —
-- one copy per extra mapping row — and every response count, theme score and
-- NPS in the dashboard inflates. Measured before the fix: Mar_25 +13%,
-- Sep_24 +13%.

select question, target_grade, count(*) as n
from {{ ref('stg_me_question_theme') }}
group by 1, 2
having count(*) > 1
