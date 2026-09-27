-- Route-level punctuality (routes with at least 30 flights in the month).
select
    strftime(flight_date, '%Y-%m')                                        as year_month,
    route,
    origin_code,
    dest_code,
    round(avg(distance_miles), 0)                                         as distance_miles,
    count(*)                                                              as flights,
    count(distinct carrier_code)                                          as carriers,
    round(100 * avg(case when is_completed then 1 - cast(is_arr_delayed as int) end), 2) as on_time_pct,
    round(avg(case when is_completed then arr_delay_min end), 2)          as avg_arr_delay_min,
    round(100 * avg(cast(is_cancelled as int)), 2)                        as cancellation_pct
from {{ ref('fct_flights') }}
group by all
having count(*) >= 30
