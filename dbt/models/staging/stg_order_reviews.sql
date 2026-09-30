{# The raw file repeats some review_ids across orders and some orders across
   review_ids. Keep one row per (review_id, order_id), preferring the latest answer. #}
with source as (
    select * from {{ source('olist', 'olist_order_reviews') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by review_id, order_id
            order by review_answer_timestamp desc, review_creation_date desc
        ) as rn
    from source
)

select
    {{ surrogate_key(['review_id', 'order_id']) }} as review_key,
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date        as review_created_at,
    review_answer_timestamp     as review_answered_at
from deduped
where rn = 1
