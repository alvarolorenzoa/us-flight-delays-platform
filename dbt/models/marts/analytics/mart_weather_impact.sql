-- How much does the weather at the origin hub change the chance of a delayed departure?
with hub_flights as (
    select * from {{ ref('fct_flights') }} where has_weather
),
by_condition as (
    select
        origin_code                                              as airport_code,
        weather_condition,
        count(*)                                                 as departures,
        round(100 * avg(cast(is_dep_delayed as int)), 2)         as dep_delay_pct,
        round(avg(dep_delay_min), 2)                             as avg_dep_delay_min,
        round(100 * avg(cast(is_cancelled as int)), 2)           as cancellation_pct
    from hub_flights
    group by all
),
all_hubs as (
    select
        'ALL HUBS'                                               as airport_code,
        weather_condition,
        count(*),
        round(100 * avg(cast(is_dep_delayed as int)), 2),
        round(avg(dep_delay_min), 2),
        round(100 * avg(cast(is_cancelled as int)), 2)
    from hub_flights
    group by all
),
combined as (
    select * from by_condition union all select * from all_hubs
)
select
    c.*,
    -- uplift vs. the same airport in dry & calm conditions (percentage points)
    round(c.dep_delay_pct - max(case when weather_condition = 'Dry & calm' then dep_delay_pct end)
          over (partition by airport_code), 2)                   as delay_uplift_pp
from combined c
