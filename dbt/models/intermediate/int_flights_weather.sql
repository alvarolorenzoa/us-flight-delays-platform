-- Attach the weather observed at the origin airport in the scheduled departure hour.
-- Only hub airports have weather; other origins keep null weather columns.
with flights as (
    select * from {{ ref('stg_flights') }}
),

weather as (
    select * from {{ ref('stg_weather') }}
)

select
    f.*,
    w.temperature_c,
    w.precipitation_mm,
    w.snowfall_cm,
    w.wind_speed_kmh,
    w.wind_gusts_kmh,
    w.cloud_cover_pct,
    w.weather_hour is not null                         as has_weather,
    case
        when w.weather_hour is null         then null
        when w.snowfall_cm > 0              then 'Snow'
        when w.precipitation_mm >= 2.5      then 'Heavy rain'
        when w.precipitation_mm > 0         then 'Light rain'
        when w.wind_gusts_kmh >= 50         then 'Strong wind'
        else 'Dry & calm'
    end                                                as weather_condition
from flights f
left join weather w
       on w.airport_code = f.origin
      and w.weather_hour = date_trunc('hour', f.scheduled_departure_at)
