# chat.py – Multi-index RAG (Constitution + Criminal Law)
import os
import re
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from openai import OpenAI

# -------------------------------
# 🔑 Load API Keys (works locally AND on Streamlit Cloud)
# -------------------------------
import streamlit as st

# Try Streamlit secrets first (for cloud deployment), fallback to .env (for local)
try:
    OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
    PINE_API = st.secrets["PINECONE_API_KEY"]
    print("✅ Loaded API keys from Streamlit secrets")
except:
    load_dotenv()
    OPENAI_KEY = os.environ["OPENAI_API_KEY"]
    PINE_API = os.environ["PINECONE_API_KEY"]
    print("✅ Loaded API keys from .env file")
# -------------------------------
# 🔧 Init Clients
# -------------------------------
try:
    client = OpenAI(api_key=OPENAI_KEY)
    pc = Pinecone(api_key=PINE_API)

    # ✅ Multi-index setup
    indexes = {
        "constitution": pc.Index("indialaw"),
        "criminal": pc.Index("criminallaw")
    }

    emb = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_KEY)
    print("✅ All clients initialized successfully (multi-index mode)")
except Exception as e:
    print(f"❌ Error initializing clients: {e}")
    raise

SYSTEM_PROMPT = """You are an Indian law assistant.
Your job is to:
1. Answer direct questions about the Constitution of India and other laws.
2. If a user describes a real-life situation in plain words (not a direct legal question),
   - Identify possible legal issues involved.
   - Suggest which laws, constitutional provisions, or schedules may apply.
   - Explain in simple, non-technical terms what kind of legal action or case may be possible.
   - If information is insufficient, politely ask clarifying questions.
Do NOT include citations, filenames, or sources in your response.
Always keep your language clear, practical, and understandable to non-lawyers.
"""

# -------------------------------
# 💾 Session Handling
# -------------------------------
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
SESSION_FILE = os.path.join(SESSIONS_DIR, f"{SESSION_ID}.json")

chat_history = []

def save_session():
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save session: {e}")

# -------------------------------
# 🔍 Multi-Query Expansion
# -------------------------------
def generate_alternative_queries(question, n=3):
    if not question.strip():
        return [question]
    
    prompt = f"""
    Rewrite the following law-related question into {n} different variations:
    - One in plain layperson language
    - One in formal legal language
    - One as a student/research query

    Question: {question}
    Return only the list of variations, one per line.
    """
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            timeout=30
        )
        content = resp.choices[0].message.content.strip()
        variations = [q.strip("-•1234567890. ") for q in content.split("\n") if q.strip()]
        return list(set([question] + variations))[:n+1]
    except Exception as e:
        print(f"⚠️ Query expansion failed: {e}")
        return [question]

def multi_query_retrieve(question, k=5, verbose=False):
    """Retrieve from ALL indexes and merge results"""
    if not question.strip():
        return []
    
    queries = generate_alternative_queries(question, n=3)
    if verbose:
        print(f"🔄 Expanded into {len(queries)} queries")

    expanded_matches = {}
    successful_queries = 0

    for q in queries:
        try:
            qvec = emb.embed_query(q)
            for name, idx in indexes.items():
                res = idx.query(vector=qvec, top_k=k, include_metadata=True)
                for m in res.get("matches", []):
                    m["metadata"]["index_source"] = name  # 👈 tag which index
                    if m["id"] not in expanded_matches or m["score"] > expanded_matches[m["id"]]["score"]:
                        expanded_matches[m["id"]] = m
            successful_queries += 1
        except Exception as e:
            print(f"⚠️ Query failed for '{q[:50]}...': {e}")
            continue
    
    if verbose:
        print(f"📚 Retrieved {len(expanded_matches)} unique chunks across {len(indexes)} indexes")
    
    return list(expanded_matches.values())

# -------------------------------
# 🔗 Cross-link Expansion
# -------------------------------
def expand_with_links(chunks, k=3, verbose=False):
    if not chunks:
        return []
    
    expanded = {c["id"]: c for c in chunks}
    for c in chunks:
        try:
            meta = c.get("metadata", {})
            related_keys = []
            for key in ["schedule", "appendix", "part"]:
                value = meta.get(key)
                if value and isinstance(value, str) and len(value.strip()) > 2:
                    related_keys.append(value)
            for value in related_keys[:3]:
                try:
                    qvec = emb.embed_query(value)
                    # search in ALL indexes
                    for name, idx in indexes.items():
                        followup = idx.query(vector=qvec, top_k=k, include_metadata=True)
                        for m in followup.get("matches", []):
                            m["metadata"]["index_source"] = name
                            if m["id"] not in expanded:
                                expanded[m["id"]] = m
                except Exception as e:
                    print(f"⚠️ Cross-link query failed for '{value}': {e}")
        except Exception as e:
            print(f"⚠️ Error in cross-links: {e}")
    if verbose:
        print(f"🔗 Expanded to {len(expanded)} chunks with cross-links")
    return list(expanded.values())

