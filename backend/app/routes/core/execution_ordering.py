def build_execution_order_clause(
    order_by: str,
    order: str,
    *,
    status_expr: str = "status",
    column_prefix: str = "",
) -> str:
    safe_order = "DESC" if order.lower() == "desc" else "ASC"
    allowed_columns = {"created_at", "started_at", "completed_at", "status"}
    safe_key = order_by if order_by in allowed_columns else "created_at"
    safe_col = f"{column_prefix}{safe_key}"
    return (
        "ORDER BY "
        f"CASE LOWER({status_expr}) "
        "WHEN 'running' THEN 0 "
        "WHEN 'queued' THEN 1 "
        "WHEN 'paused' THEN 2 "
        "WHEN 'pending' THEN 3 "
        "ELSE 4 END, "
        f"{safe_col} {safe_order}"
    )
