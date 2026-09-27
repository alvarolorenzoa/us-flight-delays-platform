-- Every carrier present in the data, enriched with the reference seed.
with seen as (
    select distinct carrier_code from {{ ref('stg_flights') }}
)
select
    s.carrier_code,
    coalesce(c.carrier_name, s.carrier_code)  as carrier_name,
    coalesce(c.carrier_type, 'Other')         as carrier_type
from seen s
left join {{ ref('carriers') }} c using (carrier_code)
