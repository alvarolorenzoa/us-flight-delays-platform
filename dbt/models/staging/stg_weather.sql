-- Hourly weather per hub airport, local time.
with source as (
    select * from {{ source('bronze', 'weather') }}
)

select
    upper(airport_code)                        as airport_code,
    cast(weather_time as timestamp)            as weather_hour,
    cast(temperature_2m as double)             as temperature_c,
    cast(precipitation as double)              as precipitation_mm,
    cast(snowfall as double)                   as snowfall_cm,
    cast(wind_speed_10m as double)             as wind_speed_kmh,
    cast(wind_gusts_10m as double)             as wind_gusts_kmh,
    cast(cloud_cover as double)                as cloud_cover_pct,
    cast(weather_code as integer)              as wmo_weather_code
from source
qualify row_number() over (partition by airport_code, weather_time order by _ingested_at desc) = 1
