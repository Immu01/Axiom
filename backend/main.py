import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Axiom API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    llm_primary = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        temperature=0.7
    )
except Exception as e:
    logger.error(f"Failed to initialize Gemini: {e}")
    llm_primary = None

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
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(item["text"])
            elif hasattr(item, "text") and item.text:
                parts.append(item.text)
        if parts:
            return "".join(parts).strip()
    if hasattr(content, "text") and content.text:
        return str(content.text).strip()
    return str(content).strip()

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Axiom Backend v1"}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    if llm_primary:
        try:
            logger.info("Attempting to use Primary Model (Gemini)...")
            response = llm_primary.invoke(request.message)
            clean_text = extract_text(response.content)
            return {"response": clean_text, "provider": "gemini"}
        except Exception as e:
            logger.warning(f"Primary model failed: {e}. Falling back to Groq...")

    if llm_fallback:
        try:
            logger.info("Attempting to use Fallback Model (Groq)...")
            response = llm_fallback.invoke(request.message)
            clean_text = extract_text(response.content)
            return {"response": clean_text, "provider": "groq"}
        except Exception as e:
            logger.error(f"Fallback model also failed: {e}")

    raise HTTPException(
        status_code=503,
        detail="Axiom is temporarily busy. All AI providers are unavailable. Please try again later."
    )
