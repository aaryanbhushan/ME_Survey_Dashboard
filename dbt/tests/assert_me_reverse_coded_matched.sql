/*
  Every reverse-coded statement must still match at least one response row.

  The reversal in int_me_responses_scored is keyed on the full question text.
  That is the right key — it is what the survey tool exports — but it fails
  silently: reword one of these statements upstream and the match stops
  applying, the item quietly reverts to the ordinary scale, and the ME score
  drops by ~0.2 with nothing in the build to say why. This test turns that
  silent inversion into a failed build.

  Returns a row per statement that matched nothing.
*/

with expected as (

    select unnest(array[
        'It is difficult to ask other members of my team for help',
        'People on my team sometimes reject others for being different',
        'If I make a mistake in my team, it is often held against me'
    ]) as question

),

matched as (

    select question, count(*) as n
    from {{ ref('int_me_responses_scored') }}
    where is_reverse_coded
    group by question

)

select
    e.question,
    coalesce(m.n, 0) as rows_matched
from expected e
left join matched m on m.question = e.question
where coalesce(m.n, 0) = 0
