-- Where do delay minutes come from? (unpivoted for charting)
with monthly as (
    select
        strftime(flight_date, '%Y-%m')      as year_month,
        sum(carrier_delay_min)              as "Carrier",
        sum(weather_delay_min)              as "Weather",
        sum(nas_delay_min)                  as "National Air System",
        sum(security_delay_min)             as "Security",
        sum(late_aircraft_delay_min)        as "Late aircraft"
    from {{ ref('fct_flights') }}
    group by 1
),
long as (
    unpivot monthly on "Carrier", "Weather", "National Air System", "Security", "Late aircraft"
    into name cause value delay_minutes
)
select
    year_month,
    cause,
    round(delay_minutes / 60, 0)                                              as delay_hours,
    round(100 * delay_minutes / nullif(sum(delay_minutes) over (partition by year_month), 0), 2) as share_pct
from long
