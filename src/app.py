import streamlit as st
import streamlit.components.v1 as components
import os
import base64

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(
    page_title="Lexora | Legal AI Assistant",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------
# Hide Streamlit UI and remove padding
# -------------------------------------------------
st.markdown("""
<style>
/* Hide Streamlit elements */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
section[data-testid="stSidebar"] {display: none;}
.stApp > header {display: none;}

/* Remove ALL padding and margins */
.main > div {
    padding: 0 !important;
    margin: 0 !important;
}
.block-container {
    padding: 0 !important;
    margin: 0 !important;
    max-width: 100% !important;
}
.element-container {
    padding: 0 !important;
    margin: 0 !important;
}
.stApp {
    margin: 0 !important;
    padding: 0 !important;
}

/* Remove iframe padding */
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

# -------------------------------------------------
# Query param routing
# -------------------------------------------------
page = st.query_params.get("page", "landing")

if page == "login":
    st.switch_page("pages/login.py")

elif page == "signup":
    st.switch_page("pages/signup.py")

elif page == "app":
    st.switch_page("pages/ui_integrated.py") 

# -------------------------------------------------
# Paths
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")

# -------------------------------------------------
# Helper function to encode images
# -------------------------------------------------
def get_base64_image(image_path):
    """Convert image to base64 string"""
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
            # Determine the image type from extension
            ext = os.path.splitext(image_path)[1].lower()
            if ext == '.png':
                return f"data:image/png;base64,{data}"
            elif ext in ['.jpg', '.jpeg']:
                return f"data:image/jpeg;base64,{data}"
            elif ext == '.gif':
                return f"data:image/gif;base64,{data}"
            elif ext == '.webp':
                return f"data:image/webp;base64,{data}"
    return ""

# -------------------------------------------------
# Load CSS
# -------------------------------------------------
css_content = ""
css_path = os.path.join(STATIC_DIR, "styles.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

# -------------------------------------------------
# Load HTML and replace image paths
# -------------------------------------------------
html_path = os.path.join(STATIC_DIR, "index.html")
if os.path.exists(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
        # Inject CSS with additional fixes for image positioning
        additional_css = """
        <style>
        /* Ensure images are positioned correctly */
        body {
            margin: 0 !important;
            padding: 0 !important;
            overflow-x: hidden;
            background: #FCF5ED;
        }
        
        /* Hero section setup */
        .hero {
            position: relative;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        
        .hero-content {
            position: relative;
            z-index: 10;
            text-align: center;
        }
        
        .hero-images {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1;
        }
        
        /* COURTHOUSE IMAGE - Bottom Left, Collapsing with page edge */
        .courthouse-image,
        .image-placeholder.courthouse-image,
        [class*="courthouse"] {
            position: absolute !important;
            left: -80px !important;  /* Extends beyond left edge */
            bottom: -40px !important; /* Extends beyond bottom edge */
            top: auto !important;
            right: auto !important;
            width: auto !important;
            height: auto !important;
            z-index: 5 !important;
            transform: none !important;
        }
        
        .courthouse-image img,
        .image-placeholder.courthouse-image img,
        [class*="courthouse"] img {
            width: auto !important;
            height: 70vh !important;
            max-height: 600px !important;
            min-height: 400px !important;
            object-fit: contain !important;
            object-position: bottom left !important;
            display: block !important;
            opacity: 0.9;
        }
        
        /* Justice/statue image - top right */
        .justice-image,
        .image-placeholder.justice-image {
            position: fixed !important;
            right: -40px !important;
            top: -20px !important;
            bottom: auto !important;
            left: auto !important;
            z-index: 5 !important;
        }
        
        .justice-image img,
        .image-placeholder.justice-image img {
            width: auto !important;
            height: 50vh !important;
            max-height: 450px !important;
            object-fit: contain !important;
            opacity: 0.85;
        }
        
        /* Ensure proper stacking */
        nav {
            position: relative;
            z-index: 100;
        }
        
        /* Responsive adjustments */
        @media (max-width: 1200px) {
            .courthouse-image,
            .image-placeholder.courthouse-image,
            [class*="courthouse"] {
                left: -100px !important;
                bottom: -60px !important;
            }
            
            .courthouse-image img,
            .image-placeholder.courthouse-image img,
            [class*="courthouse"] img {
                height: 55vh !important;
                max-height: 450px !important;
            }
        }
        
        @media (max-width: 768px) {
            .courthouse-image,
            .image-placeholder.courthouse-image,
            [class*="courthouse"] {
                left: -120px !important;
                bottom: -80px !important;
            }
            
            .courthouse-image img,
            .image-placeholder.courthouse-image img,
            [class*="courthouse"] img {
                height: 45vh !important;
                max-height: 350px !important;
                min-height: 250px !important;
            }
            
            .justice-image,
            .image-placeholder.justice-image {
                display: none !important;
            }
        }
        </style>
        """
        
        # Inject both CSS files
        if css_content and "</head>" in html_content:
            html_content = html_content.replace(
                "</head>", 
                f"<style>{css_content}</style>{additional_css}</head>"
            )
        
        # Replace all image references with base64
        image_mappings = {
            "images/courthouse.png": os.path.join(IMAGES_DIR, "courthouse.png"),
            "images/jg1.png": os.path.join(IMAGES_DIR, "jg1.png"),
            "images/jg2.png": os.path.join(IMAGES_DIR, "jg2.png"),
            "images/demon.png": os.path.join(IMAGES_DIR, "demon.png"),
            "images/review.png": os.path.join(IMAGES_DIR, "review.png"),
            "images/review2.png": os.path.join(IMAGES_DIR, "review2.png"),
            "images/review3.png": os.path.join(IMAGES_DIR, "review3.png"),
        }
        
        # Replace each image source with base64
        for img_src, img_path in image_mappings.items():
            base64_img = get_base64_image(img_path)
            if base64_img:
                html_content = html_content.replace(
                    f'src="{img_src}"',
                    f'src="{base64_img}"'
                )
                print(f"✅ Replaced {img_src}")
            else:
                print(f"⚠️ Image not found: {img_path}")
        
        # Render the HTML with full viewport height
        components.html(
            html_content,
            height=2000,  # Increased height
            scrolling=True
        )
else:
    st.error("❌ index.html not found")