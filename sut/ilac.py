"""Etken madde -> ilaç sınıfı eşleştirmesi."""

from __future__ import annotations
import re
from . import katalog
from .metin import normalize

# --- Sınıf kodları: antihipertansif ---
ACE = "ACE"
ARB = "ARB"
KKB = "KKB"
DIURETIK = "DIURETIK"
BETA = "BETA"
RENIN = "RENIN"
ARNI = "ARNI"

# --- Sınıf kodları: antidiyabetik ---
METFORMIN = "METFORMIN"
SULFONILURE = "SULFONILURE"
GLINID = "GLINID"
TZD = "TZD"
AKARBOZ = "AKARBOZ"
DPP4 = "DPP4"
SGLT2 = "SGLT2"
GLP1 = "GLP1"
INSULIN_KISA = "INSULIN_KISA"
INSULIN_UZUN = "INSULIN_UZUN"

# --- Sınıf kodları: statinler ---
ROSUVASTATIN = "ROSUVASTATIN"
ATORVASTATIN = "ATORVASTATIN"
SIMVASTATIN = "SIMVASTATIN"
PRAVASTATIN = "PRAVASTATIN"
FLUVASTATIN = "FLUVASTATIN"
PITAVASTATIN = "PITAVASTATIN"

# --- Sınıf kodları: KARDİYOLOJİ VE KAN SULANDIRICILAR ---
KLOPIDOGREL = "KLOPIDOGREL"
ASA = "ASA"
IVABRADIN = "IVABRADIN"
NOAK = "NOAK"

# --- Sınıf kodları: Osteoporoz ---
BISFOSFONAT = "BISFOSFONAT"
DENOSUMAB = "DENOSUMAB"

SINIF_ADLARI = {
    ACE: "ACE inhibitörü", ARB: "Anjiyotensin reseptör blokeri", KKB: "Kalsiyum kanal blokeri",
    DIURETIK: "Diüretik", BETA: "Beta bloker", RENIN: "Direkt renin inhibitörü", ARNI: "ARNI",
    METFORMIN: "Metformin", SULFONILURE: "Sülfonilüre", GLINID: "Glinid", TZD: "Pioglitazon",
    AKARBOZ: "Akarboz", DPP4: "DPP-4 inhibitörü", SGLT2: "SGLT-2 inhibitörü", GLP1: "GLP-1 agonisti",
    INSULIN_KISA: "Kısa etkili insülin", INSULIN_UZUN: "Uzun etkili insülin",
    ROSUVASTATIN: "Rosuvastatin", ATORVASTATIN: "Atorvastatin", SIMVASTATIN: "Simvastatin",
    PRAVASTATIN: "Pravastatin", FLUVASTATIN: "Fluvastatin", PITAVASTATIN: "Pitavastatin",
    KLOPIDOGREL: "Klopidogrel", ASA: "Asetilsalisilik Asit (Aspirin)", IVABRADIN: "İvabradin",
    NOAK: "Yeni Nesil Oral Antikoagülan", BISFOSFONAT: "Bisfosfonat (Kemik Erimesi)",
    DENOSUMAB: "Denosumab (Kemik Erimesi)",
}

ETKEN_MADDELER: dict[str, str] = {
    "ramipril": ACE, "perindopril": ACE, "enalapril": ACE, "lisinopril": ACE, "kaptopril": ACE, "silazapril": ACE, "fosinopril": ACE, "kinapril": ACE,
    "valsartan": ARB, "losartan": ARB, "irbesartan": ARB, "kandesartan": ARB, "telmisartan": ARB, "olmesartan": ARB, "eprosartan": ARB, "azilsartan": ARB,
    "amlodipin": KKB, "nifedipin": KKB, "felodipin": KKB, "lerkanidipin": KKB, "lasidipin": KKB, "nitrendipin": KKB, "isradipin": KKB, "nikardipin": KKB, "barnidipin": KKB, "manidipin": KKB,
    "verapamil": KKB, "diltiazem": KKB,
    "hidroklorotiyazid": DIURETIK, "klortalidon": DIURETIK, "indapamid": DIURETIK, "spironolakton": DIURETIK, "eplerenon": DIURETIK, "furosemid": DIURETIK, "torasemid": DIURETIK,
    "metoprolol": BETA, "bisoprolol": BETA, "nebivolol": BETA, "karvedilol": BETA, "atenolol": BETA, "propranolol": BETA, "betaksolol": BETA,
    "aliskiren": RENIN, "sakubitril": ARNI,
    "metformin": METFORMIN, "gliklazid": SULFONILURE, "glimepirid": SULFONILURE, "glibenklamid": SULFONILURE, "glipizid": SULFONILURE,
    "repaglinid": GLINID, "nateglinid": GLINID, "pioglitazon": TZD, "akarboz": AKARBOZ,
    "sitagliptin": DPP4, "vildagliptin": DPP4, "saksagliptin": DPP4, "linagliptin": DPP4,
    "dapagliflozin": SGLT2, "empagliflozin": SGLT2, "eksenatid": GLP1,
    "insulin lispro": INSULIN_KISA, "insulin aspart": INSULIN_KISA, "insulin glulisin": INSULIN_KISA,
    "insulin glargine": INSULIN_UZUN, "insulin detemir": INSULIN_UZUN, "insulin degludec": INSULIN_UZUN,
    "rosuvastatin": ROSUVASTATIN, "atorvastatin": ATORVASTATIN, "simvastatin": SIMVASTATIN, "pravastatin": PRAVASTATIN, "fluvastatin": FLUVASTATIN, "pitavastatin": PITAVASTATIN,
    # --- Kardiyoloji ve Kan Sulandırıcılar ---
    "klopidogrel": KLOPIDOGREL,
    "asetilsalisilik asit": ASA,
    "ivabradin": IVABRADIN,
    "apiksaban": NOAK,
    "rivaroksaban": NOAK,
    "dabigatran": NOAK,
    "edoksaban": NOAK,
    # --- Osteoporoz ---
    "alendronat": BISFOSFONAT, "risedronat": BISFOSFONAT, "ibandronik asit": BISFOSFONAT, "zoledronik asit": BISFOSFONAT,
    "denosumab": DENOSUMAB,
}

