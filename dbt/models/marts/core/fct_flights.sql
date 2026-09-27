-- Flight-level fact table (grain: one scheduled flight).
select
    flight_id,
    flight_date,
    cast(strftime(flight_date, '%Y%m%d') as integer)       as date_key,
    carrier_code,
    flight_number,
    tail_number,
    origin                                                  as origin_code,
    dest                                                    as dest_code,
    origin || '-' || dest                                   as route,
    scheduled_departure_at,
    scheduled_dep_hour,
    distance_miles,
    -- outcome
    is_cancelled,
    is_diverted,
    case cancellation_code
        when 'A' then 'Carrier' when 'B' then 'Weather'
        when 'C' then 'National Air System' when 'D' then 'Security'
    end                                                     as cancellation_reason,
    not is_cancelled and not is_diverted                    as is_completed,
    -- DOT definition: a flight is on time if it arrives less than 15 minutes late
    case when is_cancelled or is_diverted then null
         else arr_delay_min >= 15 end                       as is_arr_delayed,
    case when is_cancelled then null
         else dep_delay_min >= 15 end                       as is_dep_delayed,
    dep_delay_min,
    arr_delay_min,
    taxi_out_min,
    taxi_in_min,
    air_time_min,
    -- delay causes (minutes, only reported for flights arriving 15+ min late)
    coalesce(carrier_delay_min, 0)                          as carrier_delay_min,
    coalesce(weather_delay_min, 0)                          as weather_delay_min,
    coalesce(nas_delay_min, 0)                              as nas_delay_min,
    coalesce(security_delay_min, 0)                         as security_delay_min,
    coalesce(late_aircraft_delay_min, 0)                    as late_aircraft_delay_min,
    -- weather at origin (hubs only)
    has_weather,
    weather_condition,
    temperature_c,
    precipitation_mm,
    snowfall_cm,
    wind_gusts_kmh
from {{ ref('int_flights_weather') }}
