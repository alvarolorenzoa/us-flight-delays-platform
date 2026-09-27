-- Network-wide KPIs per month.
select
    strftime(flight_date, '%Y-%m')                                        as year_month,
    count(*)                                                              as flights,
    round(100 * avg(case when is_completed then 1 - cast(is_arr_delayed as int) end), 2) as on_time_pct,
    round(avg(case when is_completed then arr_delay_min end), 2)          as avg_arr_delay_min,
    round(100 * avg(cast(is_cancelled as int)), 2)                        as cancellation_pct,
    round(100 * avg(cast(is_diverted as int)), 2)                         as diversion_pct,
    round(sum(carrier_delay_min + weather_delay_min + nas_delay_min + security_delay_min
              + late_aircraft_delay_min) / 60, 0)                         as total_delay_hours
from {{ ref('fct_flights') }}
group by 1
order by 1
