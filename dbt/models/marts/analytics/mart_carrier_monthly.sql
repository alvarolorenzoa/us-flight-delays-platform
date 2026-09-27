-- Airline punctuality ranking per month.
with base as (
    select
        strftime(f.flight_date, '%Y-%m')                                  as year_month,
        f.carrier_code,
        c.carrier_name,
        c.carrier_type,
        count(*)                                                          as flights,
        round(100 * avg(case when f.is_completed then 1 - cast(f.is_arr_delayed as int) end), 2) as on_time_pct,
        round(avg(case when f.is_completed then f.arr_delay_min end), 2)  as avg_arr_delay_min,
        round(100 * avg(cast(f.is_cancelled as int)), 2)                  as cancellation_pct,
        round(sum(f.carrier_delay_min) / 60, 0)                           as carrier_delay_hours,
        round(sum(f.late_aircraft_delay_min) / 60, 0)                     as late_aircraft_delay_hours
    from {{ ref('fct_flights') }} f
    join {{ ref('dim_carrier') }} c using (carrier_code)
    group by all
)
select
    *,
    rank() over (partition by year_month order by on_time_pct desc)       as on_time_rank
from base
