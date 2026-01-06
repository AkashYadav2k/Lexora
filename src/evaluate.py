# Enhanced evaluation with multiple metrics and proper answer assessment

import os
import csv
import json
import traceback
import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass
from dotenv import load_dotenv
from chat import answer_question, multi_query_retrieve, expand_with_links, rerank_chunks
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# -----------------------------
# 🔑 Load environment
# -----------------------------
load_dotenv()
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

emb = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_KEY)
llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=OPENAI_KEY, temperature=0)

@dataclass
class EvaluationResult:
    question: str
    generated_answer: str
    expected_answer: str = ""
    retrieval_score: float = 0.0
    answer_relevance: float = 0.0
    factual_accuracy: float = 0.0
    completeness: float = 0.0
    overall_score: float = 0.0
    status: str = "Unknown"
    top_chunk_preview: str = ""
    feedback: str = ""

class RAGEvaluator:
    def __init__(self):
        self.results: List[EvaluationResult] = []
        
    def evaluate_answer_quality(self, question: str, answer: str, expected: str = "") -> Dict[str, float]:
        """Evaluate answer using LLM-based metrics"""
        
        # 1. Answer Relevance
        relevance_prompt = f"""
        Question: {question}
        Generated Answer: {answer}
        
        Rate how well the answer addresses the question on a scale of 0-1:
        - 1.0: Directly and completely answers the question
        - 0.5: Partially addresses the question
        - 0.0: Doesn't address the question at all
        
        Return only a number between 0 and 1.
        """
        
        # 2. Completeness
        completeness_prompt = f"""
        Question: {question}
        Generated Answer: {answer}
        
        Rate how complete the answer is on a scale of 0-1:
        - 1.0: Provides comprehensive, complete information
        - 0.5: Provides partial information
        - 0.0: Provides minimal or no useful information
        
        Return only a number between 0 and 1.
        """
        
        # 3. Factual Accuracy (if expected answer provided)
        accuracy_score = 0.0
        if expected:
            accuracy_prompt = f"""
            Question: {question}
            Expected Answer: {expected}
            Generated Answer: {answer}
            
            Rate the factual accuracy on a scale of 0-1:
            - 1.0: Factually correct and consistent with expected answer
            - 0.5: Mostly correct with minor inaccuracies
            - 0.0: Contains significant factual errors
            
            Return only a number between 0 and 1.
            """
            
            try:
                accuracy_response = llm.invoke(accuracy_prompt)
                accuracy_score = float(accuracy_response.content.strip())
            except:
                accuracy_score = 0.0
        
        try:
            relevance_response = llm.invoke(relevance_prompt)
            relevance_score = float(relevance_response.content.strip())
            
            completeness_response = llm.invoke(completeness_prompt)
            completeness_score = float(completeness_response.content.strip())
        except:
            relevance_score = 0.0
            completeness_score = 0.0
        
        return {
            "relevance": min(max(relevance_score, 0.0), 1.0),
            "completeness": min(max(completeness_score, 0.0), 1.0),
            "accuracy": min(max(accuracy_score, 0.0), 1.0)
        }
    
    def calculate_retrieval_score(self, question: str, chunks: List[Any]) -> float:
        """Calculate retrieval quality score"""
        if not chunks:
            return 0.0
            
        qvec = emb.embed_query(question)
        scores = []
        
        for chunk in chunks[:3]:  # Top 3 chunks
            text = chunk.get("metadata", {}).get("text") or chunk.get("text", "")
            if text:
                tvec = emb.embed_documents([text])[0]
                sim = float(np.dot(qvec, tvec) / (np.linalg.norm(qvec) * np.linalg.norm(tvec)))
                scores.append(sim)
        
        return max(scores) if scores else 0.0
    
    def determine_status(self, result: EvaluationResult) -> str:
        """Determine overall status based on multiple metrics"""
        if result.overall_score >= 0.8:
            return "Excellent"
        elif result.overall_score >= 0.65:
            return "Good"
        elif result.overall_score >= 0.5:
            return "Acceptable"
        elif result.overall_score >= 0.3:
            return "Poor"
        else:
            return "Insufficient"
    
    def evaluate_single_question(self, question: str, expected_answer: str = "") -> EvaluationResult:
        """Evaluate a single question through the full pipeline"""
        
        try:
            # 1. Retrieval pipeline
            base_chunks = multi_query_retrieve(question, k=5)
            expanded = expand_with_links(base_chunks, k=3)
            top_chunks = rerank_chunks(question, expanded, top_k=5)
            
            # 2. Generate answer
            generated_answer = answer_question(question)
            if isinstance(generated_answer, bytes):
                generated_answer = generated_answer.decode("utf-8", errors="ignore")
            generated_answer = (generated_answer or "").strip()
            
            # 3. Calculate retrieval score
            retrieval_score = self.calculate_retrieval_score(question, top_chunks)
            
            # 4. Evaluate answer quality
            quality_metrics = self.evaluate_answer_quality(question, generated_answer, expected_answer)
            
            # 5. Calculate overall score (weighted average)
            overall_score = (
                0.2 * retrieval_score +           # Retrieval quality
                0.3 * quality_metrics["relevance"] +     # Answer relevance
                0.3 * quality_metrics["completeness"] +  # Completeness
                0.2 * quality_metrics["accuracy"]        # Factual accuracy
            )
            
            # 6. Create result
            result = EvaluationResult(
                question=question,
                generated_answer=generated_answer,
                expected_answer=expected_answer,
                retrieval_score=round(retrieval_score, 3),
                answer_relevance=round(quality_metrics["relevance"], 3),
                factual_accuracy=round(quality_metrics["accuracy"], 3),
                completeness=round(quality_metrics["completeness"], 3),
                overall_score=round(overall_score, 3),
                top_chunk_preview=self.safe_preview(
                    top_chunks[0].get("metadata", {}).get("text", "") if top_chunks else ""
                ),
            )
            
            result.status = self.determine_status(result)
            return result
            
        except Exception as e:
            return EvaluationResult(
                question=question,
                generated_answer=f"ERROR: {e}",
                expected_answer=expected_answer,
                status="Error",
                feedback=str(e)
            )
    
    def safe_preview(self, text: str, length: int = 200) -> str:
        """Create safe preview of text"""
        if not text:
            return ""
        return text.replace("\n", " ").strip()[:length]
    
    def run_evaluation(self, questions_data: List[Dict], output_prefix: str = "evaluation"):
        """Run full evaluation on a list of questions"""
        
        results = []
        status_counts = {}
        total_scores = {
            "retrieval": 0.0,
            "relevance": 0.0, 
            "accuracy": 0.0,
            "completeness": 0.0,
            "overall": 0.0
        }
        
        for i, item in enumerate(questions_data, 1):
            if isinstance(item, dict):
                question = item.get("question", "")
                expected = item.get("expected_answer", "")
            else:
                question = str(item)
                expected = ""
                
            print(f"\n[{i}/{len(questions_data)}] Evaluating: {question[:80]}...")
            
            result = self.evaluate_single_question(question, expected)
            results.append(result)
            
            # Update counters
            status_counts[result.status] = status_counts.get(result.status, 0) + 1
            total_scores["retrieval"] += result.retrieval_score
            total_scores["relevance"] += result.answer_relevance
            total_scores["accuracy"] += result.factual_accuracy
            total_scores["completeness"] += result.completeness
            total_scores["overall"] += result.overall_score
            
            print(f"→ Overall: {result.overall_score:.3f} | Status: {result.status}")
            print(f"  Retrieval: {result.retrieval_score:.3f} | Relevance: {result.answer_relevance:.3f}")
            
            # Periodic save
            if i % 50 == 0:
                self.save_results(results, f"{output_prefix}_partial")
        
        # Calculate averages
        n = len(results)
        avg_scores = {k: round(v/n, 3) for k, v in total_scores.items()}
        
        # Final save
        self.save_results(results, output_prefix)
        
        # Print summary
        print(f"\n✅ Evaluation Complete!")
        print(f"Questions evaluated: {n}")
        print("Average Scores:", avg_scores)
        print("Status Distribution:", status_counts)
        
        return results
    
    def save_results(self, results: List[EvaluationResult], filename_prefix: str):
        """Save results in multiple formats"""
        
        # Convert to dict for saving
        results_data = []
        for r in results:
            results_data.append({
                "question": r.question,
                "generated_answer": r.generated_answer,
                "expected_answer": r.expected_answer,
                "retrieval_score": r.retrieval_score,
                "answer_relevance": r.answer_relevance,
                "factual_accuracy": r.factual_accuracy,
                "completeness": r.completeness,
                "overall_score": r.overall_score,
                "status": r.status,
                "top_chunk_preview": r.top_chunk_preview,
                "feedback": r.feedback
            })
        
        # Save CSV
        csv_file = f"{filename_prefix}.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            if results_data:
                writer = csv.DictWriter(f, fieldnames=results_data[0].keys())
                writer.writeheader()
                writer.writerows(results_data)
        
        # Save JSON
        json_file = f"{filename_prefix}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Results saved: {csv_file}, {json_file}")


