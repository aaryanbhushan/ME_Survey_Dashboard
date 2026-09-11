import os, warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import pandas as pd
from pg_connection import get_pg_conn
c=get_pg_conn(); pd.set_option('display.width',240)
def q(s): return pd.read_sql(s,c)

print("### HEADLINE vs PBIX  (Sep_24 3290/970/3.47/56.9 | Mar_25 3214/1001/3.48/57.8 | Sep_25 3671/953/3.53/59.3 | Mar_26 4257/1241/3.46/52.9)")
print(q("""
with nps as (
  select cycle,
    count(distinct email_address) filter (where promoter_detractor='Promoter')  p,
    count(distinct email_address) filter (where promoter_detractor='Passive')   a,
    count(distinct email_address) filter (where promoter_detractor='Detractor') d
  from marts.mart_me_responses where category='NPS' group by 1)
select r.cycle,
  count(distinct r.email_address) respondents,
  count(distinct r.manager_email) managers,
  round(avg(r.rating)::numeric,2) me_score,
  round((n.p-n.d)::numeric/nullif(n.p+n.a+n.d,0)*100,1) nps
from marts.mart_me_responses r left join nps n using (cycle)
group by 1,n.p,n.a,n.d order by 1""").to_string())

print("\n### themes Mar_26 (PBIX: 6 themes, BOBIP 3.43 CTFL 3.42 DA 3.50 IASOP 3.60 MTPS 3.42 NC 3.46)")
print(q("""select theme, round(avg(rating)::numeric,2) score, count(distinct question) nq
from marts.mart_me_responses where cycle='Mar_26' and theme is not null and rating is not null
group by 1 order by 1""").to_string())

print("\n### manager mart: visible managers + ME bands (PBIX Mar_26: 608 visible, 30/333/245)")
print(q("""select cycle, count(*) mgrs, count(*) filter (where cycle_visibility='Yes') visible,
  count(*) filter (where cycle_visibility='Yes' and me_bucket='Below 70%') b70,
  count(*) filter (where cycle_visibility='Yes' and me_bucket='70%-90%') b7090,
  count(*) filter (where cycle_visibility='Yes' and me_bucket='90% & Above') b90,
  count(*) filter (where is_below_grade_p25) below_p25,
  count(*) filter (where has_negative_nps) neg_nps
from marts.mart_me_manager_cycle group by 1 order by 1""").to_string())
c.close()
