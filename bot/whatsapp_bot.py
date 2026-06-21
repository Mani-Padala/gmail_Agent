import os
import threading
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv

from bot.router import classify_intent
from bot.session import (
    get_flow, set_flow, reset_session,
    set_pending_deletion, get_pending_deletion, clear_pending_deletion,
    set_cleanup_state, get_cleanup_state,
    update_cleanup_totals, get_cleanup_totals, reset_cleanup
)
from main import run_agent_preview, run_agent_execute, run_agent_skip
from agent.database import get_summary, get_pending_deletions, update_approval_status
from agent.gmail_client import authenticate_gmail
from tools.cleanup import fetch_email_batch, classify_batch, execute_batch_deletion

load_dotenv()

app = FastAPI()

# Twilio client for sending messages
twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # whatsapp:+14155238886
YOUR_WHATSAPP_NUMBER = os.getenv("YOUR_WHATSAPP_NUMBER")      # whatsapp:+91xxxxxxxxxx


# ── Helpers ──────────────────────────────────────────────────────────────────

def send_message(text):
    """Send a WhatsApp message back to you via Twilio."""
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=YOUR_WHATSAPP_NUMBER,
        body=text
    )


def format_deletion_list(items, max_items=10):
    """
    Formats a list of emails for WhatsApp display.
    Caps at max_items to avoid message size limits.
    """
    lines = []
    shown = items[:max_items]

    for i, item in enumerate(shown, 1):
        subject = item.get("subject", "No subject")[:50]
        sender = item.get("sender", "Unknown")[:40]
        reason = item.get("reason", "")[:60]
        lines.append(f"{i}. {subject}\n   From: {sender}\n   Why: {reason}")

    if len(items) > max_items:
        lines.append(f"...and {len(items) - max_items} more.")

    return "\n\n".join(lines)


def format_summary():
    """Formats the DB summary for WhatsApp."""
    summary = get_summary()
    if not summary:
        return "No emails processed yet."

    lines = ["📊 *Email Summary*\n"]
    total = 0
    for row in summary:
        emoji = {"spam": "🗑️", "job": "💼", "news": "📰", "alert": "🔔"}.get(row["flag"], "📧")
        lines.append(f"{emoji} {row['flag'].upper()} → {row['decision']}: {row['count']} emails")
        total += row["count"]

    lines.append(f"\n📬 Total tracked: {total}")
    return "\n".join(lines)


# ── Flow handlers ─────────────────────────────────────────────────────────────

def handle_run_agent():
    """
    Runs agent preview in a background thread.
    Sends WhatsApp message when stop.
    """
    send_message("🔄 Running email check... I'll message you when stop.")
    set_flow("agent")

    def _run():
        try:
            result = run_agent_preview()

            if result["status"] == "error":
                send_message(f"❌ Error: {result['error']}")
                reset_session()
                return

            pending = result["pending_deletion"]
            usage = result["usage"]
            cost = round(
                (usage["input_tokens"] / 1_000_000) * 1.00 +
                (usage["output_tokens"] / 1_000_000) * 5.00,
                4
            )

            summary_msg = (
                f"✅ *Email Check Complete*\n\n"
                f"📥 Fetched: {result['fetched']}\n"
                f"⏭️ Already seen: {result['skipped']}\n"
                f"✉️ Kept: {result['kept']}\n"
                f"🗑️ To delete: {len(pending)}\n"
                f"💰 Cost: ${cost}"
            )
            send_message(summary_msg)

            if not pending:
                send_message("✨ Inbox is clean. Nothing to delete.")
                reset_session()
                return

            # Store pending gmail_ids in session
            set_pending_deletion([item["gmail_id"] for item in pending])

            # Send deletion list
            deletion_msg = (
                f"🗑️ *Emails marked for deletion:*\n\n"
                f"{format_deletion_list(pending)}\n\n"
                f"Reply *yes* to delete all, *no* to skip."
            )
            send_message(deletion_msg)

        except Exception as e:
            send_message(f"❌ Agent failed: {e}")
            reset_session()

    threading.Thread(target=_run, daemon=True).start()


def handle_cleanup_start():
    """
    Starts the cleanup flow — authenticates Gmail and processes batch 1.
    """
    send_message("🧹 Starting inbox cleanup... Processing batch 1 of 50 emails.")
    set_flow("cleanup")

    def _run():
        try:
            service = authenticate_gmail()
            messages, page_token = fetch_email_batch(service, page_token=None)

            if not messages:
                send_message("✨ Inbox is already empty.")
                reset_session()
                return

            classify_result = classify_batch(service, messages)
            batch_number = 1

            update_cleanup_totals(
                kept=classify_result["kept"],
                skipped=classify_result["skipped"],
                processed=len(messages)
            )

            # Save state for when user replies
            set_cleanup_state(service, page_token, batch_number, classify_result)

            _send_cleanup_batch_message(batch_number, classify_result)

        except Exception as e:
            send_message(f"❌ Cleanup failed: {e}")
            reset_session()

    threading.Thread(target=_run, daemon=True).start()


def _send_cleanup_batch_message(batch_number, classify_result):
    """Formats and sends the cleanup batch prompt to WhatsApp."""
    to_delete = classify_result["to_delete"]
    kept = classify_result["kept"]
    skipped = classify_result["skipped"]

    if not to_delete:
        send_message(
            f"📦 *Batch {batch_number}* — Nothing to delete\n"
            f"✉️ Kept: {kept} | ⏭️ Skipped: {skipped}\n\n"
            f"Reply *next* to continue or *stop* to end cleanup."
        )
    else:
        deletion_msg = (
            f"📦 *Batch {batch_number}*\n"
            f"🗑️ To delete: {len(to_delete)} | ✉️ Kept: {kept} | ⏭️ Skipped: {skipped}\n\n"
            f"{format_deletion_list(to_delete)}\n\n"
            f"Reply *yes* to delete, *next* to skip, *stop* to end cleanup."
        )
        send_message(deletion_msg)


