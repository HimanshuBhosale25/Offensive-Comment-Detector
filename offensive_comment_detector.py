import csv
import json
from typing import List, Dict
import argparse
import os
from openai import OpenAI
from collections import Counter
import matplotlib.pyplot as plt
from better_profanity import profanity
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY not found in .env file or environment variables.")
    exit()

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_NAME = "gpt-4o-mini"  # You can choose a different model
OUTPUT_FILE_DEFAULT = "analyzed_comments.csv"
REPORT_JSON_FILE_DEFAULT = "offensive_comment_report.json"

def load_comments(file_path: str) -> List[Dict]:
    """Loads comments from a CSV or JSON file."""
    comments = []
    try:
        if file_path.endswith(".csv"):
            with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    comments.append(row)
        elif file_path.endswith(".json"):
            with open(file_path, 'r', encoding='utf-8') as jsonfile:
                data = json.load(jsonfile)
                if isinstance(data, list):
                    comments = data
                elif isinstance(data, dict) and 'comments' in data:
                    comments = data['comments']
                else:
                    raise ValueError("JSON file should contain a list of comments or a dictionary with a 'comments' key.")
        else:
            raise ValueError("Unsupported file format. Please use CSV or JSON.")
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return []
    except Exception as e:
        print(f"Error loading file: {e}")
        return []
    return comments

def display_summary(comments: List[Dict]):
    """Displays a summary of the loaded comments."""
    total_comments = len(comments)
    print(f"Total number of comments loaded: {total_comments}")
    if comments:
        print("\nSample of the first 5 comments:")
        for i, comment in enumerate(comments[:5]):
            print(f"  {i+1}. ID: {comment.get('comment_id')}, User: {comment.get('username')}, Comment: {comment.get('comment_text')}")
    else:
        print("No comments to display.")

def pre_filter_comments(comments: List[Dict]) -> List[Dict]:
    """Pre-filters comments for profanity using better_profanity."""
    filtered_comments = []
    profane_count = 0
    for comment in comments:
        text = comment.get('comment_text', '')
        if profanity.contains_profanity(text):
            comment['is_offensive'] = True
            comment['offense_type'] = "profanity"
            comment['explanation'] = "Flagged by better_profanity"
            filtered_comments.append(comment)
            profane_count += 1
        else:
            filtered_comments.append(comment)
    print(f"\nPre-filtered {profane_count} comments for profanity using better_profanity.")
    return filtered_comments

def analyze_comment_with_ai(comment: Dict) -> Dict:
    """Analyzes a comment using OpenAI to detect offensive content with severity."""
    if comment.get('is_offensive') and comment.get('offense_type') == 'profanity':
        comment['severity'] = 1  # Assign a lower severity to basic profanity
        return comment

    text = comment.get('comment_text', '')
    prompt = f"""Analyze the following user comment to determine if it contains offensive content and its severity. Consider the presence of profanity, hate speech, toxicity, and harassment, taking into account the context and overall impact.

Comment: "{text}"

Respond with a JSON object in the following format:
{{
  "is_offensive": true/false,
  "offense_type": "hate speech" or "toxicity" or "harassment" or "profanity" or null,
  "explanation": "short explanation based on the analysis" or null,
  "severity": integer from 1 (mild) to 5 (severe) or null
}}

Specifically:
- Profanity: severity 1-3 (depending on intensity and context).
- Toxicity (general rudeness, insults): severity 1-5.
- Harassment (targeted abuse, threats): severity 1-5.
- Hate Speech (attacks based on protected characteristics): severity 1-5.
- If not offensive, "is_offensive": false, and other fields null."""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.2,
        )
        if response.choices:
            try:
                analysis = json.loads(response.choices[0].message.content)
                comment['is_offensive'] = analysis.get('is_offensive', False)
                comment['offense_type'] = analysis.get('offense_type')
                comment['explanation'] = analysis.get('explanation')
                comment['severity'] = analysis.get('severity')
            except json.JSONDecodeError:
                print(f"Error decoding JSON response for comment ID {comment.get('comment_id')}: {response.choices[0].message.content}")
                comment['is_offensive'] = True
                comment['offense_type'] = "error"
                comment['explanation'] = "Error decoding AI analysis response."
                comment['severity'] = 3  # Assign a medium severity for error
        else:
            comment['is_offensive'] = False
            comment['offense_type'] = None
            comment['explanation'] = "No response from AI model."
            comment['severity'] = None
    except Exception as e:
        print(f"Error during OpenAI API call for comment ID {comment.get('comment_id')}: {e}")
        comment['is_offensive'] = True
        comment['offense_type'] = "api_error"
        comment['explanation'] = f"Error during AI analysis: {e}"
        comment['severity'] = 4  # Assign a higher severity for API error

    return comment

def process_comments(comments: List[Dict], pre_filter: bool = False) -> List[Dict]:
    """Processes each comment using the AI model with optional pre-filtering."""
    if pre_filter:
        comments = pre_filter_comments(comments)
    analyzed_comments = []
    for comment in comments:
        analyzed_comments.append(analyze_comment_with_ai(comment.copy()))
    return analyzed_comments

