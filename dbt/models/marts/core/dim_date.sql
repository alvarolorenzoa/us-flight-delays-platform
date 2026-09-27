with bounds as (
    select min(flight_date) as d0, max(flight_date) as d1 from {{ ref('stg_flights') }}
)
select
    cast(strftime(d, '%Y%m%d') as integer)     as date_key,
    cast(d as date)                            as full_date,
    year(d)                                    as year,
    quarter(d)                                 as quarter,
    month(d)                                   as month,
    strftime(d, '%b')                          as month_short,
    strftime(d, '%Y-%m')                       as year_month,
    isodow(d)                                  as day_of_week,
    strftime(d, '%a')                          as day_name,
    isodow(d) in (6, 7)                        as is_weekend
from bounds, generate_series(d0, d1, interval 1 day) t(d)
