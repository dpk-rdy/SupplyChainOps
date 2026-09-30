{# Custom generic tests used in schema.yml files. #}

{% test non_negative(model, column_name) %}
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} < 0
{% endtest %}

{% test between(model, column_name, min_value, max_value) %}
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}

{% test row_count_matches(model, compare_model) %}
    with a as (select count(*) as n from {{ model }}),
         b as (select count(*) as n from {{ compare_model }})
    select a.n as model_rows, b.n as compare_rows
    from a, b
    where a.n != b.n
{% endtest %}

{# Composite uniqueness without depending on dbt_utils (no package downloads in CI). #}
{% test dbt_utils_free_unique_combination(model, combination) %}
    select {{ combination | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination | join(', ') }}
    having count(*) > 1
{% endtest %}
