-- A cancelled flight cannot have an arrival delay or be counted as delayed on arrival.
select flight_id
from {{ ref('fct_flights') }}
where is_cancelled and (arr_delay_min is not null or is_arr_delayed is not null)
