-- Every airport seen as origin or destination; hubs get coordinates from the seed.
with seen as (
    select origin as airport_code, origin_city as city_name, origin_state as state from {{ ref('stg_flights') }}
    union
    select dest, dest_city, dest_state from {{ ref('stg_flights') }}
),
one_per_airport as (
    select airport_code, any_value(city_name) as city_name, any_value(state) as state
    from seen group by airport_code
)
select
    a.airport_code,
    coalesce(h.airport_name, a.airport_code)  as airport_name,
    a.city_name,
    a.state,
    h.latitude,
    h.longitude,
    h.airport_code is not null                as is_hub
from one_per_airport a
left join {{ ref('hub_airports') }} h using (airport_code)
