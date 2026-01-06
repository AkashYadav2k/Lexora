# Debug version with detailed error reporting
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

print(f"🔑 OpenAI Key loaded: {'✅ Yes' if OPENAI_KEY else '❌ No'}")

try:
    emb = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_KEY)
    llm = ChatOpenAI(model="gpt-4", openai_api_key=OPENAI_KEY, temperature=0)
    print("✅ OpenAI clients initialized successfully")
except Exception as e:
    print(f"❌ Error initializing OpenAI clients: {e}")
    emb = None
    llm = None

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
    error_details: str = ""

class RAGEvaluator:
    def __init__(self):
        self.results: List[EvaluationResult] = []
        self.debug_mode = True
        
    def test_individual_components(self, question: str):
        """Test each component of the RAG pipeline separately"""
        print(f"\n🔍 DEBUGGING COMPONENTS for: {question[:60]}...")
        
        # Test 1: Multi-query retrieval
        try:
            print("1️⃣ Testing multi_query_retrieve...")
            base_chunks = multi_query_retrieve(question, k=5)
            print(f"   ✅ Retrieved {len(base_chunks)} base chunks")
            if base_chunks:
                print(f"   📄 Sample chunk: {str(base_chunks[0])[:150]}...")
        except Exception as e:
            print(f"   ❌ multi_query_retrieve failed: {e}")
            traceback.print_exc()
            return None, f"multi_query_retrieve error: {e}"
        
        # Test 2: Expansion
        try:
            print("2️⃣ Testing expand_with_links...")
            expanded = expand_with_links(base_chunks, k=3)
            print(f"   ✅ Expanded to {len(expanded)} chunks")
        except Exception as e:
            print(f"   ❌ expand_with_links failed: {e}")
            traceback.print_exc()
            return None, f"expand_with_links error: {e}"
        
        # Test 3: Reranking
        try:
            print("3️⃣ Testing rerank_chunks...")
            top_chunks = rerank_chunks(question, expanded, top_k=5)
            print(f"   ✅ Reranked to {len(top_chunks)} top chunks")
        except Exception as e:
            print(f"   ❌ rerank_chunks failed: {e}")
            traceback.print_exc()
            return None, f"rerank_chunks error: {e}"
        
        # Test 4: Answer generation
        try:
            print("4️⃣ Testing answer_question...")
            generated_answer = answer_question(question)
            if isinstance(generated_answer, bytes):
                generated_answer = generated_answer.decode("utf-8", errors="ignore")
            generated_answer = (generated_answer or "").strip()
            print(f"   ✅ Generated answer ({len(generated_answer)} chars)")
            print(f"   📝 Answer preview: {generated_answer[:100]}...")
        except Exception as e:
            print(f"   ❌ answer_question failed: {e}")
            traceback.print_exc()
            return None, f"answer_question error: {e}"
        
        # Test 5: Embeddings (if available)
        if emb:
            try:
                print("5️⃣ Testing embeddings...")
                qvec = emb.embed_query(question)
                print(f"   ✅ Question embedding shape: {np.array(qvec).shape}")
                
                if top_chunks:
                    text = top_chunks[0].get("metadata", {}).get("text") or top_chunks[0].get("text", "")
                    if text:
                        tvec = emb.embed_documents([text])[0]
                        sim = float(np.dot(qvec, tvec) / (np.linalg.norm(qvec) * np.linalg.norm(tvec)))
                        print(f"   ✅ Similarity score: {sim:.3f}")
                    else:
                        print("   ⚠️ No text found in top chunk")
            except Exception as e:
                print(f"   ❌ Embeddings failed: {e}")
                traceback.print_exc()
        
        return (top_chunks, generated_answer), "All components working"
    
    def evaluate_answer_quality_safe(self, question: str, answer: str, expected: str = "") -> Dict[str, float]:
        """Safe version of answer quality evaluation with fallbacks"""
        
        if not llm:
            print("   ⚠️ LLM not available, using fallback scoring")
            return {"relevance": 0.5, "completeness": 0.5, "accuracy": 0.5}
        
        try:
            # Simplified relevance check
            relevance_prompt = f"""
            Question: {question}
            Answer: {answer}
            
            Does this answer address the question? Reply with just a number 0-1:
            1.0 = fully addresses the question
            0.5 = partially addresses it  
            0.0 = doesn't address it
            """
            
            try:
                relevance_response = llm.invoke(relevance_prompt)
                relevance_score = float(relevance_response.content.strip())
                relevance_score = min(max(relevance_score, 0.0), 1.0)
            except Exception as e:
                print(f"   ⚠️ Relevance evaluation failed: {e}")
                relevance_score = 0.5
            
            # If we have expected answer, check accuracy
            accuracy_score = 0.5  # default
            if expected and len(expected.strip()) > 5:
                try:
                    accuracy_prompt = f"""
                    Expected: {expected}
                    Generated: {answer}
                    
                    How accurate is the generated answer? Reply with just a number 0-1:
                    1.0 = completely accurate
                    0.5 = partially accurate
                    0.0 = inaccurate
                    """
                    
                    accuracy_response = llm.invoke(accuracy_prompt)
                    accuracy_score = float(accuracy_response.content.strip())
                    accuracy_score = min(max(accuracy_score, 0.0), 1.0)
                except Exception as e:
                    print(f"   ⚠️ Accuracy evaluation failed: {e}")
            
            return {
                "relevance": relevance_score,
                "completeness": relevance_score * 0.9,  # approximation
                "accuracy": accuracy_score
            }
            
        except Exception as e:
            print(f"   ❌ Answer quality evaluation failed: {e}")
            return {"relevance": 0.0, "completeness": 0.0, "accuracy": 0.0}
    
    def evaluate_single_question_debug(self, question: str, expected_answer: str = "") -> EvaluationResult:
        """Debug version with detailed error reporting"""
        
        if not question.strip():
            return EvaluationResult(
                question=question,
                generated_answer="",
                status="Error",
                error_details="Empty question"
            )
        
        print(f"\n🔬 DEBUGGING: {question[:80]}...")
        
        try:
            # Test all components
            components_result, error_msg = self.test_individual_components(question)
            
            if components_result is None:
                return EvaluationResult(
                    question=question,
                    generated_answer="",
                    expected_answer=expected_answer,
                    status="Error",
                    error_details=error_msg,
                    feedback=f"Component failure: {error_msg}"
                )
            
            top_chunks, generated_answer = components_result
            
            # Calculate scores with fallbacks
            retrieval_score = 0.0
            if emb and top_chunks:
                try:
                    qvec = emb.embed_query(question)
                    scores = []
                    
                    for chunk in top_chunks[:3]:
                        text = chunk.get("metadata", {}).get("text") or chunk.get("text", "")
                        if text:
                            tvec = emb.embed_documents([text])[0]
                            sim = float(np.dot(qvec, tvec) / (np.linalg.norm(qvec) * np.linalg.norm(tvec)))
                            scores.append(sim)
                    
                    retrieval_score = max(scores) if scores else 0.0
                except Exception as e:
                    print(f"   ⚠️ Retrieval scoring failed: {e}")
                    retrieval_score = 0.3  # fallback
            
            # Evaluate answer quality
            quality_metrics = self.evaluate_answer_quality_safe(question, generated_answer, expected_answer)
            
            # Calculate overall score
            overall_score = (
                0.2 * retrieval_score +
                0.3 * quality_metrics["relevance"] +
                0.3 * quality_metrics["completeness"] +
                0.2 * quality_metrics["accuracy"]
            )
            
            # Determine status
            if overall_score >= 0.8:
                status = "Excellent"
            elif overall_score >= 0.65:
                status = "Good"
            elif overall_score >= 0.5:
                status = "Acceptable"
            elif overall_score >= 0.3:
                status = "Poor"
            else:
                status = "Insufficient"
            
            result = EvaluationResult(
                question=question,
                generated_answer=generated_answer,
                expected_answer=expected_answer,
                retrieval_score=round(retrieval_score, 3),
                answer_relevance=round(quality_metrics["relevance"], 3),
                factual_accuracy=round(quality_metrics["accuracy"], 3),
                completeness=round(quality_metrics["completeness"], 3),
                overall_score=round(overall_score, 3),
                status=status,
                top_chunk_preview=self.safe_preview(
                    top_chunks[0].get("metadata", {}).get("text", "") if top_chunks else ""
                ),
                feedback="Successfully processed"
            )
            
            return result
            
        except Exception as e:
            print(f"❌ MAJOR ERROR in evaluate_single_question_debug:")
            traceback.print_exc()
            
            return EvaluationResult(
                question=question,
                generated_answer="",
                expected_answer=expected_answer,
                status="Error",
                error_details=str(e),
                feedback=f"Evaluation error: {str(e)}"
            )
    
    def safe_preview(self, text: str, length: int = 200) -> str:
        if not text:
            return ""
        return text.replace("\n", " ").strip()[:length]
    
    def run_debug_evaluation(self, questions_data: List[Dict], max_questions: int = 10):
        """Run evaluation in debug mode with detailed logging"""
        
        print(f"🚀 STARTING DEBUG EVALUATION")
        print(f"   Processing first {max_questions} questions")
        print(f"   Total questions available: {len(questions_data)}")
        
        results = []
        
        for i, item in enumerate(questions_data[:max_questions], 1):
            if isinstance(item, dict):
                question = item.get("question", "")
                expected = item.get("expected_answer", "")
            else:
                question = str(item)
                expected = ""
            
            print(f"\n{'='*80}")
            print(f"🔍 QUESTION {i}/{max_questions}")
            print(f"{'='*80}")
            
            result = self.evaluate_single_question_debug(question, expected)
            results.append(result)
            
            print(f"\n📊 RESULT SUMMARY:")
            print(f"   Status: {result.status}")
            print(f"   Overall Score: {result.overall_score}")
            print(f"   Retrieval: {result.retrieval_score}")
            print(f"   Relevance: {result.answer_relevance}")
            if result.error_details:
                print(f"   ❌ Error: {result.error_details}")
            
            # Stop on first few errors to debug
            if result.status == "Error" and i <= 3:
                print(f"\n🛑 STOPPING after {i} questions due to consistent errors")
                print("Please fix the underlying issues before continuing.")
                break
        
        return results

