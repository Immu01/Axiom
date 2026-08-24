import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables (ignored on Render if using environment dashboard, used locally)
load_dotenv()

app = FastAPI(title="Axiom API")

# Configure CORS (Allow localhost for dev, and we can add your GitHub Pages URL later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For now, allow all origins so GitHub Pages can connect easily
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Primary Model (Gemini)
try:
    llm_primary = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash", 
        temperature=0.7
    )
except Exception as e:
    logger.error(f"Failed to initialize Gemini: {e}")
    llm_primary = None

# Initialize Fallback Model (Groq)
try:
    llm_fallback = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.7
    )
except Exception as e:
    logger.error(f"Failed to initialize Groq: {e}")
    llm_fallback = None

class ChatRequest(BaseModel):
    message: str

def extract_text(content):
    if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and "text" in content[0]:
        return content[0]["text"]
    return str(content)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Axiom Backend v1"}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    # 1. Try Primary Provider (Gemini)
    if llm_primary:
        try:
            logger.info("Attempting to use Primary Model (Gemini)...")
            response = llm_primary.invoke(request.message)
            clean_text = extract_text(response.content)
            return {"response": clean_text, "provider": "gemini"}
        except Exception as e:
            logger.warning(f"Primary model failed: {e}. Falling back to Groq...")

    # 2. Try Fallback Provider (Groq)
    if llm_fallback:
        try:
            logger.info("Attempting to use Fallback Model (Groq)...")
            response = llm_fallback.invoke(request.message)
            clean_text = extract_text(response.content)
            return {"response": clean_text, "provider": "groq"}
        except Exception as e:
            logger.error(f"Fallback model also failed: {e}")
            
    # 3. All failed
    raise HTTPException(
        status_code=503, 
        detail="Axiom is temporarily busy. All AI providers are unavailable. Please try again later."
    )
