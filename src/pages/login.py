# src/pages/login.py
import streamlit as st
import streamlit.components.v1 as components
import pyrebase
import time
import os
import base64


# ✅ Firebase Configuration
# Try Streamlit secrets first (for cloud), fallback to hardcoded (for local)
try:
    firebase_config = {
        "apiKey": st.secrets["FIREBASE_API_KEY"],
        "authDomain": st.secrets["FIREBASE_AUTH_DOMAIN"],
        "projectId": st.secrets["FIREBASE_PROJECT_ID"],
        "storageBucket": st.secrets["FIREBASE_STORAGE_BUCKET"],
        "messagingSenderId": st.secrets["FIREBASE_MESSAGING_SENDER_ID"],
        "appId": st.secrets["FIREBASE_APP_ID"],
        "measurementId": st.secrets.get("FIREBASE_MEASUREMENT_ID", ""),
        "databaseURL": st.secrets.get("FIREBASE_DATABASE_URL", "")
    }
except:
    firebase_config = {
        "apiKey": "AIzaSyCfnLLLs9pPInFZPfsYbFclXNVKtYShAqY",
        "authDomain": "legal-ai-assistant-d26ca.firebaseapp.com",
        "projectId": "legal-ai-assistant-d26ca",
        "storageBucket": "legal-ai-assistant-d26ca.firebasestorage.app",
        "messagingSenderId": "799641895027",
        "appId": "1:799641895027:web:03247ff5a54c0ad2476a06",
        "measurementId": "G-E4W3G50M8X",
        "databaseURL": ""
    }

firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()


# ✅ Page Setup
st.set_page_config(page_title="Lexora - Login", page_icon="⚖️", layout="wide")


# Hide Streamlit UI elements
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.block-container {padding: 0 !important; margin: 0 !important; max-width: 100% !important;}
iframe {
    display: block;
    border: none;
    height: 100vh !important;
    width: 100vw !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
}
</style>
""", unsafe_allow_html=True)


# Check for form submission via query params
if "action" in st.query_params:
    action = st.query_params["action"]
    email = st.query_params.get("email", "")
    password = st.query_params.get("password", "")
   
    if action == "login" and email and password:
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            st.session_state["user"] = user
            st.session_state["logged_in"] = True
            st.session_state["question_count"] = 0
            st.session_state["trial_exhausted"] = False
            st.session_state["firestore_initialized"] = True
            st.query_params.clear()
            st.switch_page("pages/ui_integrated.py")
        except Exception as e:
            st.error(f"❌ Login failed: {str(e)}")  # Show actual error
            time.sleep(3)
            st.query_params.clear()
            st.rerun()


# Load your CSS
css_content = """
/* Your complete CSS here */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
.head_container a {
    text-decoration: none;
    color: inherit;
}
.head_container{
      font-family: 'Cinzel', serif;
      font-size: 32px;
      font-weight: 600;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      backdrop-filter: blur(10px);
      z-index: 1000;
      padding: 20px 0px 0px 100px;
      transition: all 0.3s ease-in-out;
      background: transparent;
}


body {
    font-family: -apple-system, BlinkMacSystemFont, 'Poppins', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: #FCF5ED;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
}


.container {
    width: 100%;
    max-width: 400px;
    margin-bottom: 50px;
    text-align: center;
    animation: fadeIn 0.6s ease-out;
}


.logo {
    font-size: 32px;
    font-weight: 600;
    letter-spacing: 2px;
    color: #1a1a2e;
    margin-bottom: 60px;
    text-transform: uppercase;
}


h1 {
    font-size: 32px;
    font-weight: 600;
    color: #1a1a2e;
    margin-bottom: 50px;
    line-height: 1.2;
}


.subtitle {
    font-size: 16px;
    color: #4a4a5e;
    margin-bottom: 40px;
}


.form-container {
    width: 100%;
}


.input-group {
    margin-bottom: 20px;
}


input {
    width: 100%;
    padding: 16px 20px;
    border: 2px solid #e8e8f0;
    border-radius: 50px;
    font-size: 16px;
    background-color: rgba(255, 255, 255, 0.7);
    transition: all 0.3s ease;
    outline: none;
}


.no-acc {
    padding: 16px;
    font-size: 14px;
}


.no-acc a {
    color: #1a2332;
    text-decoration: underline;
}


input::placeholder {
    color: #9a9aaa;
}


input:focus {
    border-color: #d8b8b8;
    background-color: rgba(255, 255, 255, 0.9);
}


input[type="email"] {
    background-color: rgba(255, 255, 255, 0.9);
    color: #4a4a5e;
}


.continue-btn {
    width: 100%;
    padding: 16px 20px;
    background-color: #1a2332;
    color: white;
    border: none;
    border-radius: 50px;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
    margin-top: 10px;
}


.continue-btn:hover {
    background-color: #0f1720;
    transform: translateY(-2px);
    box-shadow: 0 5px 20px rgba(26, 35, 50, 0.3);
}


.continue-btn:active {
    transform: translateY(0);
}


.footer-links {
    position: fixed;
    bottom: 30px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 20px;
    font-size: 14px;
}


.footer-links a {
    color: #9a9aaa;
    text-decoration: none;
    transition: color 0.3s ease;
}


.footer-links a:hover {
    color: #4a4a5e;
}


.footer-links span {
    color: #d8d8e0;
}


@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
"""


# HTML with integrated Firebase form handling
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&display=swap" rel="stylesheet">
    <title>Lexora - Login</title>
    <style>
        {css_content}
    </style>
</head>
<body>
    <header>
        <nav class="head_container">
            <div>
                <a href="/?page=landing"><strong>LEXORA</strong></a>
            </div>
        </nav>
    </header>
   
    <div class="container">
        <h1>Log in to your account</h1>
        <p class="subtitle">Enter your credentials</p>
       
        <form class="form-container" onsubmit="handleLogin(event)">
            <div class="input-group">
                <input
                    type="email"
                    id="email"
                    placeholder="xyz@email.com"
                    required
                >
            </div>
           
            <div class="input-group">
                <input
                    type="password"
                    id="password"
                    placeholder="Password"
                    required
                >
            </div>
           
            <button type="submit" class="continue-btn">Continue</button>
        </form>
       
        <div class="no-acc">Don't have an account? <a href="/?page=signup">Sign up</a></div>
    </div>
   
    <div class="footer-links">
        <a href="#">Terms of Use</a>
        <span>|</span>
        <a href="#">Privacy Policy</a>
    </div>
   
    <script>
        function handleLogin(e) {{
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
           
            // Submit to Streamlit via URL params
            window.location.href = `?action=login&email=${{encodeURIComponent(email)}}&password=${{encodeURIComponent(password)}}`;
        }}
    </script>
</body>
</html>
"""


# Render your HTML
components.html(html_content, height=800, scrolling=False)



