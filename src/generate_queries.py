# src/generate_queries.py
import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from collections import defaultdict

# -------------------------------
# 🔑 Load API key
# -------------------------------
load_dotenv()
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_KEY)

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data/Constitution Data")
OUT_FILE = "Constitution_Que.json"


# -------------------------------
# 📂 Extract sections
# -------------------------------
def extract_sections_from_json():
    """Extract text fields from all JSON files."""
    sections = []
    for fname in os.listdir(DATA_DIR):
        if fname.lower().endswith(".json"):
            path = os.path.join(DATA_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"⚠️ Skipping {fname}, invalid JSON: {e}")
                    continue

            def walk(node):
                if isinstance(node, dict):
                    if "text" in node and isinstance(node["text"], str):
                        sections.append({"source": fname, "text": node["text"]})
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(data)
    return sections


# -------------------------------
# 🧠 Question Generation
# -------------------------------
def generate_queries_for_section(section_text, source):
    """Generate diverse queries with layman voice tone."""
    prompt = f"""
    You are helping create a question bank.

    The following text is from {source}:
    ---
    {section_text[:1200]}
    ---

    Generate 2 questions written in simple, everyday language that a common person with no legal knowledge might ask about the Constitution of India.
    For example: What will happen if I steal a car or commit a murder?
    The other question could be something like: Can a government officer be punished for taking a bribe or forging official documents?
    Keep all questions diverse — covering different situations such as murder, theft, bribery, tax fraud, document forgery, corruption, misuse of power, or violation of constitutional rights.

    Return only the questions — one per line.
    """

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500
    )

    content = resp.choices[0].message.content.strip()
    questions = [q.strip("•- \t1234567890.") for q in content.split("\n") if q.strip()]
    return questions


# -------------------------------
# 🚀 Main
# -------------------------------
def main():
    sections = extract_sections_from_json()
    print(f"📂 Extracted {len(sections)} text chunks from Constituion JSON files")

    # Group by file
    grouped = defaultdict(list)
    for sec in sections:
        grouped[sec["source"]].append(sec)

    all_questions = []
    counter = 1

    for fname, secs in grouped.items():
        print(f"\n📄 Processing {fname} ({len(secs)} chunks)")

        for sec in secs:
            qs = generate_queries_for_section(sec["text"], fname)
            for q in qs:
                all_questions.append({
                    "id": counter,
                    "question": q,
                    "source": fname
                })
                counter += 1

    # Deduplicate by question text
    seen = set()
    unique_questions = []
    for item in all_questions:
        if item["question"] not in seen:
            unique_questions.append(item)
            seen.add(item["question"])

    out_path = os.path.join(os.path.dirname(__file__), OUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(unique_questions, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Generated {len(unique_questions)} questions saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
