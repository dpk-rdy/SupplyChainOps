with reviews as (
    select
        *,
        row_number() over (partition by order_id order by review_answered_at desc, review_created_at desc) as rn
    from {{ ref('stg_order_reviews') }}
)

select
    order_id,
    review_id,
    review_score,
    review_created_at,
    review_answered_at,
    review_comment_message is not null as has_comment
from reviews
where rn = 1
