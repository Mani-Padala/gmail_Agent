"""
session.py — In-memory conversation state for the WhatsApp bot.

Since this is a single-user personal bot, a simple dict is sufficient.
State persists as long as the server is running.
If the server restarts mid-conversation, state resets cleanly.
"""

# Single global session — one user, one state at a time
_session = {
    "active_flow": None,       # "agent" | "cleanup" | None
    "pending_deletion": [],    # list of gmail_id strings awaiting yes/no
    "cleanup_service": None,   # authenticated Gmail service for cleanup batches
    "cleanup_page_token": None,# pagination token for next cleanup batch
    "cleanup_batch_number": 0, # current batch number
    "cleanup_totals": {        # running totals across cleanup batches
        "processed": 0,
        "deleted": 0,
        "kept": 0,
        "skipped": 0
    },
    "last_classify_result": None  # last batch classify result for cleanup
}


def get_session():
    return _session


def set_flow(flow_name):
    """Set the active conversation flow. flow_name: 'agent' | 'cleanup' | None"""
    _session["active_flow"] = flow_name


def get_flow():
    """Returns the current active flow or None."""
    return _session["active_flow"]


def set_pending_deletion(gmail_ids):
    """Store gmail_ids awaiting user confirmation."""
    _session["pending_deletion"] = gmail_ids


def get_pending_deletion():
    """Returns list of gmail_ids pending deletion."""
    return _session["pending_deletion"]


def clear_pending_deletion():
    _session["pending_deletion"] = []


def set_cleanup_state(service, page_token, batch_number, last_classify_result):
    """Store cleanup pagination state between WhatsApp messages."""
    _session["cleanup_service"] = service
    _session["cleanup_page_token"] = page_token
    _session["cleanup_batch_number"] = batch_number
    _session["last_classify_result"] = last_classify_result


def get_cleanup_state():
    return {
        "service": _session["cleanup_service"],
        "page_token": _session["cleanup_page_token"],
        "batch_number": _session["cleanup_batch_number"],
        "last_classify_result": _session["last_classify_result"]
    }


def update_cleanup_totals(kept=0, deleted=0, skipped=0, processed=0):
    _session["cleanup_totals"]["kept"] += kept
    _session["cleanup_totals"]["deleted"] += deleted
    _session["cleanup_totals"]["skipped"] += skipped
    _session["cleanup_totals"]["processed"] += processed


def get_cleanup_totals():
    return _session["cleanup_totals"]


def reset_cleanup():
    """Clear all cleanup state after session ends."""
    _session["cleanup_service"] = None
    _session["cleanup_page_token"] = None
    _session["cleanup_batch_number"] = 0
    _session["last_classify_result"] = None
    _session["cleanup_totals"] = {
        "processed": 0,
        "deleted": 0,
        "kept": 0,
        "skipped": 0
    }


def reset_session():
    """Full reset — called when flow ends or on error."""
    _session["active_flow"] = None
    _session["pending_deletion"] = []
    reset_cleanup()
