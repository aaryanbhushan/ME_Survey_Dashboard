/*
  stg_me_email_resolution must hold exactly ONE row per survey_email.

  This is the highest-consequence grain in the project. The resolution is
  joined to the fact twice in int_me_responses_scored (manager and reportee)
  and once more in mart_me_responses. A single duplicated survey_email
  therefore multiplies response rows, and because almost every measure is a
  DISTINCTCOUNT of email_address the inflation would not show up in the
  respondent count -- it would quietly reweight AVERAGE(Rating) instead, which
  is exactly the kind of silently-wrong number this project has already been
  bitten by once (see the SELECT DISTINCT note in stg_me_survey_responses).

  Returns a row per offending email.
*/

select
    survey_email,
    count(*) as rows_for_email
from {{ ref('stg_me_email_resolution') }}
group by survey_email
having count(*) > 1
