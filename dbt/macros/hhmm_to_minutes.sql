{# BTS times are local hhmm integers (e.g. 1905, 5 = 00:05, 2400 = midnight) #}
{% macro hhmm_hour(col) -%}
    case when {{ col }} is null then null when {{ col }} >= 2400 then 0 else cast(floor({{ col }} / 100) as integer) end
{%- endmacro %}
{% macro hhmm_minute(col) -%}
    case when {{ col }} is null then null when {{ col }} >= 2400 then 0 else cast({{ col }} % 100 as integer) end
{%- endmacro %}
