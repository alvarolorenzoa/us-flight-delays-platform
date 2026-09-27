-- Delays snowball during the day: punctuality by scheduled departure hour.
select
    scheduled_dep_hour,
    count(*)                                                     as departures,
    round(100 * avg(cast(is_dep_delayed as int)), 2)             as dep_delay_pct,
    round(avg(dep_delay_min), 2)                                 as avg_dep_delay_min,
    round(100 * avg(case when late_aircraft_delay_min > 0 then 1 else 0 end), 2) as late_aircraft_pct
from {{ ref('fct_flights') }}
where not is_cancelled
group by 1
order by 1
