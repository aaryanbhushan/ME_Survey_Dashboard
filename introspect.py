"""Inspect the four ME source tables and print everything the dbt staging
models need to know: schema, columns, row counts, and the distinct values of
the columns the PBIP's logic keys on (cycle, target grade, answer).

Run this once, before the staging models are finalised:

    python introspect.py

It writes introspect_output.txt beside itself so the result can be read back
without a second round trip over the tunnel.
"""
import os
import sys

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '.env'))

import pandas as pd

from pg_connection import get_pg_conn

# The four tables the ME dashboard reads, plus the three shared ones that are
# already maintained for the other dashboards on this estate.
ME_TABLES = [
    'me_question_theme_mapping',
    'me_survey_recipient_merged',
    'me_survey_response_merged',
    'mesurvey_responses',
]
SHARED_TABLES = ['pg_dim_employee', 'pg_manager_hierarchy', 'pg_hrbp_hierarchy']

# Columns whose distinct values decide how the staging models branch. The
# PBIP switches on cycle and target grade, and derives Rating and
# Promoter_Detractor from the answer text, so the exact spellings matter.
VALUE_COLUMNS = ['cycle', 'target_grade', 'answer', 'theme', 'category',
                 'sub_theme', 'tenet', 'grade', 'question_type', 'status']

out = []


def emit(line=''):
    print(line)
    out.append(str(line))


def main():
    conn = get_pg_conn()

    emit('=' * 78)
    emit('WHERE THE TABLES LIVE')
    emit('=' * 78)
    locs = pd.read_sql(
        """
        select table_schema, table_name, table_type
        from information_schema.tables
        where lower(table_name) = any(%s)
        order by table_name, table_schema
        """,
        conn, params=(ME_TABLES + SHARED_TABLES,))
    emit(locs.to_string(index=False) if len(locs) else '  (none found)')

    if not len(locs):
        emit('\nNothing matched. Listing anything ME-ish so the real names show up:')
        like = pd.read_sql(
            """
            select table_schema, table_name
            from information_schema.tables
            where table_name ilike '%%me!_%%' escape '!'
               or table_name ilike '%%mesurvey%%'
               or table_name ilike '%%managerial%%'
            order by 1, 2
            """, conn)
        emit(like.to_string(index=False))
        return 1

    for _, row in locs.iterrows():
        schema, table = row.table_schema, row.table_name
        fq = f'{schema}.{table}'
        emit()
        emit('=' * 78)
        emit(f'{fq}')
        emit('=' * 78)

        cols = pd.read_sql(
            """
            select column_name, data_type, is_nullable
            from information_schema.columns
            where table_schema = %s and table_name = %s
            order by ordinal_position
            """, conn, params=(schema, table))
        emit(f'-- {len(cols)} columns')
        emit(cols.to_string(index=False))

        try:
            n = pd.read_sql(f'select count(*) as n from {fq}', conn).n.iloc[0]
            emit(f'-- {n:,} rows')
        except Exception as exc:
            emit(f'-- row count failed: {exc}')
            continue

        # A couple of sample rows make the shape obvious in a way the column
        # list alone does not — especially for the mapping table, which the
        # PBIP joined three different ways depending on grade band.
        try:
            emit('-- sample')
            sample = pd.read_sql(f'select * from {fq} limit 3', conn)
            with pd.option_context('display.max_columns', None,
                                   'display.width', 250,
                                   'display.max_colwidth', 40):
                emit(sample.to_string(index=False))
        except Exception as exc:
            emit(f'-- sample failed: {exc}')

        # Distinct values for the branching columns.
        present = [c for c in cols.column_name
                   if c.lower() in VALUE_COLUMNS]
        for col in present:
            try:
                vals = pd.read_sql(
                    f'select "{col}" as v, count(*) as n from {fq} '
                    f'group by 1 order by 2 desc limit 25', conn)
                emit(f'-- distinct {col} (top 25)')
                emit(vals.to_string(index=False))
            except Exception as exc:
                emit(f'-- distinct {col} failed: {exc}')

    conn.close()
    return 0


if __name__ == '__main__':
    code = main()
    with open(os.path.join(HERE, 'introspect_output.txt'), 'w',
              encoding='utf-8') as fh:
        fh.write('\n'.join(out))
    print(f'\nWritten to {os.path.join(HERE, "introspect_output.txt")}')
    sys.exit(code)