def handle_next_cleanup_batch():
    """Fetches and classifies the next cleanup batch."""
    state = get_cleanup_state()
    service = state["service"]
    page_token = state["page_token"]
    batch_number = state["batch_number"]

    def _run():
        try:
            if not page_token:
                # No more pages — cleanup complete
                _finish_cleanup()
                return

            next_batch_number = batch_number + 1
            send_message(f"⏳ Processing batch {next_batch_number}...")

            messages, next_page_token = fetch_email_batch(service, page_token)

            if not messages:
                _finish_cleanup()
                return

            classify_result = classify_batch(service, messages)

            update_cleanup_totals(
                kept=classify_result["kept"],
                skipped=classify_result["skipped"],
                processed=len(messages)
            )

            set_cleanup_state(service, next_page_token, next_batch_number, classify_result)
            _send_cleanup_batch_message(next_batch_number, classify_result)

        except Exception as e:
            send_message(f"❌ Batch processing failed: {e}")
            reset_session()

    threading.Thread(target=_run, daemon=True).start()


def _finish_cleanup():
    """Called when all batches are stop or user stops."""
    totals = get_cleanup_totals()
    msg = (
        f"🏁 *Cleanup Complete*\n\n"
        f"📬 Processed: {totals['processed']}\n"
        f"⏭️ Already seen: {totals['skipped']}\n"
        f"✉️ Kept: {totals['kept']}\n"
        f"🗑️ Deleted: {totals['deleted']}"
    )
    send_message(msg)
    reset_session()


# ── Confirmation handler ──────────────────────────────────────────────────────

def handle_confirm(value):
    """
    Routes confirmation responses based on active flow.
    value: "yes" | "no" | "next" | "stop"
    """
    flow = get_flow()

    # ── Agent flow confirmation ──
    if flow == "agent":
        if value == "yes":
            gmail_ids = get_pending_deletion()
            if not gmail_ids:
                send_message("⚠️ No pending deletions found.")
                reset_session()
                return

            send_message(f"🗑️ Deleting {len(gmail_ids)} emails...")

            def _delete():
                try:
                    result = run_agent_execute(gmail_ids)
                    send_message(
                        f"✅ stop!\n"
                        f"🗑️ Deleted: {result['deleted']}\n"
                        f"❌ Failed: {result['failed']}"
                    )
                except Exception as e:
                    send_message(f"❌ Deletion failed: {e}")
                finally:
                    reset_session()

            threading.Thread(target=_delete, daemon=True).start()

        elif value == "no":
            run_agent_skip()
            send_message("⏭️ Skipped. Emails marked as skipped in DB.")
            reset_session()

        else:
            send_message("⚠️ Please reply *yes* to delete or *no* to skip.")

    # ── Cleanup flow confirmation ──
    elif flow == "cleanup":
        state = get_cleanup_state()
        classify_result = state["last_classify_result"]

        if value == "stop":
            send_message("🛑 Cleanup stopped.")
            _finish_cleanup()

        elif value == "yes":
            to_delete = classify_result.get("to_delete", []) if classify_result else []
            if to_delete:
                ids = [item["gmail_id"] for item in to_delete]

                def _delete_and_continue():
                    try:
                        service = state["service"]
                        result = execute_batch_deletion(service, ids)
                        update_cleanup_totals(deleted=result["deleted"])
                        send_message(f"✅ Deleted {result['deleted']} emails.")
                    except Exception as e:
                        send_message(f"❌ Deletion failed: {e}")
                    finally:
                        handle_next_cleanup_batch()

                threading.Thread(target=_delete_and_continue, daemon=True).start()
            else:
                handle_next_cleanup_batch()

        elif value == "next":
            handle_next_cleanup_batch()

        else:
            send_message("⚠️ Reply *yes* to delete, *next* to skip, *stop* to end.")

    else:
        send_message("⚠️ No active task. Send *run the agent* or *clean up my inbox* to start.")


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request, Body: str = Form(...), From: str = Form(...)):
    """
    Twilio calls this endpoint when you send a WhatsApp message.
    Twilio sends form data — Body is message text, From is your WhatsApp number.
    """
    # Security check — only respond to your own number
    if From != YOUR_WHATSAPP_NUMBER:
        return ""

    message_text = Body.strip()
    print(f"Received: '{message_text}'")

    # Classify intent
    intent = classify_intent(message_text)
    action = intent["action"]
    value = intent.get("value")

    print(f"Intent: {action} | Value: {value}")

    # Route to handler
    if action == "run_agent":
        if get_flow():
            send_message("⚠️ Another task is already running. Please wait or send *stop*.")
        else:
            handle_run_agent()

    elif action == "cleanup":
        if get_flow():
            send_message("⚠️ Another task is already running. Please wait or send *stop*.")
        else:
            handle_cleanup_start()

    elif action == "summary":
        send_message(format_summary())

    elif action == "confirm":
        handle_confirm(value)

    elif action == "reset":
        reset_session()
        send_message("🔄 Session reset. You can start a new task now.")

    elif action == "unknown":
        send_message(
            "🤖 I didn't understand that. Here's what I can do:\n\n"
            "• *run the agent* — check and classify new emails\n"
            "• *clean up my inbox* — full inbox cleanup\n"
            "• *summary* — show email statistics\n"
            "• *yes / no / next / stop* — respond to prompts\n"
            "• *reset* — clear stuck session"
        )

    # Twilio expects an empty 200 response — actual reply sent via send_message()
    return ""


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.whatsapp_bot:app", host="0.0.0.0", port=8000, reload=True)