-- Clean, typed and de-duplicated flights. One row per flight.
with source as (
    select * from {{ source('bronze', 'flights') }}
),

typed as (
    select
        cast(flight_date as date)                         as flight_date,
        upper(trim(carrier_code))                         as carrier_code,
        trim(flight_number)                               as flight_number,
        nullif(trim(tail_number), '')                     as tail_number,
        upper(trim(origin))                               as origin,
        origin_city,
        origin_state,
        upper(trim(dest))                                 as dest,
        dest_city,
        dest_state,
        cast(crs_dep_time as integer)                     as crs_dep_time,
        cast(dep_time as integer)                         as dep_time,
        cast(crs_arr_time as integer)                     as crs_arr_time,
        cast(arr_time as integer)                         as arr_time,
        cast(dep_delay as double)                         as dep_delay_min,
        cast(arr_delay as double)                         as arr_delay_min,
        cast(taxi_out as double)                          as taxi_out_min,
        cast(taxi_in as double)                           as taxi_in_min,
        cast(crs_elapsed_time as double)                  as scheduled_duration_min,
        cast(actual_elapsed_time as double)               as actual_duration_min,
        cast(air_time as double)                          as air_time_min,
        cast(distance as double)                          as distance_miles,
        coalesce(cast(cancelled as double), 0) = 1        as is_cancelled,
        coalesce(cast(diverted as double), 0) = 1         as is_diverted,
        nullif(trim(cancellation_code), '')               as cancellation_code,
        cast(carrier_delay as double)                     as carrier_delay_min,
        cast(weather_delay as double)                     as weather_delay_min,
        cast(nas_delay as double)                         as nas_delay_min,
        cast(security_delay as double)                    as security_delay_min,
        cast(late_aircraft_delay as double)               as late_aircraft_delay_min,
        _ingested_at
    from source
),

enriched as (
    select
        *,
        {{ hhmm_hour('crs_dep_time') }}                   as scheduled_dep_hour,
        make_timestamp(year(flight_date), month(flight_date), day(flight_date),
                       {{ hhmm_hour('crs_dep_time') }}, {{ hhmm_minute('crs_dep_time') }}, 0)
                                                          as scheduled_departure_at,
        md5(concat_ws('|', flight_date, carrier_code, flight_number, origin, dest, crs_dep_time))
                                                          as flight_id
    from typed
    where flight_date is not null
)

select *
from enriched
-- the source has no primary key: keep one row per natural key (latest ingestion wins)
qualify row_number() over (partition by flight_id order by _ingested_at desc) = 1