ES_ADLAR: dict[str, str] = {
    "hidroklorotiazid": "hidroklorotiyazid", "hidroklorothiazid": "hidroklorotiyazid", "hctz": "hidroklorotiyazid",
    "captopril": "kaptopril", "cilazapril": "silazapril", "quinapril": "kinapril", "candesartan": "kandesartan",
    "carvedilol": "karvedilol", "sacubitril": "sakubitril", "lercanidipin": "lerkanidipin", "nicardipin": "nikardipin",
    "indapamit": "indapamid", "exenatide": "eksenatid",
}

MARKALAR: dict[str, str] = {
    "exforge hct": "valsartan amlodipin hidroklorotiyazid", "exforge": "valsartan amlodipin", "twynsta": "telmisartan amlodipin",
    "sevikar hct": "olmesartan amlodipin hidroklorotiyazid", "sevikar": "olmesartan amlodipin", "triplixam": "perindopril indapamid amlodipin",
    "diovan": "valsartan", "cozaar": "losartan", "atacand": "kandesartan", "micardis": "telmisartan", "aprovel": "irbesartan", "norvasc": "amlodipin",
    "glifor": "metformin", "diaformin": "metformin", "matofin": "metformin", "diamicron": "gliklazid", "amaryl": "glimepirid", "glucobay": "akarboz",
    "glifix plus": "pioglitazon metformin", "glifix": "pioglitazon", "novonorm": "repaglinid", "starlix": "nateglinid",
    "janumet": "sitagliptin metformin", "januvia": "sitagliptin", "galvus met": "vildagliptin metformin", "galvus": "vildagliptin",
    "onglyza": "saksagliptin", "trajenta": "linagliptin", "forziga": "dapagliflozin", "jardiance": "empagliflozin", "byetta": "eksenatid",
    "humalog": "insulin lispro", "novorapid": "insulin aspart", "apidra": "insulin glulisin", "novomix": "insulin aspart",
    "lantus": "insulin glargine", "glarin": "insulin glargine", "basaglar": "insulin glargine", "levemir": "insulin detemir", "tresiba": "insulin degludec", "toujeo": "insulin glargine", "ryzodeg": "insulin degludec insulin aspart",
    # --- Kardiyoloji ve Kan Sulandırıcılar ---
    "plavix": "klopidogrel", "karum": "klopidogrel", "pingel": "klopidogrel", "planor": "klopidogrel",
    "coraspin": "asetilsalisilik asit", "ecopirin": "asetilsalisilik asit", "aspirin": "asetilsalisilik asit",
    "coralan": "ivabradin",
    "eliquis": "apiksaban", "xarelto": "rivaroksaban", "pradaxa": "dabigatran", "lixiana": "edoksaban",
    # --- Osteoporoz ---
    "fosamax": "alendronat", "actonel": "risedronat", "bonviva": "ibandronik asit", "aclasta": "zoledronik asit",
    "prolia": "denosumab",
}

try:
    from .markalar_uretilen import URETILEN
    MARKALAR = {**URETILEN, **MARKALAR}
except ImportError:
    pass

def _desen_derle(ad: str) -> re.Pattern:
    kacisli = re.escape(normalize(ad))
    return re.compile(rf"\b{kacisli}\b" if len(ad) <= 5 else rf"\b{kacisli}")

_DERLENMIS: list[tuple[str, str, re.Pattern]] = []
for _ad, _sinif in ETKEN_MADDELER.items():
    _DERLENMIS.append((_ad, _sinif, _desen_derle(_ad)))
for _es, _asil in ES_ADLAR.items():
    _DERLENMIS.append((_asil, ETKEN_MADDELER[_asil], _desen_derle(_es)))

def maddeleri_bul(metin: str) -> dict[str, str]:
    norm = normalize(metin)
    bulunan: dict[str, str] = {}
    if not norm:
        return bulunan
    for marka, icerik in MARKALAR.items():
        if re.search(rf"\b{re.escape(normalize(marka))}\b", norm):
            norm += " " + normalize(icerik)
    for barkod in katalog.barkodlari_bul(metin):
        kayit = katalog.bul(barkod)
        if kayit and kayit.get("e"):
            norm += " " + normalize(kayit["e"])
    for kkod in katalog.kamu_kodlarini_bul(metin):
        kayit = katalog.kamu_kodu_ile_bul(kkod)
        if kayit and kayit.get("e"):
            norm += " " + normalize(kayit["e"])
    for ad, sinif, desen in _DERLENMIS:
        if desen.search(norm):
            bulunan[ad] = sinif
    return bulunan

def siniflari_bul(metin: str) -> set[str]:
    return set(maddeleri_bul(metin).values())

def sinif_adi(kod: str) -> str:
    return SINIF_ADLARI.get(kod, kod)