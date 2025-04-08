import os
from dotenv import load_dotenv
from groq import Groq
import csv
import json
import time
from faker import Faker
import random

# Load environment variables from .env file
load_dotenv()

# Get your Groq API key from the environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"  # Or another suitable Groq model
OUTPUT_FILENAME = "generated_comments.csv"
NUM_COMMENTS_TO_GENERATE = 200
COMMENTS_PER_BATCH = 10  # To avoid overwhelming the API and for better progress tracking

if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY not found in .env file or environment variables.")
    # Provide instructions on how to set up the .env file
    print("Please create a .env file in the same directory as this script and add:")
    print("GROQ_API_KEY=your_groq_api_key_here")
    exit()

client = Groq(api_key=GROQ_API_KEY)
fake = Faker()

def generate_comments_batch(num_comments: int) -> list[dict]:
    """Generates a batch of user comments using the Groq LLM."""
    prompt = f"""Generate {num_comments} diverse user comments suitable for testing an offensive content detection system.
Include a mix of positive, neutral, and various types of offensive comments (hate speech, toxicity, profanity, harassment, spam, sarcasm, etc.).
Each comment should be a single-line JSON object with the keys: "username" (generate a realistic-sounding username), and "comment_text" (the user comment). Separate each JSON object with a newline character."""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL_NAME,
            max_tokens=2000,  # Increased max_tokens to accommodate more varied responses
            temperature=0.8,  # Slightly higher temperature for more variety
        )
        if chat_completion.choices:
            content = chat_completion.choices[0].message.content.strip()
            comments = []
            for line in content.splitlines():
                try:
                    comment_json = json.loads(line)
                    if "username" in comment_json and "comment_text" in comment_json:
                        comments.append(comment_json)
                    else:
                        print(f"Warning: Incomplete JSON object: {comment_json}")
                except json.JSONDecodeError:
                    print(f"Warning: Could not decode JSON line: {line}")
            return comments
        else:
            print("Warning: No response from the Groq model.")
            return []
    except Exception as e:
        print(f"Error during Groq API call: {e}")
        return []

all_generated_comments = []
for i in range(0, NUM_COMMENTS_TO_GENERATE, COMMENTS_PER_BATCH):
    print(f"Generating comments {i + 1} to {min(i + COMMENTS_PER_BATCH, NUM_COMMENTS_TO_GENERATE)}...")
    batch = generate_comments_batch(COMMENTS_PER_BATCH)
    all_generated_comments.extend(batch)
    time.sleep(2)  # Be mindful of rate limits

print(f"\nGenerated {len(all_generated_comments)} comments.")

# Ensure all comments have the required fields and add a sequential ID
final_comments = []
for index, comment in enumerate(all_generated_comments):
    if "username" not in comment:
        comment["username"] = fake.user_name()
    if "comment_text" not in comment:
        comment["comment_text"] = "This comment had an issue."
    final_comments.append({"comment_id": index + 1, "username": comment["username"], "comment_text": comment["comment_text"]})

# Save the generated comments to a CSV file
with open(OUTPUT_FILENAME, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ["comment_id", "username", "comment_text"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(final_comments)

print(f"\nGenerated comments saved to {OUTPUT_FILENAME}")