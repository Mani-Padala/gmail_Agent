import sys
from agent.gmail_client import authenticate_gmail, fetch_emails, delete_email
from agent.classifier import classify_email, apply_guardrails, create_usage_tracker, print_usage_summary
from agent.database import (initialise_db, initialise_runs_table,
                             is_already_processed, save_classification,
                             get_pending_deletions, update_approval_status,
                             get_summary, get_last_run_timestamp, save_run)


def run_agent_preview():
    """
    Stage 1: Fetch and classify new emails since last run.
    Saves classifications to DB with user_approval='pending' for spam.
    Returns a structured result for the WhatsApp layer to present to user.

    Returns:
    {
        "status": "ok" | "error",
        "fetched": int,
        "skipped": int,
        "kept": int,
        "pending_deletion": [
            {
                "gmail_id": str,
                "subject": str,
                "sender": str,
                "flag": str,
                "reason": str
            }
        ],
        "usage": { "calls": int, "input_tokens": int, "output_tokens": int },
        "error": str | None
    }
    """
    initialise_db()
    initialise_runs_table()

    last_run = get_last_run_timestamp()

    try:
        service = authenticate_gmail()
    except Exception as e:
        return {"status": "error", "error": f"Gmail connection failed: {e}"}

    try:
        emails = fetch_emails(service, max_results=500, after_date=last_run)
    except Exception as e:
        return {"status": "error", "error": f"Email fetch failed: {e}"}

    usage = create_usage_tracker()
    skipped = 0
    kept = []
    pending_deletion = []

    for email in emails:
        if is_already_processed(email['id']):
            skipped += 1
            continue

        try:
            classification = classify_email(email, usage)
            classification = apply_guardrails(email, classification, usage)
        except Exception as e:
            print(f"Classification failed: {email['subject'][:50]} - {e}")
            continue

        try:
            save_classification(email, classification)
        except Exception as e:
            print(f"Failed to save: {email['subject'][:50]} - {e}")
            continue

        if classification['decision'] == 'delete':
            pending_deletion.append({
                "gmail_id": email['id'],
                "subject": email['subject'],
                "sender": email['sender'],
                "flag": classification['flag'],
                "reason": classification['reason']
            })
        else:
            kept.append(email['id'])

    return {
        "status": "ok",
        "last_run": last_run,
        "fetched": len(emails),
        "skipped": skipped,
        "kept": len(kept),
        "pending_deletion": pending_deletion,
        "usage": usage,
        "error": None
    }


def run_agent_execute(gmail_ids):
    """
    Stage 2: Delete emails that the user approved via WhatsApp.
    Updates user_approval to 'approved' in DB after successful deletion.
    Call this only after user confirms via WhatsApp.

    Args:
        gmail_ids: list of gmail_id strings to delete

    Returns:
    {
        "status": "ok" | "error",
        "deleted": int,
        "failed": int,
        "error": str | None
    }
    """
    if not gmail_ids:
        return {"status": "ok", "deleted": 0, "failed": 0, "error": None}

    try:
        service = authenticate_gmail()
    except Exception as e:
        return {"status": "error", "deleted": 0, "failed": 0, "error": f"Gmail connection failed: {e}"}

    success_ids = []
    failed_count = 0

    for gmail_id in gmail_ids:
        success = delete_email(service, gmail_id)
        if success:
            success_ids.append(gmail_id)
        else:
            failed_count += 1

    # Mark successfully deleted emails as approved in DB
    if success_ids:
        update_approval_status(success_ids, 'approved')

    # Save run record
    save_run(
        emails_processed=len(gmail_ids),
        emails_deleted=len(success_ids)
    )

    return {
        "status": "ok",
        "deleted": len(success_ids),
        "failed": failed_count,
        "error": None
    }


def run_agent_skip():
    """
    Called when user says NO on WhatsApp.
    Marks all pending deletions as skipped so they don't resurface next run.
    """
    pending = get_pending_deletions()
    ids = [row['gmail_id'] for row in pending]
    update_approval_status(ids, 'skipped')

    return {
        "status": "ok",
        "skipped_count": len(ids)
    }


if __name__ == "__main__":
    # Local test — simulates what the WhatsApp layer will do
    print("=" * 60)
    print("Stage 1: Preview")
    print("=" * 60)

    result = run_agent_preview()

    if result["status"] == "error":
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"Fetched:  {result['fetched']}")
    print(f"Skipped:  {result['skipped']}")
    print(f"Kept:     {result['kept']}")
    print(f"To delete: {len(result['pending_deletion'])}")

    if result['pending_deletion']:
        print("\nEmails pending deletion:")
        for item in result['pending_deletion']:
            print(f"  - {item['subject'][:60]}")
            print(f"    From:   {item['sender'][:60]}")
            print(f"    Reason: {item['reason']}")

        confirm = input(f"\nDelete these {len(result['pending_deletion'])} emails? (yes/no): ").strip().lower()

        if confirm == "yes":
            print("\n" + "=" * 60)
            print("Stage 2: Execute")
            print("=" * 60)

            ids_to_delete = [item['gmail_id'] for item in result['pending_deletion']]
            exec_result = run_agent_execute(ids_to_delete)

            print(f"Deleted: {exec_result['deleted']}")
            print(f"Failed:  {exec_result['failed']}")
        else:
            run_agent_skip()
            print("Deletion skipped. Emails marked as skipped in DB.")
    else:
        print("\nNo emails marked for deletion.")
        save_run(
            emails_processed=result['kept'],
            emails_deleted=0
        )

    print_usage_summary(result['usage'])
