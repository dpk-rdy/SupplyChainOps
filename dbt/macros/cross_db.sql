{# ------------------------------------------------------------------------
   Cross-database helpers. Every model is written once and runs unchanged on
   DuckDB (dev/CI) and BigQuery (prod); the differences live here.
   ------------------------------------------------------------------------ #}

{% macro days_between(start_ts, end_ts) -%}
    {%- if target.type == 'bigquery' -%}
        (timestamp_diff({{ end_ts }}, {{ start_ts }}, second) / 86400.0)
    {%- else -%}
        (date_diff('second', {{ start_ts }}, {{ end_ts }}) / 86400.0)
    {%- endif -%}
{%- endmacro %}

{% macro hours_between(start_ts, end_ts) -%}
    {%- if target.type == 'bigquery' -%}
        (timestamp_diff({{ end_ts }}, {{ start_ts }}, second) / 3600.0)
    {%- else -%}
        (date_diff('second', {{ start_ts }}, {{ end_ts }}) / 3600.0)
    {%- endif -%}
{%- endmacro %}

{% macro to_date(ts) -%}
    {%- if target.type == 'bigquery' -%}
        date({{ ts }})
    {%- else -%}
        cast({{ ts }} as date)
    {%- endif -%}
{%- endmacro %}

{% macro week_start(date_expr) -%}
    {%- if target.type == 'bigquery' -%}
        date_trunc({{ date_expr }}, week(monday))
    {%- else -%}
        cast(date_trunc('week', {{ date_expr }}) as date)
    {%- endif -%}
{%- endmacro %}

{% macro month_start(date_expr) -%}
    {%- if target.type == 'bigquery' -%}
        date_trunc({{ date_expr }}, month)
    {%- else -%}
        cast(date_trunc('month', {{ date_expr }}) as date)
    {%- endif -%}
{%- endmacro %}

{% macro safe_divide(numerator, denominator) -%}
    {%- if target.type == 'bigquery' -%}
        safe_divide({{ numerator }}, {{ denominator }})
    {%- else -%}
        (case when {{ denominator }} = 0 or {{ denominator }} is null then null else {{ numerator }} / {{ denominator }} end)
    {%- endif -%}
{%- endmacro %}

{% macro iso_day_of_week(date_expr) -%}
    {%- if target.type == 'bigquery' -%}
        (mod(extract(dayofweek from {{ date_expr }}) + 5, 7) + 1)
    {%- else -%}
        isodow({{ date_expr }})
    {%- endif -%}
{%- endmacro %}

{% macro median_of(expr) -%}
    {%- if target.type == 'bigquery' -%}
        approx_quantiles({{ expr }}, 2)[offset(1)]
    {%- else -%}
        median({{ expr }})
    {%- endif -%}
{%- endmacro %}

{% macro date_spine(start_date, end_date) -%}
    {%- if target.type == 'bigquery' -%}
        select date_day from unnest(generate_date_array('{{ start_date }}', '{{ end_date }}')) as date_day
    {%- else -%}
        select cast(unnest(generate_series(date '{{ start_date }}', date '{{ end_date }}', interval 1 day)) as date) as date_day
    {%- endif -%}
{%- endmacro %}

{% macro surrogate_key(columns) -%}
    {%- set parts = [] -%}
    {%- for col in columns -%}
        {%- do parts.append("coalesce(cast(" ~ col ~ " as " ~ dbt.type_string() ~ "), '')") -%}
    {%- endfor -%}
    {%- if target.type == 'bigquery' -%}
        to_hex(md5(concat({{ parts | join(", '|', ") }})))
    {%- else -%}
        md5(concat({{ parts | join(", '|', ") }}))
    {%- endif -%}
{%- endmacro %}

{# Great-circle distance in km between two lat/lng pairs (degrees). #}
{% macro haversine_km(lat1, lng1, lat2, lng2) -%}
    (6371.0 * acos(least(1.0, greatest(-1.0,
        cos({{ lat1 }} * acos(-1) / 180) * cos({{ lat2 }} * acos(-1) / 180)
            * cos(({{ lng2 }} - {{ lng1 }}) * acos(-1) / 180)
        + sin({{ lat1 }} * acos(-1) / 180) * sin({{ lat2 }} * acos(-1) / 180)
    ))))
{%- endmacro %}

{% macro bool_to_int(expr) -%}
    (case when {{ expr }} then 1 else 0 end)
{%- endmacro %}
