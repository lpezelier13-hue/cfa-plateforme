from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import time
import datetime
from supabase import create_client, Client

# ── CONFIG ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="CFA Compagnons du Devoir — API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── MODÈLES ──────────────────────────────────────────────────────────────
class DemandeCreate(BaseModel):
    metier_id: str
    budget_id: str
    objet: str
    justif: Optional[str] = None
    fournisseur: str
    ref_fourn: Optional[str] = None
    montant: float
    date_demande: str
    fichier_nom: Optional[str] = None
    formateur_nom: str

class DemandeUpdate(BaseModel):
    statut: str
    motif_refus: Optional[str] = None
    budget_id: Optional[str] = None

class MetierCreate(BaseModel):
    id: str
    label: str
    icon: str = "📁"
    color: str = "#6366f1"

class BudgetCreate(BaseModel):
    metier_id: str
    label: str
    montant: float

class BudgetUpdate(BaseModel):
    montant: float

class ApprentiCreate(BaseModel):
    prenom: str
    nom: str
    metier_id: str
    formation: str
    annee: str
    age: Optional[int] = None
    telephone: Optional[str] = None
    entreprise: Optional[str] = None

class LoginData(BaseModel):
    email: str
    password: str

# ── HELPER AUTH ──────────────────────────────────────────────────────────
async def get_user(authorization: str = Header(...)):
    try:
        token = authorization.replace("Bearer ", "")
        user = supabase.auth.get_user(token)
        return user.user
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

