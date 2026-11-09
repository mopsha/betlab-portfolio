from betlab import plan


def test_page_todos_keep_their_ids_order_and_state():
    r = plan.todo_row("c-nba", {"owner": "claude", "title": " NBA ", "detail": "x", "due": "2026-10-17", "status": "open",
                                "done_at": None, "order": 10.0, "added_by": "claude", "created_at": "2026-09-23T21:40:00Z"})
    assert (r["id"], r["owner"], r["title"], r["ord"], r["status"], r["due"]) == ("c-nba", "claude", "NBA", 10, "open", "2026-10-17")
    page = plan.todo_row("ppeb", {"owner": "claude", "title": "Skip the state picker", "status": "done",
                                  "done_at": "2026-10-01T15:00:00Z", "order": 1790818125882, "added_by": "page"})
    assert page["status"] == "done" and page["done_at"] is not None and page["added_by"] == "page"


def test_odd_owner_or_missing_title_still_imports():
    r = plan.todo_row("x", {"owner": "mike"})
    assert r["owner"] == "you" and r["title"] == "(untitled)" and r["created_at"] is not None


def test_review_rows_and_slugs():
    r = plan.review_row("2026-09-29-week-1", {"title": "Week 1", "body": "b", "created_at": "2026-09-29T15:00:00Z"})
    assert (r["id"], r["title"], r["body"]) == ("2026-09-29-week-1", "Week 1", "b")
    assert plan.slug("Weekly review #2: props & CLV!") == "weekly-review-2-props-clv"
