import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ROUTER_PROMPT = """
You are an intent classifier for a personal Gmail agent controlled via WhatsApp.

The user sends natural language messages to control their Gmail agent.
Your job is to classify the intent and return ONLY JSON with no preamble or markdown.

Possible intents:

1. run_agent — user wants to run the regular email check and classify new emails
   Examples: "run the agent", "check my emails", "run email check", 
             "scan my inbox", "check new emails", "run it"

2. cleanup — user wants to run the full inbox cleanup (one-time deep clean)
   Examples: "clean up my inbox", "run cleanup", "do a full cleanup",
             "clean my mailbox", "deep clean"

3. summary — user wants a summary of what the agent has processed so far
   Examples: "show summary", "what have you processed", "give me stats",
             "how many emails", "show me the numbers"

4. confirm — user is responding to a pending confirmation prompt
   Examples: "yes", "no", "next", "stop", "yeah", "nope", "yep", "go ahead",
             "skip", "cancel", "delete them", "don't delete"

5. reset — user wants to clear a stuck session and start fresh
   Examples: "reset", "start over", "cancel everything", "clear session"

6. unknown — message doesn't match any known intent
   Examples: "hello", "what can you do", random text

For confirm intent, map the value:
- "yes" for: yes, yeah, yep, go ahead, delete them, confirm, ok, sure, do it
- "no" for: no, nope, don't delete, skip, cancel (when no active cleanup batch)
- "next" for: next, skip this batch, next batch
- "stop" for: stop, cancel cleanup, abort, quit, end

Respond ONLY in JSON:
{
    "action": "run_agent | cleanup | summary | confirm | reset | unknown",
    "value": "yes | no | next | stop | null",
    "confidence": "high | low"
}

value is only set when action is "confirm", otherwise null.
"""


def classify_intent(message_text):
    """
    Takes raw WhatsApp message text and returns structured intent.

    Returns:
    {
        "action": "run_agent" | "cleanup" | "summary" | "confirm" | "unknown",
        "value": "yes" | "no" | "next" | "stop" | None,
        "confidence": "high" | "low"
    }
    """
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=64,
            system=ROUTER_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Classify this message: {message_text}"
                }
            ]
        )

        response_text = response.content[0].text.strip()

        # Strip markdown if model adds it
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        result = json.loads(response_text)

        # Normalise value field
        if result.get("action") != "confirm":
            result["value"] = None

        return result

    except Exception as e:
        print(f"Router error: {e}")
        return {
            "action": "unknown",
            "value": None,
            "confidence": "low"
        }


if __name__ == "__main__":
    # Quick test
    test_messages = [
        "run the agent",
        "clean up my inbox",
        "show me the summary",
        "yes",
        "no",
        "next batch",
        "stop",
        "hello there",
        "check my emails please",
        "yeah go ahead delete them",
    ]

    print("Intent Router Test")
    print("=" * 50)
    for msg in test_messages:
        result = classify_intent(msg)
        print(f"Input:  '{msg}'")
        print(f"Intent: {result['action']} | value: {result['value']} | confidence: {result['confidence']}")
        print("-" * 50)