# -------------------------------
# 🔎 Reranking
# -------------------------------
def rerank_chunks(question, chunks, top_k=5, verbose=False):
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks[:top_k]

    chunk_texts = []
    for i, c in enumerate(chunks):
        text = c.get('metadata', {}).get('text', '')[:300]
        source = c.get('metadata', {}).get('index_source', 'unknown')
        chunk_texts.append(f"Chunk {i} ({source}): {text}")
    
    chunk_block = "\n\n".join(chunk_texts)

    rerank_prompt = f"""
    You are a legal assistant. Rank the following chunks by their relevance to the question.

    Question: {question}

    Chunks:
    {chunk_block}

    Output ONLY the top {top_k} chunk numbers in order of relevance, comma-separated.
    """

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": rerank_prompt}],
            temperature=0,
            max_tokens=100,
            timeout=30
        )
        raw_output = resp.choices[0].message.content.strip()
        numbers = re.findall(r'\b\d+\b', raw_output)
        selected_idx = []
        for num_str in numbers:
            try:
                idx = int(num_str)
                if 0 <= idx < len(chunks) and idx not in selected_idx:
                    selected_idx.append(idx)
                if len(selected_idx) >= top_k:
                    break
            except:
                continue
        if len(selected_idx) < top_k:
            for i in range(len(chunks)):
                if i not in selected_idx:
                    selected_idx.append(i)
                if len(selected_idx) >= top_k:
                    break
        return [chunks[i] for i in selected_idx[:top_k]]
    except Exception as e:
        print(f"⚠️ Reranking failed: {e}")
        return sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)[:top_k]

# -------------------------------
# 🧠 Build Context
# -------------------------------
def build_context(chunks, max_length=8000):
    context_parts = []
    total_length = 0
    for c in chunks:
        text = c.get('metadata', {}).get('text', '')
        source = c.get('metadata', {}).get('index_source', 'unknown')
        if not text.strip():
            continue
        snippet = f"[{source.upper()}] {text}"
        if total_length + len(snippet) > max_length:
            remaining = max_length - total_length
            if remaining > 100:
                snippet = snippet[:remaining].rsplit(' ', 1)[0] + "..."
                context_parts.append(snippet)
            break
        context_parts.append(snippet)
        total_length += len(snippet)
        if total_length >= max_length:
            break
    return "\n\n".join(context_parts)

# -------------------------------
# 🧠 Answer
# -------------------------------
def answer_question(question, verbose=False):
    if not question.strip():
        return "Please provide a valid question."
    try:
        candidate_chunks = multi_query_retrieve(question, k=5, verbose=verbose)
        if not candidate_chunks:
            return "I couldn't find relevant information."
        expanded_chunks = expand_with_links(candidate_chunks, k=3, verbose=verbose)
        top_chunks = rerank_chunks(question, expanded_chunks, top_k=5, verbose=verbose)
        context = build_context(top_chunks, max_length=8000)
        if not context.strip():
            return "I found data but couldn’t extract meaningful content."
        user_message = f"Question: {question}\n\nContext:\n{context}\n\nAnswer:"
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0,
            max_tokens=600,
            timeout=60
        )
        answer = resp.choices[0].message.content
        chat_history.append({"role": "user", "content": question})
        chat_history.append({"role": "assistant", "content": answer})
        save_session()
        return answer
    except Exception as e:
        return f"❌ Error while answering: {str(e)}"

# -------------------------------
# 💬 Interactive Mode
# -------------------------------
if __name__ == "__main__":
    print(f"📌 New session started: {SESSION_ID}")
    print("Type 'exit' to quit.\n")
    while True:
        q = input("Ask about Indian law: ").strip()
        if q.lower() in ["exit", "quit"]:
            print(f"💾 Chat saved at {SESSION_FILE}")
            break
        if not q:
            continue
        print("🤔 Thinking...")
        print("\n🤖", answer_question(q, verbose=False), "\n")