async def get_profil(user=Depends(get_user)):
    res = supabase.table("profils").select("*").eq("id", user.id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return res.data[0]

# ── SANTÉ ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "app": "CFA Compagnons du Devoir API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ── AUTH ─────────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(data: LoginData):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
        print(f"Auth response type: {type(res)}")
        print(f"Auth response: {res}")
        # Supabase 1.x retourne directement session et user
        if hasattr(res, 'session') and res.session:
            access_token = res.session.access_token
            user_id = res.user.id
        elif hasattr(res, 'data') and res.data:
            access_token = res.data.session.access_token
            user_id = res.data.user.id
        else:
            raise Exception(f"Structure réponse inattendue: {res}")
        profil = supabase.table("profils").select("*").eq("id", user_id).execute()
        return {
            "access_token": access_token,
            "user": profil.data[0] if profil.data else {}
        }
    except Exception as e:
        print(f"Login error detail: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/auth/me")
def me(profil=Depends(get_profil)):
    return profil

# ── MÉTIERS ──────────────────────────────────────────────────────────────
@app.get("/metiers")
def get_metiers():
    res = supabase.table("metiers").select("*").order("label").execute()
    return res.data

@app.post("/metiers")
def create_metier(data: MetierCreate, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    res = supabase.table("metiers").insert(data.dict()).execute()
    return res.data[0]

@app.delete("/metiers/{metier_id}")
def delete_metier(metier_id: str, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    used = supabase.table("demandes").select("id").eq("metier_id", metier_id).execute()
    if used.data:
        raise HTTPException(status_code=400, detail=f"{len(used.data)} demande(s) utilisent ce métier")
    supabase.table("metiers").delete().eq("id", metier_id).execute()
    return {"ok": True}

# ── BUDGETS ───────────────────────────────────────────────────────────────
@app.get("/budgets")
def get_budgets():
    res = supabase.table("budgets").select("*").order("metier_id").execute()
    return res.data

@app.post("/budgets")
def create_budget(data: BudgetCreate, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    bid = "B" + str(int(time.time()))[-6:]
    res = supabase.table("budgets").insert({"id": bid, **data.dict()}).execute()
    return res.data[0]

@app.put("/budgets/{budget_id}")
def update_budget(budget_id: str, data: BudgetUpdate, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    res = supabase.table("budgets").update({"montant": data.montant}).eq("id", budget_id).execute()
    return res.data[0]

@app.delete("/budgets/{budget_id}")
def delete_budget(budget_id: str, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    used = supabase.table("demandes").select("id").eq("budget_id", budget_id).execute()
    if used.data:
        raise HTTPException(status_code=400, detail=f"{len(used.data)} demande(s) utilisent ce budget")
    supabase.table("budgets").delete().eq("id", budget_id).execute()
    return {"ok": True}

# ── DEMANDES ──────────────────────────────────────────────────────────────
@app.get("/demandes")
def get_demandes(profil=Depends(get_profil)):
    if profil["role"] in ("responsable", "secretariat", "direction"):
        res = supabase.table("demandes").select("*").order("created_at", desc=True).execute()
    else:
        res = supabase.table("demandes").select("*").eq("formateur_id", profil["id"]).order("created_at", desc=True).execute()
    return res.data

@app.post("/demandes")
def create_demande(data: DemandeCreate, profil=Depends(get_profil)):
    if profil["role"] not in ("formateur", "secretariat", "responsable"):
        raise HTTPException(status_code=403, detail="Non autorisé")
    did = "DA-" + str(int(time.time()))[-6:]
    payload = {
        "id": did,
        "formateur_id": profil["id"],
        "formateur_nom": profil["prenom"] + " " + profil["nom"],
        "statut": "attente",
        **data.dict()
    }
    res = supabase.table("demandes").insert(payload).execute()
    return res.data[0]

@app.put("/demandes/{demande_id}")
def update_demande(demande_id: str, data: DemandeUpdate, profil=Depends(get_profil)):
    if profil["role"] != "responsable":
        raise HTTPException(status_code=403, detail="Réservé au responsable")
    if data.statut == "refuse" and not data.motif_refus:
        raise HTTPException(status_code=400, detail="Motif de refus obligatoire")
    payload = {
        "statut": data.statut,
        "motif_refus": data.motif_refus,
        "date_validation": datetime.datetime.now().isoformat(),
        "valideur_id": profil["id"],
    }
    if data.budget_id:
        payload["budget_id"] = data.budget_id
    res = supabase.table("demandes").update(payload).eq("id", demande_id).execute()
    return res.data[0]

# ── APPRENTIS ─────────────────────────────────────────────────────────────
@app.get("/apprentis")
def get_apprentis():
    res = supabase.table("apprentis").select("*").order("nom").execute()
    return res.data

@app.post("/apprentis")
def create_apprenti(data: ApprentiCreate, profil=Depends(get_profil)):
    if profil["role"] not in ("responsable", "secretariat"):
        raise HTTPException(status_code=403, detail="Non autorisé")
    aid = "E" + str(int(time.time()))[-6:]
    res = supabase.table("apprentis").insert({"id": aid, **data.dict()}).execute()
    return res.data[0]

@app.delete("/apprentis/{apprenti_id}")
def delete_apprenti(apprenti_id: str, profil=Depends(get_profil)):
    if profil["role"] not in ("responsable", "secretariat"):
        raise HTTPException(status_code=403, detail="Non autorisé")
    supabase.table("apprentis").delete().eq("id", apprenti_id).execute()
    return {"ok": True}

# ── STATS ─────────────────────────────────────────────────────────────────
@app.get("/stats")
def get_stats(profil=Depends(get_profil)):
    budgets = supabase.table("budgets").select("*").execute().data
    demandes = supabase.table("demandes").select("*").execute().data
    total_budget = sum(b["montant"] for b in budgets)
    total_engage = sum(d["montant"] for d in demandes if d["statut"] == "valide")
    total_attente = sum(d["montant"] for d in demandes if d["statut"] == "attente")
    return {
        "total_budget": total_budget,
        "total_engage": total_engage,
        "total_restant": total_budget - total_engage,
        "total_attente": total_attente,
        "nb_demandes_attente": len([d for d in demandes if d["statut"] == "attente"]),
        "nb_bc_valides": len([d for d in demandes if d["statut"] == "valide"]),
    }