def generate_report_json(analyzed_comments: List[Dict]) -> Dict:
    """Generates a JSON report of the analysis, prioritizing variation in top severe comments."""
    offensive_comments = [c for c in analyzed_comments if c.get('is_offensive')]
    num_offensive = len(offensive_comments)
    total_comments = len(analyzed_comments)

    # Sort all offensive comments by severity in descending order
    sorted_offensive = sorted(offensive_comments, key=lambda x: x.get('severity', 0), reverse=True)

    top_5_varied = []
    seen_offense_types = set()

    for comment in sorted_offensive:
        offense_type = comment.get('offense_type')
        if len(top_5_varied) < 5:
            if offense_type not in seen_offense_types:
                top_5_varied.append(comment)
                seen_offense_types.add(offense_type)
            elif not top_5_varied:  # If we haven't found any yet, add the most severe
                top_5_varied.append(comment)
        else:
            break

    # If we still have less than 5, fill with the remaining most severe
    if len(top_5_varied) < 5:
        for comment in sorted_offensive:
            if comment not in top_5_varied and len(top_5_varied) < 5:
                top_5_varied.append(comment)

    report = {
        "total_comments": total_comments,
        "num_offensive_comments": num_offensive,
        "offense_type_breakdown": Counter([c.get('offense_type') for c in offensive_comments if c.get('offense_type')]),
        "top_5_most_severe_offensive_comments_varied": top_5_varied
    }
    return report

def export_report(analyzed_comments: List[Dict], output_file: str):
    """Exports the analyzed data to a new CSV or JSON file."""
    try:
        if output_file.endswith(".csv"):
            fieldnames = ["comment_id", "username", "comment_text", "is_offensive", "offense_type", "explanation", "severity"]
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                # Ensure all dictionaries have all the fieldnames
                for comment in analyzed_comments:
                    for field in fieldnames:
                        if field not in comment:
                            comment[field] = None
                writer.writerows(analyzed_comments)
            print(f"\nAnalyzed data exported to {output_file}")
        elif output_file.endswith(".json"):
            with open(output_file, 'w', encoding='utf-8') as jsonfile:
                json.dump({"analyzed_comments": analyzed_comments}, jsonfile, indent=4)
            print(f"\nAnalyzed data exported to {output_file}")
        else:
            print("Unsupported output file format. Please use CSV or JSON.")
    except Exception as e:
        print(f"Error exporting data: {e}")

def save_report_json(report_data: Dict, output_file: str = REPORT_JSON_FILE_DEFAULT):
    """Saves the JSON report data to a file."""
    try:
        with open(output_file, 'w', encoding='utf-8') as jsonfile:
            json.dump(report_data, jsonfile, indent=4)
        print(f"\nOffensive comment report saved to: {output_file}")
    except Exception as e:
        print(f"Error saving JSON report: {e}")

def plot_offense_distribution(analyzed_comments: List[Dict]):
    """Creates a bar chart showing the distribution of offense types."""
    offensive_comments = [c for c in analyzed_comments if c.get('is_offensive') and c.get('offense_type')]
    offense_types = [c.get('offense_type') for c in offensive_comments]
    offense_type_counts = Counter(offense_types)

    if offense_type_counts:
        labels = list(offense_type_counts.keys())
        counts = list(offense_type_counts.values())

        plt.figure(figsize=(10, 6))
        plt.bar(labels, counts, color='skyblue')
        plt.xlabel("Offense Type")
        plt.ylabel("Number of Comments")
        plt.title("Distribution of Offensive Comment Types")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()
    else:
        print("No offensive comments found to plot distribution.")

def main():
    parser = argparse.ArgumentParser(description="Detect offensive comments in a file using Gen AI with bonus features.")
    parser.add_argument("input_file", nargs='?', default="generated_comments.csv", help="Path to the input CSV or JSON file containing comments (default: generated_comments.csv).")
    parser.add_argument("-o", "--output_file", default=OUTPUT_FILE_DEFAULT, help=f"Path to the output CSV/JSON file (default: {OUTPUT_FILE_DEFAULT}).")
    parser.add_argument("--filter", action="store_true", help="Enable pre-filtering of profanity using profanity libraries.")
    parser.add_argument("--plot", action="store_true", help="Create a bar chart of offense type distribution.")
    parser.add_argument("--report_json", action="store_true", help="Save the report summary as a separate JSON file.")
    parser.add_argument("--report_json_output_file", default=REPORT_JSON_FILE_DEFAULT, help=f"Path to save the JSON report (default: {REPORT_JSON_FILE_DEFAULT}).")
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file
    pre_filter = args.filter
    plot_chart = args.plot
    report_json_output = args.report_json
    report_json_output_file = args.report_json_output_file

    comments = load_comments(input_file)
    if comments:
        display_summary(comments)
        analyzed_comments = process_comments(comments, pre_filter)
        export_report(analyzed_comments, output_file)
        report_data = generate_report_json(analyzed_comments)
        if report_json_output:
            save_report_json(report_data, report_json_output_file)
        if plot_chart:
            plot_offense_distribution(analyzed_comments)
    else:
        print("No comments loaded. Exiting.")

if __name__ == "__main__":
    main()