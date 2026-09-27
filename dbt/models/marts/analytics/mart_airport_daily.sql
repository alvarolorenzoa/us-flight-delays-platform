-- Daily departure performance per origin airport (with daily weather for hubs).
select
    f.flight_date,
    f.origin_code                                                         as airport_code,
    a.airport_name,
    a.city_name,
    a.state,
    a.latitude,
    a.longitude,
    a.is_hub,
    count(*)                                                              as departures,
    round(100 * avg(cast(f.is_dep_delayed as int)), 2)                    as dep_delay_pct,
    round(avg(f.dep_delay_min), 2)                                        as avg_dep_delay_min,
    round(100 * avg(cast(f.is_cancelled as int)), 2)                      as cancellation_pct,
    round(avg(f.taxi_out_min), 2)                                         as avg_taxi_out_min,
    round(max(f.precipitation_mm), 2)                                     as max_hourly_precip_mm,
    round(max(f.snowfall_cm), 2)                                          as max_hourly_snow_cm,
    round(max(f.wind_gusts_kmh), 1)                                       as max_wind_gust_kmh
from {{ ref('fct_flights') }} f
join {{ ref('dim_airport') }} a on a.airport_code = f.origin_code
group by all