def load_questions_from_json(filepath: str) -> List[Dict]:
    """
    Flexibly load questions from JSON file with multiple format support
    """
    print(f"🔍 Attempting to load questions from: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return None
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"✅ JSON file loaded successfully")
        print(f"📊 Data type: {type(data)}")
        
        # Handle different JSON structures
        questions_data = []
        
        # Case 1: Already a list of dicts
        if isinstance(data, list):
            print(f"✅ Found list with {len(data)} items")
            questions_data = data
            
        # Case 2: Dict with a "questions" key
        elif isinstance(data, dict) and "questions" in data:
            print(f"✅ Found 'questions' key with {len(data['questions'])} items")
            questions_data = data["questions"]
            
        # Case 3: Dict with other possible keys
        elif isinstance(data, dict):
            # Try common key names
            possible_keys = ["data", "items", "question_list", "queries", "test_cases"]
            for key in possible_keys:
                if key in data:
                    print(f"✅ Found '{key}' key with {len(data[key])} items")
                    questions_data = data[key]
                    break
            
            # If no known key found, check if all values are lists
            if not questions_data:
                list_values = [v for v in data.values() if isinstance(v, list)]
                if list_values:
                    questions_data = list_values[0]
                    print(f"✅ Using first list value with {len(questions_data)} items")
        
        if not questions_data:
            print(f"❌ Could not extract questions from JSON structure")
            print(f"Available keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            return None
        
        # Normalize the format
        normalized = []
        for item in questions_data:
            if isinstance(item, dict):
                # Extract question and expected answer with flexible key names
                q = (item.get("question") or 
                     item.get("query") or 
                     item.get("text") or 
                     item.get("q") or "")
                
                exp = (item.get("expected_answer") or 
                       item.get("answer") or 
                       item.get("expected") or 
                       item.get("ground_truth") or "")
                
                # Also preserve source and id if available
                source = item.get("source", "")
                question_id = item.get("id", "")
                
                normalized.append({
                    "question": q,
                    "expected_answer": exp,
                    "source": source,
                    "id": question_id
                })
            elif isinstance(item, str):
                # Simple string questions
                normalized.append({
                    "question": item,
                    "expected_answer": "",
                    "source": "",
                    "id": ""
                })
        
        print(f"✅ Successfully normalized {len(normalized)} questions")
        
        # Show first question as example
        if normalized:
            print(f"\n📝 First question preview:")
            print(f"   ID: {normalized[0].get('id', 'N/A')}")
            print(f"   Q: {normalized[0]['question'][:100]}...")
            print(f"   Source: {normalized[0].get('source', 'N/A')}")
            if normalized[0]['expected_answer']:
                print(f"   A: {normalized[0]['expected_answer'][:100]}...")
        
        return normalized
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        traceback.print_exc()
        return None


# -----------------------------
# 🚀 Main execution
# -----------------------------
def main():
    evaluator = RAGEvaluator()
    
    # Try multiple possible locations for the questions file
    possible_paths = [
        "src/Constitution_Que.json",                # In src folder
        "../Criminal_Law_Que.json",                 # Parent directory
        "data/Criminal_Law_Que.json",               # In data folder
        "questions/Criminal_Law_Que.json",          # In questions folder
    ]
    
    questions_data = None
    questions_file = None
    
    # Try each path
    for path in possible_paths:
        if os.path.exists(path):
            print(f"✅ Found file at: {path}")
            questions_file = path
            questions_data = load_questions_from_json(path)
            break
    
    if questions_data is None and questions_file is None:
        # Print current directory to help user locate the file
        print(f"\n📁 Current working directory: {os.getcwd()}")
        print(f"📁 Files in current directory:")
        try:
            files = [f for f in os.listdir('.') if f.endswith('.json')]
            for f in files:
                print(f"   - {f}")
        except:
            pass
        
        print(f"\n❓ Could not find Criminal_Law_Que.json in any expected location.")
        print(f"💡 Please ensure the file exists or provide the correct path.")
    
    if questions_data is None:
        print(f"\n⚠️  Using fallback questions since file could not be loaded")
        questions_data = [
            {
                "question": "What is the short title and commencement date of the Protection of Women from Domestic Violence Act, 2005?",
                "expected_answer": "The Act is called the Protection of Women from Domestic Violence Act, 2005, and it came into force on 26th October, 2006."
            },
            {
                "question": "How does the Act define 'aggrieved person' and 'domestic relationship'?",
                "expected_answer": "An 'aggrieved person' means any woman who is, or has been, in a domestic relationship with the respondent and alleges to have been subjected to domestic violence. A 'domestic relationship' means a relationship between two persons who live or have lived together in a shared household, being related by consanguinity, marriage, a relationship in the nature of marriage, adoption, or as family members in a joint family."
            }
        ]
    
    # Run evaluation
    results = evaluator.run_evaluation(questions_data, "enhanced_evaluation")
    
    return results

if __name__ == "__main__":
    main()