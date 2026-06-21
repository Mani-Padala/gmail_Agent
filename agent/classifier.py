import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Haiku 4.5 pricing per million tokens
INPUT_COST_PER_MILLION = 1.00
OUTPUT_COST_PER_MILLION = 5.00

SYSTEM_PROMPT = """
You are an email classifier for a software professional based in India
with the following profile:
- Works in software engineering and testing
- Interested in tech learning and career growth
- Personal interests include running, cycling and gym
- Uses services like Swiggy, Zomato, Ola, Uber, Blinkit for daily needs
- Has accounts with ICICI, SBI, Axis bank, BSE, NSE, Zerodha, Upstox

You will receive the subject, sender, date and body of each email.
Use ALL of this information to understand the true intent before classifying.
Do not rely on subject alone - the body reveals the real purpose.

ALWAYS classify as alert and keep, regardless of sender:
- Payment confirmations or receipts for any purchase or bill payment
- OTP or verification code emails
- PAN, Aadhaar, passport, visa or any government identity document emails
- Tax related emails - ITR, Form 16, TDS certificates
- Insurance policy documents, premium confirmations, policy copies,
  health or life insurance coverage communications
- Subscription renewal confirmations for any paid service
- Order confirmations from food, grocery or any delivery service
- Flight, train, hotel or travel booking confirmations
- Doctor appointment confirmations, medical reports, hospital bills
- Electricity, water, gas or any utility bill confirmations
- HR communications, offer letters, interview calls, salary documents
- Professional certification or course completion confirmations
- Government or legal notices
- Any email confirming a transaction or action the user initiated
- Course enrollment confirmations or receipts from any learning platform
- Recommended courses from platforms like Udemy, Coursera, LinkedIn Learning
  if they are relevant to tech, AI, or software engineering

ALWAYS classify as spam and delete:
- Promotional offers, discounts, cashback, vouchers
- Loan or credit card offers
- Unsolicited investment advice or stock tips
- Marketing emails even from known brands
- Weekly digests or newsletters unless specifically tech related
- Any email trying to sell something rather than confirm something

Classify the email and respond ONLY in JSON with no preamble or markdown:
{
    "flag": "spam|job|news|alert",
    "decision": "delete|keep",
    "reason": "one line explanation"
}

Classification rules:
- job: career emails, job postings, interview calls, HR communications
- news: tech news, industry updates from reputable sources
- alert: transaction confirmations, OTPs, documents, bookings, bills
- spam: advertisements, promotions, offers, unsolicited emails

For decision:
- spam -> delete
- job, news, alert -> keep
"""

INTENT_PROMPT = """
You are helping classify a financial email for a software professional.
Determine if this email is genuinely informing the user about a transaction,
account activity, or financial event related to their account.

Respond ONLY in JSON with no preamble or markdown:
{
    "is_transactional": "yes|no",
    "reason": "one line explanation"
}

Examples of transactional emails - classify as yes:
- Account balance update
- Fund transfer confirmation
- Securities balance statement
- Reward points redeemed successfully
- Payment confirmation for any purchase or bill
- Trade execution confirmation
- OTP or verification code
- PAN, Aadhaar, or government document related
- Insurance policy document or premium payment confirmation
- Health or life insurance coverage related communication
- Subscription renewal confirmation
- Order confirmation from any service

Examples of non-transactional emails - classify as no:
- Loan offers
- Credit card promotions
- Investment advice advertisements
- Free course offerings
- Voucher unlocks as promotions
- Cashback offers
- Any unsolicited offer or advertisement
"""


def create_usage_tracker():
    """
    Creates a fresh usage tracker dictionary.
    Pass this into classify functions to track API usage across a run.
    """
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0
    }


def calculate_cost(usage):
    """
    Calculates approximate cost in USD based on token usage.
    """
    input_cost = (usage["input_tokens"] / 1_000_000) * INPUT_COST_PER_MILLION
    output_cost = (usage["output_tokens"] / 1_000_000) * OUTPUT_COST_PER_MILLION
    return round(input_cost + output_cost, 6)


def print_usage_summary(usage):
    """
    Prints a summary of API usage and estimated cost.
    """
    cost = calculate_cost(usage)
    print("\n" + "=" * 60)
    print("API USAGE SUMMARY")
    print("=" * 60)
    print(f"Total API calls made:     {usage['calls']}")
    print(f"Total input tokens:       {usage['input_tokens']:,}")
    print(f"Total output tokens:      {usage['output_tokens']:,}")
    print(f"Estimated cost:           ${cost:.6f} USD")
    print("=" * 60)


