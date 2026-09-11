-- The Rating SWITCH is the single most load-bearing translation in this
-- project: it turns answer text into the 1-4 scale every score is built on.
-- If the source ever ships an answer spelling the CASE does not know
-- ("Somewhat agree", a trailing space that btrim misses, a locale variant),
-- the row scores NULL and silently vanishes from every average rather than
-- erroring.
--
-- Fails if a scorable row (has a theme, is not NPS or open-ended) has an
-- answer but no rating.

select
    cycle,
    answer,
    count(*) as rows_unscored
from {{ ref('int_me_responses_scored') }}
where theme is not null
  and coalesce(category, '') not in ('NPS', 'Open Ended')
  and answer is not null
  and rating is null
group by cycle, answer
