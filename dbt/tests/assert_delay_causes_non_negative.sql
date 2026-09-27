-- Delay-cause minutes are durations: they can never be negative.
select flight_id
from {{ ref('fct_flights') }}
where least(carrier_delay_min, weather_delay_min, nas_delay_min, security_delay_min, late_aircraft_delay_min) < 0
