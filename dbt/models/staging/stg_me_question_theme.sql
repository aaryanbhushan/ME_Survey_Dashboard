{{ config(materialized='view') }}

/*
  Question -> theme / sub-theme / category / tenet, one row per
  (question, target_grade).

  The source table is WIDE — one row per concept, with the wording for each
  grade band in its own column:

      theme | sub theme | category | grade 10 and above | grade 8 and 9
            | grade 7 and below | tenet                       (63 rows)

  ...and it has NO cycle column, unlike the PBIP, which read three separate
  per-cycle mapping tables and picked a branch with a CASE ladder. Here the
  three band columns are unpivoted into rows and the band becomes part of the
  key, which is what the CASE ladder was doing by hand.

  Two hazards this model exists to neutralise:

  1. FAN-OUT. The unpivoted mapping is NOT unique on (question, target_grade)
     — the open-ended prompts ("3 things you want your manager to STOP
     doing.") appear on more than one row, as does one real statement. Joined
     raw, that duplicated response rows and inflated Mar_25 by 13% and Sep_24
     by 13%. distinct on (question, target_grade) fixes it at the source.

  2. DIRTY THEME TEXT. The raw column carries trailing colons, a leading
     space, "Pitstop" for "Pit Stop", and BOTH "Cross the Finish Line" and
     "Cross the Finish line". Left alone that reads as 11 themes instead of
     the 6 the report shows. The cleanup below is the M query's, in its
     original order, plus a case fix the PBIP did not need because its
     per-cycle tables happened to be internally consistent.
*/

with unpivoted as (

    select btrim("grade 7 and below")  as question,
           'Grade 7 and below'         as target_grade,
           theme, "sub theme" as sub_theme, category, tenet
    from {{ source('swiggydbo', 'me_question_theme_mapping') }}

    union all
    select btrim("grade 8 and 9"),      'Grade 8 and 9',
           theme, "sub theme", category, tenet
    from {{ source('swiggydbo', 'me_question_theme_mapping') }}

    union all
    select btrim("grade 10 and above"), 'Grade 10 and above',
           theme, "sub theme", category, tenet
    from {{ source('swiggydbo', 'me_question_theme_mapping') }}

),

cleaned as (

    select
        nullif(question, '')            as question,
        target_grade,

        /*
          Theme cleanup. M order:
            "Open Ended Questions" -> ''   then  ':' -> ''   then  trim
            then "Pitstop" -> "Pit Stop"
          The colon strip must precede the trim, or "Drive Alignment:" keeps a
          trailing space and splits into a second theme.

          initcap() is NOT used — it would turn "Bring out the Best in People"
          into "Bring Out The Best In People". The only casing collision in
          the data is Finish Line / Finish line, so that one is fixed by name.
        */
        nullif(
            replace(
                replace(
                    replace(
                        btrim(
                            replace(
                                replace(coalesce(theme, ''),
                                        'Open Ended Questions', ''),
                                ':', '')
                        ),
                        'Pitstop', 'Pit Stop'),
                    'Cross the Finish line', 'Cross the Finish Line'),
                'Fairiness and Inclusion', 'Fairness and Inclusion'),
            '')                         as theme,

        nullif(btrim(sub_theme), '')    as sub_theme,
        nullif(btrim(category), '')     as category,
        nullif(btrim(tenet), '')        as tenet

    from unpivoted
    where nullif(btrim(question), '') is not null

)

-- One row per (question, target_grade). Where the source duplicates a pair,
-- the row carrying a theme wins over one that does not.
select distinct on (question, target_grade)
    question,
    target_grade,
    theme,
    sub_theme,
    category,
    tenet
from cleaned
order by question, target_grade, theme nulls last, category nulls last
