-- Row-count reconciliation: every de-duplicated staging flight reaches the fact table.
select 1
from (select count(*) n from {{ ref('stg_flights') }}) s,
     (select count(*) n from {{ ref('fct_flights') }}) f
where s.n <> f.n