def main_debug():
    """Main function for debugging"""
    print("🔧 RUNNING EVALUATION IN DEBUG MODE")
    print("="*60)
    
    evaluator = RAGEvaluator()
    
    # Load questions
    questions_file = "auto_generated_questions.json"
    if os.path.exists(questions_file):
        with open(questions_file, "r", encoding="utf-8") as f:
            questions_data = json.load(f)
            print(f"📁 Loaded {len(questions_data)} questions")
    else:
        print(f"❌ Questions file {questions_file} not found!")
        return
    
    # Test with first 5 questions only
    results = evaluator.run_debug_evaluation(questions_data, max_questions=5)
    
    # Save debug results
    debug_results = []
    for r in results:
        debug_results.append({
            "question": r.question,
            "generated_answer": r.generated_answer,
            "status": r.status,
            "overall_score": r.overall_score,
            "retrieval_score": r.retrieval_score,
            "answer_relevance": r.answer_relevance,
            "error_details": r.error_details,
            "feedback": r.feedback
        })
    
    with open("debug_results.json", "w", encoding="utf-8") as f:
        json.dump(debug_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Debug results saved to debug_results.json")
    print(f"\n🎯 DEBUGGING COMPLETE. Check the detailed logs above.")
    
    return results

if __name__ == "__main__":
    main_debug()