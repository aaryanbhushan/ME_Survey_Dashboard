{{ config(materialized='view') }}

/*
  HRBP hierarchy, renumbered TOP-DOWN as h1..h10 (h1 = topmost HRBP).

  Unlike the reporting line, this one cannot be mapped onto the PBIP's
  L-numbering by a constant offset. pg_hrbp_hierarchy is BOTTOM-UP
  (l1_hrbp_email = the immediate HRBP) and the chains are ragged:

      top of chain          length   employees
      the CEO                    8      30,095
      a second root HRBP       2-6      31,023
      (a long tail of others)

  The PBIP's HRBPHierarchy was right-aligned at L8 with L8 = the CEO for
  everyone, so its L6/L5/L4/L3 sat at a fixed depth from the top. Two
  populations of different chain length cannot both keep that alignment.

  Resolution (agreed with the report owner): reverse each chain so h1 is the
  topmost HRBP and count DOWN from there. The report's L6->L5->L4->L3 drill
  becomes h3->h4->h5->h6, preserving the top-down intent of the visual. Level
  labels will not line up with the retired PBIP for the shorter-chain
  population -- that is the deliberate trade for using current, complete data.

  Chains are compacted before reversing: pg leaves holes (employee 1010001 has
  an empty l1_hrbp_email but a populated l2..l9), and a hole must not consume
  a level or every h-number below it would shift.
*/

with chains as (

    select
        employee_id,
        -- array_remove drops the holes; the array is bottom-up at this point.
        array_remove(
            array_remove(
                array[
                    lower(trim(l1_hrbp_email)),  lower(trim(l2_hrbp_email)),
                    lower(trim(l3_hrbp_email)),  lower(trim(l4_hrbp_email)),
                    lower(trim(l5_hrbp_email)),  lower(trim(l6_hrbp_email)),
                    lower(trim(l7_hrbp_email)),  lower(trim(l8_hrbp_email)),
                    lower(trim(l9_hrbp_email)),  lower(trim(l10_hrbp_email))
                ],
                ''
            ),
            null
        )                                            as chain_up
    from {{ source('swiggydbo', 'pg_hrbp_hierarchy') }}

),

sized as (

    select
        employee_id,
        chain_up,
        coalesce(array_length(chain_up, 1), 0)       as chain_len
    from chains

)

select
    employee_id,
    chain_len                                        as hrbp_chain_len,
    -- h1 = topmost = last element of the bottom-up array.
    chain_up[chain_len - 0] as h1,
    chain_up[chain_len - 1] as h2,
    chain_up[chain_len - 2] as h3,
    chain_up[chain_len - 3] as h4,
    chain_up[chain_len - 4] as h5,
    chain_up[chain_len - 5] as h6,
    chain_up[chain_len - 6] as h7,
    chain_up[chain_len - 7] as h8,
    -- The immediate HRBP, kept because it is stable across both populations
    -- and is what most consumers actually mean by "my HRBP".
    chain_up[1]             as hrbp_immediate
from sized