def classify_email(email, usage=None):
    """
    Takes an email dictionary and returns classification from Claude API.
    Optionally tracks usage if a usage dict is passed in.
    """
    email_data = json.dumps({
        "subject": email["subject"],
        "sender": email["sender"],
        "date": email["date"],
        "body": email.get("body", "")
    })

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Classify this email:\n{email_data}"
            }
        ]
    )

    # Track usage if tracker provided
    if usage is not None:
        usage["calls"] += 1
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens

    response_text = response.content[0].text.strip()

    # Clean response in case of markdown
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    # Handle empty response
    if not response_text:
        return {
            "is_transactional": "no",
            "reason": "Empty response from model - defaulting to non-transactional"
        }

    return json.loads(response_text)

    # Clean response in case of markdown
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    return json.loads(response_text)

# Kept for reference - may be useful if body parsing is removed in future

# def check_transactional_intent(email, usage=None):
#     email_data = json.dumps({
#         "subject": email["subject"],
#         "sender": email["sender"],
#         "body": email.get("body", "")
#     })

#     response = client.messages.create(
#         model="claude-haiku-4-5",
#         max_tokens=128,
#         system=INTENT_PROMPT,
#         messages=[
#             {
#                 "role": "user",
#                 "content": f"Is this email transactional or promotional?\n{email_data}"
#             }
#         ]
#     )

#     if usage is not None:
#         usage["calls"] += 1
#         usage["input_tokens"] += response.usage.input_tokens
#         usage["output_tokens"] += response.usage.output_tokens

#     # Debug - let's see exactly what came back
#     print(f"DEBUG stop_reason: {response.stop_reason}")
#     print(f"DEBUG content blocks: {len(response.content)}")
#     print(f"DEBUG raw response: '{response.content}'")

#     response_text = response.content[0].text.strip()
#     print(f"DEBUG response_text: '{response_text}'")

#     if response_text.startswith("```"):
#         response_text = response_text.split("```")[1]
#         if response_text.startswith("json"):
#             response_text = response_text[4:]

#     if not response_text:
#         return {
#             "is_transactional": "no",
#             "reason": "Empty response from model - defaulting to non-transactional"
#         }

#     return json.loads(response_text)


def apply_guardrails(email, classification, usage=None):
    """
    Enforces business rules on top of LLM classification.
    Layer 1 - Sender trust check in code
    Layer 2 - Intent verification via second LLM call for financial senders
    Layer 3 - Image heavy email detection
    Layer 4 - OTP detection
    """

    subject = email["subject"].lower()
    body = email.get("body", "").lower()

    # Layer 3 - Handle image heavy or very short body emails
    if len(body) < 50:
        otp_keywords = ["otp", "verification", "verify", "code",
                       "password", "authentication", "confirm your"]
        is_otp = any(
            keyword in subject or keyword in body
            for keyword in otp_keywords
        )

        if is_otp:
            classification["flag"] = "alert"
            classification["decision"] = "keep"
            classification["reason"] = (
                "OTP or verification email - kept regardless of body length")
        elif classification["flag"] != "alert":
            classification["flag"] = "spam"
            classification["decision"] = "delete"
            classification["reason"] += (
                " [Guardrail: image-heavy email with no readable content]")

    # Final safety net
    if classification["flag"] == "spam":
        classification["decision"] = "delete"
    else:
        classification["decision"] = "keep"

    return classification


if __name__ == "__main__":
    # Create usage tracker for this test run
    usage = create_usage_tracker()

    test_emails = [
        {
            "id": "test_001",
            "subject": "Senior Applied AI Engineer - $200,000/year",
            "sender": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            "date": "Tue, 16 Jun 2026",
            "body": "We found a job matching your profile. Senior Applied AI Engineer at LearnWith.AI."
        },
        {
            "id": "test_002",
            "subject": "Your OTP for login",
            "sender": "ICICI Bank <alerts@icicibank.com>",
            "date": "Tue, 16 Jun 2026",
            "body": "Your OTP is 456123. Valid for 10 minutes. Do not share."
        },
        {
            "id": "test_003",
            "subject": "Your Swiggy order is confirmed",
            "sender": "Swiggy <no-reply@swiggy.in>",
            "date": "Tue, 16 Jun 2026",
            "body": "Your order from Burger King has been confirmed. Order total Rs 450."
        },
        {
            "id": "test_004",
            "subject": "HDFC Bank - Pre approved loan offer",
            "sender": "HDFC Bank <offers@hdfcbank.com>",
            "date": "Tue, 16 Jun 2026",
            "body": "Congratulations! You are pre-approved for a personal loan of Rs 5 lakhs."
        }
    ]

    for email in test_emails:
        print(f"\nEmail: {email['subject'][:60]}")
        classification = classify_email(email, usage)
        classification = apply_guardrails(email, classification, usage)
        print(f"Flag:     {classification['flag']}")
        print(f"Decision: {classification['decision']}")
        print(f"Reason:   {classification['reason']}")
        print("-" * 50)

    # Print usage summary at end
    print_usage_summary(usage)