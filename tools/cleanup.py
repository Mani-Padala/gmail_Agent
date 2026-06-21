import sys
import time
import os
from agent.gmail_client import authenticate_gmail, fetch_email_details, delete_email
from agent.classifier import classify_email, apply_guardrails
from agent.database import (initialise_db, is_already_processed,
                             save_classification, get_summary)

BATCH_SIZE = 50
DELAY_SECONDS = 2


def fetch_email_batch(service, page_token=None):
    """
    Fetches one page of emails from inbox.
    Returns (messages, next_page_token).
    """
    params = {
        'userId': 'me',
        'labelIds': ['INBOX'],
        'maxResults': BATCH_SIZE
    }
    if page_token:
        params['pageToken'] = page_token

    results = service.users().messages().list(**params).execute()
    messages = results.get('messages', [])
    next_page_token = results.get('nextPageToken', None)
    return messages, next_page_token


def classify_batch(service, messages):
    """
    Fetches full details and classifies a batch of messages.
    Returns a structured result for the WhatsApp layer to present.

    Returns:
    {
        "to_delete": [{ "gmail_id", "subject", "sender", "reason" }],
        "kept": int,
        "skipped": int
    }
    """
    to_delete = []
    kept = 0
    skipped = 0

    for message in messages:
        if is_already_processed(message['id']):
            skipped += 1
            continue

        try:
            email = fetch_email_details(service, message['id'])
        except Exception as e:
            print(f"Failed to fetch email: {e}")
            continue

        try:
            classification = classify_email(email)
            classification = apply_guardrails(email, classification)
            time.sleep(DELAY_SECONDS)
        except Exception as e:
            print(f"Classification failed: {email['subject'][:50]} - {e}")
            continue

        try:
            save_classification(email, classification)
        except Exception as e:
            print(f"Failed to save: {email['subject'][:50]} - {e}")
            continue

        if classification['decision'] == 'delete':
            to_delete.append({
                "gmail_id": email['id'],
                "subject": email['subject'],
                "sender": email['sender'],
                "reason": classification['reason']
            })
        else:
            kept += 1

    return {
        "to_delete": to_delete,
        "kept": kept,
        "skipped": skipped
    }


def execute_batch_deletion(service, gmail_ids):
    """
    Deletes a list of emails by gmail_id.
    Returns count of successes and failures.
    """
    success = 0
    failed = 0

    for gmail_id in gmail_ids:
        if delete_email(service, gmail_id):
            success += 1
        else:
            failed += 1

    return {"deleted": success, "failed": failed}


def run_cleanup_session(on_batch_ready, on_session_complete):
    """
    Core cleanup loop — no input() calls.
    Drives the full inbox cleanup batch by batch.

    Callbacks provided by the caller (WhatsApp layer or local test):

    on_batch_ready(batch_number, classify_result) -> "yes" | "next" | "stop"
        Called after each batch is classified.
        Caller presents the list to user and returns their response.

    on_session_complete(totals)
        Called when all batches are done or user stops.
        totals = { "processed", "deleted", "kept", "skipped" }
    """
    initialise_db()

    try:
        service = authenticate_gmail()
    except Exception as e:
        on_session_complete({"error": f"Gmail connection failed: {e}"})
        return

    totals = {
        "processed": 0,
        "deleted": 0,
        "kept": 0,
        "skipped": 0
    }

    batch_number = 0
    page_token = None

    while True:
        batch_number += 1

        try:
            messages, page_token = fetch_email_batch(service, page_token)
        except Exception as e:
            print(f"Failed to fetch batch: {e}")
            break

        if not messages:
            break

        classify_result = classify_batch(service, messages)

        totals["kept"] += classify_result["kept"]
        totals["skipped"] += classify_result["skipped"]
        totals["processed"] += len(messages)

        # Hand off to caller — WhatsApp layer or local input()
        user_response = on_batch_ready(batch_number, classify_result)

        if user_response == "stop":
            break
        elif user_response == "yes" and classify_result["to_delete"]:
            ids = [item["gmail_id"] for item in classify_result["to_delete"]]
            result = execute_batch_deletion(service, ids)
            totals["deleted"] += result["deleted"]
        # "next" — skip deletion for this batch, continue to next

        if not page_token:
            break

    on_session_complete(totals)


# ── Local test runner ────────────────────────────────────────────────────────

def _local_on_batch_ready(batch_number, classify_result):
    """Terminal callback for local testing."""
    print(f"\n--- Batch {batch_number} ---")
    print(f"To delete: {len(classify_result['to_delete'])} | "
          f"Kept: {classify_result['kept']} | "
          f"Skipped: {classify_result['skipped']}")

    if classify_result["to_delete"]:
        print("\nEmails marked for deletion:")
        for item in classify_result["to_delete"]:
            print(f"  - {item['subject'][:60]}")
            print(f"    From:   {item['sender'][:60]}")
            print(f"    Reason: {item['reason'][:60]}")

        response = input(
            "\nDelete these emails? (yes/next/stop): "
        ).strip().lower()

        if response in ("yes", "next", "stop"):
            return response
        return "next"

    return "next"


def _local_on_session_complete(totals):
    """Terminal callback for local testing."""
    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)

    if "error" in totals:
        print(f"Error: {totals['error']}")
        return

    print(f"Total processed: {totals['processed']}")
    print(f"Already seen:    {totals['skipped']}")
    print(f"Kept:            {totals['kept']}")
    print(f"Sent to trash:   {totals['deleted']}")

    print("\nOverall DB Summary:")
    summary = get_summary()
    for row in summary:
        print(f"  {row['flag']} -> {row['decision']}: {row['count']} emails")


if __name__ == "__main__":
    print("=" * 60)
    print("Gmail Agent - Initial Inbox Cleanup")
    print("=" * 60)
    print("\nWARNING: This will process your entire inbox in batches of 50.")

    confirm_start = input("\nReady to start? (yes/no): ").strip().lower()
    if confirm_start != "yes":
        print("Cleanup cancelled.")
        sys.exit(0)

    run_cleanup_session(
        on_batch_ready=_local_on_batch_ready,
        on_session_complete=_local_on_session_complete
    )
