import os
from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AI Study Helper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------- AI Study Helper: Lightweight generators (rule-based) ----------

class GenerateRequest(BaseModel):
    text: str
    type: str  # notes | summary | flashcards | mcqs | quiz | mindmap
    count: Optional[int] = 5

class Flashcard(BaseModel):
    question: str
    answer: str

class MCQ(BaseModel):
    question: str
    options: List[str]
    answer_index: int

class MindMapNode(BaseModel):
    id: str
    label: str
    children: List[str] = []

class GenerateResponse(BaseModel):
    type: str
    notes: Optional[List[str]] = None
    summary: Optional[str] = None
    flashcards: Optional[List[Flashcard]] = None
    mcqs: Optional[List[MCQ]] = None
    quiz: Optional[List[MCQ]] = None
    mindmap: Optional[dict] = None


def _sentences(text: str) -> List[str]:
    raw = [s.strip() for s in text.replace('\n', ' ').split('.')]
    return [s for s in raw if s]


def _top_keywords(text: str, k: int = 8) -> List[str]:
    import re
    stop = set("""
        a an the and or but if then else for to of in on at by with from into over after before during is are was were be been being
    """.split())
    words = re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower())
    freq = {}
    for w in words:
        if w in stop or len(w) < 3:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:k]]


def generate_notes(text: str, n: int = 7) -> List[str]:
    sents = _sentences(text)
    return [f"• {s}" for s in sents[:n]] or ["No content recognized."]


def generate_summary(text: str, n: int = 3) -> str:
    sents = _sentences(text)
    if not sents:
        return "No content provided."
    return " ".join(sents[:n])


def generate_flashcards(text: str, n: int = 5) -> List[Flashcard]:
    keys = _top_keywords(text, max(3, n))
    sents = _sentences(text)
    cards: List[Flashcard] = []
    for i, k in enumerate(keys[:n]):
        hint = next((s for s in sents if k in s.lower()), None)
        answer = hint if hint else f"Definition/context for {k} from the text."
        cards.append(Flashcard(question=f"What is {k}?", answer=answer))
    if not cards:
        cards = [Flashcard(question="What is the main idea?", answer=generate_summary(text))]
    return cards


def generate_mcqs(text: str, n: int = 5) -> List[MCQ]:
    keys = _top_keywords(text, n + 3)
    sents = _sentences(text)
    out: List[MCQ] = []
    for i, k in enumerate(keys[:n]):
        base = next((s for s in sents if k in s.lower()), None) or f"Identify the concept related to '{k}'."
        distractors = [d for d in keys if d != k][:3]
        while len(distractors) < 3:
            distractors.append(f"Not {k}")
        options = distractors + [k]
        import random
        random.shuffle(options)
        answer_index = options.index(k)
        out.append(MCQ(question=base, options=options, answer_index=answer_index))
    if not out:
        out.append(MCQ(question="What is the main idea?", options=["Summary", "Detail", "Example", "Opinion"], answer_index=0))
    return out


def generate_mindmap(text: str) -> dict:
    center = "Study Notes"
    keys = _top_keywords(text, 6)
    nodes = [{"id": "root", "label": center}]
    edges = []
    for i, k in enumerate(keys):
        nid = f"n{i}"
        nodes.append({"id": nid, "label": k.title()})
        edges.append({"from": "root", "to": nid})
    return {"nodes": nodes, "edges": edges}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest):
    text = (payload.text or "").strip()
    if not text:
        return GenerateResponse(type=payload.type, summary="Please provide lesson text.")

    t = payload.type.lower()
    count = payload.count or 5

    if t == "notes":
        return GenerateResponse(type=t, notes=generate_notes(text, count))
    if t == "summary":
        return GenerateResponse(type=t, summary=generate_summary(text))
    if t == "flashcards":
        return GenerateResponse(type=t, flashcards=generate_flashcards(text, count))
    if t == "mcqs":
        return GenerateResponse(type=t, mcqs=generate_mcqs(text, count))
    if t == "quiz":
        return GenerateResponse(type=t, quiz=generate_mcqs(text, count))
    if t == "mindmap":
        return GenerateResponse(type=t, mindmap=generate_mindmap(text))

    return GenerateResponse(type=t, summary="Unknown generation type.")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
