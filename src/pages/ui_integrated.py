"""
Lexora - Legal AI Assistant
Main Chat Interface - WITH FREE TRIAL SYSTEM (5 questions for anonymous users)
With Firestore persistent tracking (users can't bypass by refreshing)
"""

import streamlit as st
import random
import sys
import os
import re
import hashlib
import json
from datetime import datetime

# -------------------------------------------------
# Page config - MUST be first Streamlit command
# -------------------------------------------------
st.set_page_config(
    page_title="Lexora | Legal AI Assistant",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------
# Import RAG System
# -------------------------------------------------
try:
    from chat import answer_question
    RAG_AVAILABLE = True
    print("✅ RAG system loaded successfully")
except ImportError as e:
    RAG_AVAILABLE = False
    print(f"⚠️ RAG system not available: {e}")
    print("Running in demo mode with hardcoded responses")

# -------------------------------------------------
# Firebase/Firestore Setup for Persistent Tracking
# -------------------------------------------------
FIRESTORE_AVAILABLE = False
db = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        try:
            # Try Streamlit secrets first (for cloud deployment)
            import streamlit as st
            cred = credentials.Certificate(dict(st.secrets["FIREBASE_SERVICE_ACCOUNT"]))
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized from Streamlit secrets")
        except:
            # Fallback to local file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(current_dir)
            possible_paths = [
                os.path.join(src_dir, "serviceAccountKey.json"),
                os.path.join(current_dir, "serviceAccountKey.json"),
                "serviceAccountKey.json",
            ]
            
            service_account_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    service_account_path = path
                    break
            
            if service_account_path:
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                print(f"✅ Firebase initialized from: {service_account_path}")
            else:
                print("⚠️ serviceAccountKey.json not found")

    if firebase_admin._apps:
        db = firestore.client()
        FIRESTORE_AVAILABLE = True
        print("✅ Firestore connected successfully")

except ImportError as e:
    print(f"⚠️ Firebase Admin SDK not installed: {e}")
except Exception as e:
    print(f"⚠️ Firestore initialization error: {e}")

# -------------------------------------------------
# FREE TRIAL CONFIGURATION
# -------------------------------------------------
FREE_TRIAL_LIMIT = 5  # Number of free questions for anonymous users

# -------------------------------------------------
# Session State Initialization
# -------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "history" not in st.session_state:
    st.session_state.history = []
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "question_count" not in st.session_state:
    st.session_state.question_count = 0
if "show_signup_modal" not in st.session_state:
    st.session_state.show_signup_modal = False
if "trial_exhausted" not in st.session_state:
    st.session_state.trial_exhausted = False
if "fingerprint" not in st.session_state:
    st.session_state.fingerprint = None
if "firestore_initialized" not in st.session_state:
    st.session_state.firestore_initialized = False
if "current_examples" not in st.session_state:
    st.session_state.current_examples = [
        "Explain the concept of secularism in Indian Constitution",
        "What are the fundamental duties of citizens?",
        "Explain Article 21 - Right to Life and Personal Liberty",
        "What are the fundamental rights guaranteed by the Indian Constitution?"
    ]
# -------------------------------------------------
# RESET TRIAL FLAGS FOR LOGGED-IN USERS
# -------------------------------------------------
if st.session_state.logged_in:
    st.session_state.trial_exhausted = False
    st.session_state.question_count = 0 


# -------------------------------------------------
# DEBUG: Check login status (REMOVE AFTER TESTING)
# -------------------------------------------------
#st.warning(f"DEBUG: logged_in={st.session_state.logged_in}, user={st.session_state.user}, trial_exhausted={st.session_state.trial_exhausted}")
# -------------------------------------------------
# CSS Styling (with FIXED modal styles)
# -------------------------------------------------
st.markdown("""
<style>
    /* Import Poppins Font */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');
    
    /* Hide Streamlit Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    div[data-testid="stToolbar"] {display: none;}
    section[data-testid="stSidebar"] {display: none !important;}
    [data-testid="collapsedControl"] {display: none !important;}
    
    /* Apply Poppins globally */
    html, body, [class*="css"] {
        font-family: 'Poppins', sans-serif !important;
    }
    
    /* Main App Background */
    .stApp {
        background: #FCF5ED;
    }
    
    /* Make the app fill viewport height without scroll */
    .main .block-container {
        padding: 0 !important;
        max-width: 100% !important;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
    }
    
    /* Welcome Header */
    .welcome-header {
        font-family: 'Poppins', sans-serif;
        font-size: 2.2rem;
        font-weight: 600;
        color: #1A2B3C;
        text-align: center;
        margin-bottom: 8px;
        line-height: 1.3;
    }
    
    .welcome-subtitle {
        font-family: 'Poppins', sans-serif;
        font-size: 1rem;
        font-weight: 400;
        color: #4A5B6C;
        text-align: center;
        margin-bottom: 24px;
    }
    
    /* Free Trial Badge */
    .trial-badge {
        text-align: center;
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 13px;
        margin-bottom: 20px;
        display: inline-block;
        font-weight: 500;
    }
    
    .trial-active {
        background: linear-gradient(135deg, #E0F2FE, #BAE6FD);
        color: #0369A1;
        border: 1px solid #7DD3FC;
    }
    
    .trial-warning {
        background: linear-gradient(135deg, #FEF3C7, #FDE68A);
        color: #92400E;
        border: 1px solid #FCD34D;
    }
    
    .trial-exhausted {
        background: linear-gradient(135deg, #FEE2E2, #FECACA);
        color: #DC2626;
        border: 1px solid #F87171;
    }
    
    .logged-in-badge {
        background: linear-gradient(135deg, #D1FAE5, #A7F3D0);
        color: #065F46;
        border: 1px solid #6EE7B7;
    }
    
    /* Chat Messages */
    .chat-message {
        display: flex;
        gap: 14px;
        margin-bottom: 24px;
        max-width: 100%;
    }
    
    .message-avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
    }
    
    .message-avatar.user {
        background: linear-gradient(135deg, #FFB347, #FFCC80);
    }
    
    .message-avatar.assistant {
        background: linear-gradient(135deg, #3B82C4, #6BA5D7);
    }
    
    .message-content {
        flex: 1;
        padding-top: 6px;
        font-family: 'Poppins', sans-serif;
    }
    
    .message-content.user {
        font-weight: 500;
        font-size: 16px;
        color: #1A2B3C;
    }
    
    .message-content.assistant {
        font-size: 15px;
        line-height: 1.7;
        color: #4A5B6C;
        font-weight: 400;
    }
    
    .message-content.assistant p {
        margin-bottom: 12px;
    }
    
    .message-content.assistant ol,
    .message-content.assistant ul {
        margin: 12px 0;
        padding-left: 24px;
    }
    
    .message-content.assistant li {
        margin-bottom: 8px;
        line-height: 1.6;
    }
    
    .message-content.assistant strong {
        color: #1A2B3C;
        font-weight: 600;
    }
    
    /* Chat Input Container */
    .stChatInput {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        padding: 20px 40px 30px !important;
        background: #FCF5ED;
        z-index: 1000 !important;
    }
    
    .stChatInput > div {
        max-width: 800px !important;
        margin: 0 auto !important;
        background: #F0F2F6 !important;
        border: 2px solid #E8DDD4 !important;
        border-radius: 16px !important;
        box-shadow: 0 4px 24px rgba(139, 109, 76, 0.12) !important;
        transition: all 0.3s ease !important;
    }
    
    .stChatInput > div:focus-within {
        border-color: #C4A484 !important;
        box-shadow: 0 6px 30px rgba(139, 109, 76, 0.2) !important;
        background: #F0F2F6 !important;
    }
    
    .stChatInput textarea {
        font-family: 'Poppins', sans-serif !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        color: #475569 !important;
        background: transparent !important;
    }
    
    .stChatInput textarea::placeholder {
        font-family: 'Poppins', sans-serif !important;
        color: #8B7355 !important;
        opacity: 0.7 !important;
    }
    
    .stChatInput button {
        background: linear-gradient(135deg, #C4A484, #A67C52) !important;
        border: none !important;
        border-radius: 12px !important;
        color: #FFFFFF !important;
        transition: all 0.3s ease !important;
    }
    
    .stChatInput button:hover {
        background: linear-gradient(135deg, #A67C52, #8B6914) !important;
        transform: scale(1.05) !important;
        box-shadow: 0 4px 12px rgba(166, 124, 82, 0.4) !important;
    }
    
    .stChatInput button svg {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }
    
    /* Streamlit Button Overrides */
    .stButton > button {
        background: #FFFBF7 !important;
        border: 1px solid #E8DDD4 !important;
        border-radius: 12px !important;
        color: #1A2B3C !important;
        font-family: 'Poppins', sans-serif !important;
        font-weight: 400 !important;
        padding: 12px 16px !important;
        font-size: 14px !important;
        line-height: 1.4 !important;
        height: auto !important;
        min-height: 50px !important;
        text-align: left !important;
        white-space: normal !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:hover {
        background: #FFF8F0 !important;
        border-color: #C4A484 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(196, 164, 132, 0.25) !important;
    }
    
    /* Small action buttons */
    .small-btn .stButton > button {
        min-height: 36px !important;
        padding: 6px 14px !important;
        border-radius: 50px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
    }
    
    /* Content area with proper spacing for chat input */
    .content-area {
        padding-bottom: 100px;
    }
    
    /* Hide empty space at top */
    .block-container {
        padding-top: 0 !important;
    }
    
    .stVerticalBlock {
        gap: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# Example Questions Pool
# -------------------------------------------------
EXAMPLE_QUESTIONS_POOL = [
    [
        "Explain the concept of secularism in Indian Constitution",
        "What are the fundamental duties of citizens?",
        "Explain Article 21 - Right to Life and Personal Liberty",
        "What are the fundamental rights guaranteed by the Indian Constitution?"
    ],
    [
        "What is habeas corpus?",
        "Explain the right to freedom of religion",
        "What are directive principles of state policy?",
        "What is the preamble of Indian Constitution?"
    ],
    [
        "What is judicial review?",
        "Explain Article 14 - Right to Equality",
        "What is the procedure for constitutional amendments?",
        "What are writs in Indian Constitution?"
    ],
    [
        "What is PIL (Public Interest Litigation)?",
        "Explain separation of powers",
        "What are the functions of the Supreme Court?",
        "What is the role of the Election Commission?"
    ]
]

# -------------------------------------------------
# FIRESTORE TRACKING FUNCTIONS
# -------------------------------------------------
def get_or_create_fingerprint():
    """
    Get fingerprint from session or create new one.
    """
    if st.session_state.fingerprint:
        return st.session_state.fingerprint
    
    # Generate a session-based fingerprint
    import uuid
    fingerprint = str(uuid.uuid4())
    st.session_state.fingerprint = fingerprint
    return fingerprint

def get_question_count_from_firestore(fingerprint: str) -> int:
    """Get question count from Firestore for a fingerprint."""
    if not FIRESTORE_AVAILABLE or db is None:
        return st.session_state.question_count
    
    try:
        doc_ref = db.collection('trial_users').document(fingerprint)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('question_count', 0)
        return 0
    except Exception as e:
        print(f"Firestore read error: {e}")
        return st.session_state.question_count

def save_question_count_to_firestore(fingerprint: str, count: int):
    """Save question count to Firestore."""
    if not FIRESTORE_AVAILABLE or db is None:
        return
    
    try:
        doc_ref = db.collection('trial_users').document(fingerprint)
        doc_ref.set({
            'question_count': count,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'created_at': firestore.SERVER_TIMESTAMP
        }, merge=True)
    except Exception as e:
        print(f"Firestore write error: {e}")

def init_trial_count():
    """Initialize trial count from Firestore on first load."""
    if st.session_state.firestore_initialized:
        return
    
    if not st.session_state.logged_in and FIRESTORE_AVAILABLE:
        fingerprint = get_or_create_fingerprint()
        count = get_question_count_from_firestore(fingerprint)
        st.session_state.question_count = count
        if count >= FREE_TRIAL_LIMIT:
            st.session_state.trial_exhausted = True
    
    st.session_state.firestore_initialized = True

# Initialize on load
init_trial_count()

# -------------------------------------------------
# FREE TRIAL HELPER FUNCTIONS
# -------------------------------------------------
def get_remaining_questions() -> int:
    """Get remaining free questions for anonymous user."""
    if st.session_state.logged_in:
        return -1  # Unlimited for logged-in users
    return max(0, FREE_TRIAL_LIMIT - st.session_state.question_count)

def can_ask_question() -> bool:
    """Check if user can ask a question."""
    if st.session_state.logged_in:
        return True
    return st.session_state.question_count < FREE_TRIAL_LIMIT

def increment_question_count():
    """Increment the question count for anonymous users and save to Firestore."""
    if not st.session_state.logged_in:
        st.session_state.question_count += 1
        # Save to Firestore for persistence
        fingerprint = get_or_create_fingerprint()
        save_question_count_to_firestore(fingerprint, st.session_state.question_count)
        # Check if trial is exhausted after this question
        if st.session_state.question_count >= FREE_TRIAL_LIMIT:
            st.session_state.trial_exhausted = True

def get_trial_status_badge() -> str:
    """Generate HTML for trial status badge."""
    if st.session_state.logged_in:
        return '<span class="trial-badge logged-in-badge">✓ Unlimited Access</span>'
    
    remaining = get_remaining_questions()
    
    if remaining == 0:
        return '<span class="trial-badge trial-exhausted">⚠️ Free trial ended</span>'
    elif remaining <= 2:
        return f'<span class="trial-badge trial-warning">🔥 {remaining} free question{"s" if remaining > 1 else ""} left</span>'
    else:
        return f'<span class="trial-badge trial-active">✨ {remaining} free questions remaining</span>'

# -------------------------------------------------
# IMPROVED: Markdown to HTML Converter
# -------------------------------------------------
def markdown_to_html(text: str) -> str:
    """
    Convert markdown formatting to HTML.
    Handles: **bold**, *italic*, numbered lists, bullet lists, paragraphs
    """
    if not text:
        return "<p>I couldn't generate a response.</p>"
    
    # Step 1: Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Step 2: Convert *italic* to <em> (but not if it's part of a list marker)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    
    # Step 3: Process the text line by line for lists and paragraphs
    lines = text.split('\n')
    html_parts = []
    current_list = None  # 'ol' or 'ul' or None
    current_paragraph = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check if it's a numbered list item (1. or 1) or 2. etc)
        numbered_match = re.match(r'^(\d+)[.\)]\s*(.+)$', stripped)
        # Check if it's a bullet list item
        bullet_match = re.match(r'^[-•*]\s+(.+)$', stripped)
        
        if numbered_match:
            # Close any open paragraph
            if current_paragraph:
                html_parts.append('<p>' + ' '.join(current_paragraph) + '</p>')
                current_paragraph = []
            
            # Start ordered list if not already in one
            if current_list != 'ol':
                if current_list == 'ul':
                    html_parts.append('</ul>')
                html_parts.append('<ol>')
                current_list = 'ol'
            
            html_parts.append(f'<li>{numbered_match.group(2)}</li>')
            
        elif bullet_match:
            # Close any open paragraph
            if current_paragraph:
                html_parts.append('<p>' + ' '.join(current_paragraph) + '</p>')
                current_paragraph = []
            
            # Start unordered list if not already in one
            if current_list != 'ul':
                if current_list == 'ol':
                    html_parts.append('</ol>')
                html_parts.append('<ul>')
                current_list = 'ul'
            
            html_parts.append(f'<li>{bullet_match.group(1)}</li>')
            
        elif stripped == '':
            # Empty line - close paragraph but keep list open
            if current_paragraph:
                html_parts.append('<p>' + ' '.join(current_paragraph) + '</p>')
                current_paragraph = []
                
        else:
            # Regular text - close any open list first
            if current_list:
                html_parts.append(f'</{current_list}>')
                current_list = None
            
            current_paragraph.append(stripped)
    
    # Close any remaining open elements
    if current_list:
        html_parts.append(f'</{current_list}>')
    if current_paragraph:
        html_parts.append('<p>' + ' '.join(current_paragraph) + '</p>')
    
    result = '\n'.join(html_parts)
    
    # If no HTML was generated, wrap in paragraph
    if not result.strip():
        result = f'<p>{text}</p>'
    
    return result


# -------------------------------------------------
# Response Generator - CONNECTED TO RAG
# -------------------------------------------------
def generate_response(question: str) -> tuple:
    """
    Generate response using the actual RAG system.
    Falls back to demo responses if RAG is unavailable.
    """
    
    if RAG_AVAILABLE:
        try:
            # Call the actual RAG pipeline
            answer = answer_question(question, verbose=False)
            
            # Convert markdown to HTML for proper display
            formatted_answer = markdown_to_html(answer)
            
            sources = []
            return formatted_answer, sources
            
        except Exception as e:
            error_msg = f"<p>Sorry, I encountered an error while processing your question: {str(e)}</p>"
            return error_msg, []
    
    else:
        return generate_demo_response(question)


def generate_demo_response(question: str) -> tuple:
    """
    Fallback demo responses when RAG is unavailable.
    """
    question_lower = question.lower()
    
    if "secular" in question_lower:
        response = """<p>Secularism in the Indian Constitution is a fundamental principle that ensures:</p>
        <ol>
            <li><strong>No State Religion:</strong> India does not have an official state religion.</li>
            <li><strong>Equal Treatment:</strong> The state treats all religions equally without favoritism.</li>
            <li><strong>Freedom of Religion:</strong> Every citizen has the right to practice, profess, and propagate any religion.</li>
            <li><strong>No Religious Instruction:</strong> Government-funded educational institutions cannot provide religious instruction.</li>
            <li><strong>Positive Secularism:</strong> Unlike Western secularism that separates religion from state, Indian secularism allows state intervention in religious matters for social reform.</li>
        </ol>"""
        sources = [{"metadata": {"title": "Preamble", "text": "WE, THE PEOPLE OF INDIA..."}}]
    
    elif "dut" in question_lower or "fundamental duties" in question_lower:
        response = """<p>The Fundamental Duties of Indian citizens (Article 51A) include:</p>
        <ol>
            <li>To abide by the Constitution and respect its ideals and institutions.</li>
            <li>To cherish and follow the noble ideals of the freedom struggle.</li>
            <li>To uphold and protect the sovereignty, unity, and integrity of India.</li>
            <li>To defend the country and render national service when called upon.</li>
            <li>To promote harmony and brotherhood among all people of India.</li>
            <li>To preserve the rich heritage of our composite culture.</li>
            <li>To protect and improve the natural environment.</li>
            <li>To develop scientific temper and spirit of inquiry.</li>
            <li>To safeguard public property and abjure violence.</li>
            <li>To strive towards excellence in all spheres of activity.</li>
        </ol>"""
        sources = [{"metadata": {"article_number": "51A", "title": "Fundamental Duties"}}]
    
    elif "article 21" in question_lower or ("life" in question_lower and "liberty" in question_lower):
        response = """<p>Article 21 of the Indian Constitution states:</p>
        <p><strong>"No person shall be deprived of his life or personal liberty except according to procedure established by law."</strong></p>
        <p>Over time, the Supreme Court has expanded its interpretation to include:</p>
        <ol>
            <li><strong>Right to live with dignity</strong></li>
            <li><strong>Right to livelihood</strong></li>
            <li><strong>Right to privacy</strong></li>
            <li><strong>Right to health</strong></li>
            <li><strong>Right to clean environment</strong></li>
            <li><strong>Right to speedy trial</strong></li>
            <li><strong>Right against solitary confinement</strong></li>
            <li><strong>Right to legal aid</strong></li>
        </ol>"""
        sources = [{"metadata": {"article_number": "21", "title": "Protection of life and personal liberty"}}]
    
    elif "fundamental rights" in question_lower:
        response = """<p>The fundamental rights guaranteed by the Indian Constitution include:</p>
        <ol>
            <li><strong>Right to equality:</strong> Everyone is equal before the law.</li>
            <li><strong>Right to freedom:</strong> Freedom of speech, assembly, association, movement, residence, and profession.</li>
            <li><strong>Right against exploitation:</strong> Prohibition of human trafficking and forced labor.</li>
            <li><strong>Right to freedom of religion:</strong> Freedom to practice and propagate religion.</li>
            <li><strong>Cultural and educational rights:</strong> Protection of minority interests.</li>
            <li><strong>Right to constitutional remedies:</strong> Right to approach courts for enforcement.</li>
        </ol>"""
        sources = [{"metadata": {"title": "Part III - Fundamental Rights"}}]
    
    else:
        response = f"""<p>⚠️ <strong>Demo Mode:</strong> RAG system not connected.</p>
        <p>Your question: "<em>{question}</em>"</p>
        <p>To get real answers, ensure chat.py is in the same directory and all dependencies are installed.</p>"""
        sources = []
    
    return response, sources


# -------------------------------------------------
# SHOW SIGNUP MODAL USING STREAMLIT DIALOG
# -------------------------------------------------
@st.dialog("Free Trial Ended", width="small")
def signup_modal():
    """Display the signup/login modal when trial is exhausted."""
    st.markdown("""
        <div style="text-align: center; padding: 10px 0;">
            <div style="font-size: 48px; margin-bottom: 10px;">🔒</div>
            <h2 style="font-family: 'Poppins', sans-serif; font-size: 22px; font-weight: 600; color: #1A2B3C; margin-bottom: 8px;">
                You've used all 5 free questions!
            </h2>
            <p style="font-family: 'Poppins', sans-serif; font-size: 14px; color: #4A5B6C; margin-bottom: 20px;">
                Create a free account to continue exploring Indian Constitutional Law with Lexora.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Benefits box
    st.markdown("""
        <div style="background: #F8F4F0; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
            <div style="font-size: 12px; font-weight: 600; color: #1A2B3C; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">
                What you'll get:
            </div>
            <div style="font-size: 14px; color: #4A5B6C; margin-bottom: 6px;">✅ Unlimited legal questions</div>
            <div style="font-size: 14px; color: #4A5B6C; margin-bottom: 6px;">✅ Save your chat history</div>
            <div style="font-size: 14px; color: #4A5B6C; margin-bottom: 6px;">✅ Export conversations as PDF</div>
            <div style="font-size: 14px; color: #4A5B6C;">✅ Access to all features</div>
        </div>
    """, unsafe_allow_html=True)
    
    # Buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Sign Up Free", use_container_width=True, type="primary"):
            st.switch_page("pages/signup.py")
    with col2:
        if st.button("🔑 Log In", use_container_width=True):
            st.switch_page("pages/login.py")

# Show modal if trial exhausted
if st.session_state.trial_exhausted and not st.session_state.logged_in:
    signup_modal()

# -------------------------------------------------
# MAIN CONTENT AREA
# -------------------------------------------------

# Show example questions only if no chat history
if not st.session_state.history:
    st.markdown("<div style='height: 15vh;'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2.5, 1])
    
    with col2:
        st.markdown('<h1 class="welcome-header">Hey there! I\'m Lexora, your personal law assistant.</h1>', unsafe_allow_html=True)
        st.markdown('<p class="welcome-subtitle">Ask me anything about Indian law, or try one of these examples:</p>', unsafe_allow_html=True)
        
        # Trial Status Badge
        st.markdown(f'<div style="text-align: center;">{get_trial_status_badge()}</div>', unsafe_allow_html=True)
        
        # Example Questions as 2x2 Grid
        examples = st.session_state.current_examples
        
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            if st.button(f"📜 {examples[0]}", key="ex_0", use_container_width=True):
                if can_ask_question():
                    st.session_state.pending_question = examples[0]
                    st.rerun()
                else:
                    st.session_state.trial_exhausted = True
                    st.rerun()
        with row1_col2:
            if st.button(f"⚖️ {examples[1]}", key="ex_1", use_container_width=True):
                if can_ask_question():
                    st.session_state.pending_question = examples[1]
                    st.rerun()
                else:
                    st.session_state.trial_exhausted = True
                    st.rerun()
        
        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            if st.button(f"🏛️ {examples[2]}", key="ex_2", use_container_width=True):
                if can_ask_question():
                    st.session_state.pending_question = examples[2]
                    st.rerun()
                else:
                    st.session_state.trial_exhausted = True
                    st.rerun()
        with row2_col2:
            if st.button(f"📖 {examples[3]}", key="ex_3", use_container_width=True):
                if can_ask_question():
                    st.session_state.pending_question = examples[3]
                    st.rerun()
                else:
                    st.session_state.trial_exhausted = True
                    st.rerun()
        
        # Refresh Examples Button
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        refresh_col1, refresh_col2, refresh_col3 = st.columns([1.5, 1, 1.5])
        with refresh_col2:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="refresh", use_container_width=True):
                current = st.session_state.current_examples
                available = [ex for ex in EXAMPLE_QUESTIONS_POOL if ex != current]
                if available:
                    st.session_state.current_examples = random.choice(available)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

else:
    # Display chat history
    st.markdown('<div class="content-area">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<h1 class="welcome-header">Hey there! I\'m Lexora, your personal law assistant.</h1>', unsafe_allow_html=True)
        
        # Trial Status Badge in chat view
        st.markdown(f'<div style="text-align: center; margin-bottom: 20px;">{get_trial_status_badge()}</div>', unsafe_allow_html=True)
        
        for message in st.session_state.history:
            role = message["role"]
            content = message["content"]
            
            if role == "user":
                st.markdown(f'''
                    <div class="chat-message">
                        <div class="message-avatar user">👤</div>
                        <div class="message-content user">{content}</div>
                    </div>
                ''', unsafe_allow_html=True)
            else:
                st.markdown(f'''
                    <div class="chat-message">
                        <div class="message-avatar assistant">⚖️</div>
                        <div class="message-content assistant">{content}</div>
                    </div>
                ''', unsafe_allow_html=True)
        
        # Action buttons after chat
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
        
        with btn_col1:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("🗑️ Clear Chat", key="clear", use_container_width=True):
                st.session_state.history = []
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        
        with btn_col2:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("📄 Export PDF", key="pdf", use_container_width=True):
                st.toast("PDF export coming soon!", icon="📄")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with btn_col3:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("🔄 New Chat", key="new", use_container_width=True):
                st.session_state.history = []
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        
        with btn_col4:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.session_state.logged_in:
                if st.button("🚪 Logout", key="logout", use_container_width=True):
                    st.session_state.logged_in = False
                    st.session_state.user = None
                    st.session_state.history = []
                    st.switch_page("pages/login.py")
            else:
                if st.button("🔐 Sign Up", key="signup_btn", use_container_width=True):
                    st.switch_page("pages/signup.py")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------
# CHAT INPUT (at bottom)
# -------------------------------------------------
if st.session_state.pending_question:
    user_input = st.session_state.pending_question
    st.session_state.pending_question = None
else:
    # Only show chat input if user can still ask questions
    if can_ask_question():
        user_input = st.chat_input("Enter your legal questions....")
    else:
        user_input = st.chat_input("Sign up to continue asking questions...", disabled=True)
        user_input = None

# Handle input
if user_input:
    # Double-check they can ask (in case of race condition)
    if not can_ask_question():
        st.session_state.trial_exhausted = True
        st.rerun()
    else:
        st.session_state.history.append({"role": "user", "content": user_input})
        
        with st.spinner("Researching legal documents..."):
            response, sources = generate_response(user_input)
        
        st.session_state.history.append({"role": "assistant", "content": response, "sources": sources})
        
        # Increment question count AFTER successful response
        increment_question_count()
        
        st.rerun()