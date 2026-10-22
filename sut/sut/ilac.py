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
DMAH = "DMAH"  # Düşük molekül ağırlıklı heparin (SUT 4.2.7)

# --- Sınıf kodları: Osteoporoz ---
BISFOSFONAT = "BISFOSFONAT"
DENOSUMAB = "DENOSUMAB"

# --- Sınıf kodları: Prostat (BPH) ---
BPH_ALFA_BLOKER = "BPH_ALFA_BLOKER"
BPH_5ARI = "BPH_5ARI"

SINIF_ADLARI = {
    ACE: "ACE inhibitörü",
    ARB: "Anjiyotensin reseptör blokeri",
    KKB: "Kalsiyum kanal blokeri",
    DIURETIK: "Diüretik",
    BETA: "Beta bloker",
    RENIN: "Direkt renin inhibitörü",
    ARNI: "ARNI (sakubitril içeren)",
    METFORMIN: "Metformin",
    SULFONILURE: "Sülfonilüre",
    GLINID: "Glinid",
    TZD: "Tiazolidindion (pioglitazon)",
    AKARBOZ: "Akarboz",
    DPP4: "DPP-4 inhibitörü",
    SGLT2: "SGLT-2 inhibitörü",
    GLP1: "GLP-1 agonisti",
    INSULIN_KISA: "Kısa/hızlı etkili insülin",
    INSULIN_UZUN: "Uzun etkili insülin",
    ROSUVASTATIN: "Rosuvastatin",
    ATORVASTATIN: "Atorvastatin",
    SIMVASTATIN: "Simvastatin",
    PRAVASTATIN: "Pravastatin",
    FLUVASTATIN: "Fluvastatin",
    PITAVASTATIN: "Pitavastatin",
    KLOPIDOGREL: "Klopidogrel",
    ASA: "Asetilsalisilik Asit (Aspirin)",
    IVABRADIN: "İvabradin",
    NOAK: "Yeni Nesil Oral Antikoagülan",
    DMAH: "Düşük molekül ağırlıklı heparin (DMAH)",
    BISFOSFONAT: "Bisfosfonat (Kemik Erimesi)",
    DENOSUMAB: "Denosumab (Kemik Erimesi)",
    BPH_ALFA_BLOKER: "BPH Alfa Bloker",
    BPH_5ARI: "BPH 5-Alfa Redüktaz İnhibitörü",
}

ETKEN_MADDELER: dict[str, str] = {
    # --- ACE inhibitörleri ---
    "ramipril": ACE, "perindopril": ACE, "enalapril": ACE, "lisinopril": ACE,
    "kaptopril": ACE, "silazapril": ACE, "fosinopril": ACE, "kinapril": ACE,
    "trandolapril": ACE, "zofenopril": ACE, "delapril": ACE, "benazepril": ACE,
    "imidapril": ACE, "moeksipril": ACE, "spirapril": ACE,
    # --- ARB ---
    "valsartan": ARB, "losartan": ARB, "irbesartan": ARB, "kandesartan": ARB,
    "telmisartan": ARB, "olmesartan": ARB, "eprosartan": ARB, "azilsartan": ARB,
    # --- KKB ---
    "amlodipin": KKB, "nifedipin": KKB, "felodipin": KKB, "lerkanidipin": KKB,
    "lasidipin": KKB, "nitrendipin": KKB, "isradipin": KKB, "nikardipin": KKB,
    "barnidipin": KKB, "manidipin": KKB, "verapamil": KKB, "diltiazem": KKB,
    # --- Diüretikler ---
    "hidroklorotiyazid": DIURETIK, "klortalidon": DIURETIK, "indapamid": DIURETIK,
    "spironolakton": DIURETIK, "eplerenon": DIURETIK, "furosemid": DIURETIK,
    "torasemid": DIURETIK, "amilorid": DIURETIK, "triamteren": DIURETIK,
    # --- Beta blokerler ---
    "metoprolol": BETA, "bisoprolol": BETA, "nebivolol": BETA, "karvedilol": BETA,
    "atenolol": BETA, "propranolol": BETA, "betaksolol": BETA,
    # --- Diğer antihipertansif ---
    "aliskiren": RENIN, "sakubitril": ARNI,
    # --- Antidiyabetikler ---
    "metformin": METFORMIN,
    "gliklazid": SULFONILURE, "glimepirid": SULFONILURE,
    "glibenklamid": SULFONILURE, "glipizid": SULFONILURE,
    "repaglinid": GLINID, "nateglinid": GLINID,
    "pioglitazon": TZD, "akarboz": AKARBOZ,
    "sitagliptin": DPP4, "vildagliptin": DPP4, "saksagliptin": DPP4, "linagliptin": DPP4,
    "dapagliflozin": SGLT2, "empagliflozin": SGLT2,
    "eksenatid": GLP1,
    "insulin lispro": INSULIN_KISA, "insulin aspart": INSULIN_KISA, "insulin glulisin": INSULIN_KISA,
    "insulin glargine": INSULIN_UZUN, "insulin detemir": INSULIN_UZUN, "insulin degludec": INSULIN_UZUN,
    # --- Statinler ---
    "rosuvastatin": ROSUVASTATIN, "atorvastatin": ATORVASTATIN, "simvastatin": SIMVASTATIN,
    "pravastatin": PRAVASTATIN, "fluvastatin": FLUVASTATIN, "pitavastatin": PITAVASTATIN,
    # --- Kardiyoloji ve Kan Sulandırıcılar ---
    "klopidogrel": KLOPIDOGREL,
    "asetilsalisilik asit": ASA,
    "ivabradin": IVABRADIN,
    "apiksaban": NOAK,
    "rivaroksaban": NOAK,
    "dabigatran": NOAK,
    "edoksaban": NOAK,
    "tikagrelor": KLOPIDOGREL,
    "prasugrel": KLOPIDOGREL,
    "varfarin": NOAK,
    # --- Düşük molekül ağırlıklı heparinler (DMAH) -- SUT 4.2.7 ---
    "enoksaparin": DMAH,
    "nadroparin": DMAH,
    "dalteparin": DMAH,
    "tinzaparin": DMAH,
    "bemiparin": DMAH,
    # --- Osteoporoz ---
    "alendronat": BISFOSFONAT, "risedronat": BISFOSFONAT,
    "ibandronik asit": BISFOSFONAT, "zoledronik asit": BISFOSFONAT,
    "denosumab": DENOSUMAB,
    # --- Prostat (BPH) ---
    "alfuzosin": BPH_ALFA_BLOKER,
    "tamsulosin": BPH_ALFA_BLOKER,
    "terazosin": BPH_ALFA_BLOKER,
    "doksazosin": BPH_ALFA_BLOKER,
    "silodosin": BPH_ALFA_BLOKER,
    "finasterid": BPH_5ARI,
    "dutasterid": BPH_5ARI,
}

ES_ADLAR: dict[str, str] = {
    "hidroklorotiazid": "hidroklorotiyazid", "hidroklorothiazid": "hidroklorotiyazid", "hctz": "hidroklorotiyazid",
    "captopril": "kaptopril", "cilazapril": "silazapril", "quinapril": "kinapril", "candesartan": "kandesartan",
    "carvedilol": "karvedilol", "sacubitril": "sakubitril", "lercanidipin": "lerkanidipin", "nicardipin": "nikardipin",
    "indapamit": "indapamid", "exenatide": "eksenatid",
    "asetilsalisilik": "asetilsalisilik asit", "aspirin": "asetilsalisilik asit",
    "doksazosio": "doksazosin", "siladosin": "silodosin",
    # --- DMAH alternatif yazımlar ---
    "enoxaparin": "enoksaparin",
    "enoxaparine": "enoksaparin",
    "enoksaparin sodyum": "enoksaparin",
    "nadroparine": "nadroparin",
    "nadroparina": "nadroparin",
    "dalteparine": "dalteparin",
    "tinzaparine": "tinzaparin",
    "bemiparine": "bemiparin",
    "bemiparina": "bemiparin",
}

MARKALAR: dict[str, str] = {
    # --- Antihipertansif ---
    "exforge hct": "valsartan amlodipin hidroklorotiyazid", "exforge": "valsartan amlodipin", "twynsta": "telmisartan amlodipin",
    "sevikar hct": "olmesartan amlodipin hidroklorotiyazid", "sevikar": "olmesartan amlodipin", "triplixam": "perindopril indapamid amlodipin",
    "diovan": "valsartan", "cozaar": "losartan", "atacand": "kandesartan", "micardis": "telmisartan", "aprovel": "irbesartan", "norvasc": "amlodipin",
    # --- Antidiyabetik ---
    "glifor": "metformin", "diaformin": "metformin", "matofin": "metformin", "diamicron": "gliklazid", "amaryl": "glimepirid", "glucobay": "akarboz",
    "glifix plus": "pioglitazon metformin", "glifix": "pioglitazon", "novonorm": "repaglinid", "starlix": "nateglinid",
    "janumet": "sitagliptin metformin", "januvia": "sitagliptin", "galvus met": "vildagliptin metformin", "galvus": "vildagliptin",
    "onglyza": "saksagliptin", "trajenta": "linagliptin", "forziga": "dapagliflozin", "jardiance": "empagliflozin", "byetta": "eksenatid",
    "humalog": "insulin lispro", "novorapid": "insulin aspart", "apidra": "insulin glulisin", "novomix": "insulin aspart",
    "lantus": "insulin glargine", "glarin": "insulin glargine", "basaglar": "insulin glargine", "levemir": "insulin detemir", "tresiba": "insulin degludec", "toujeo": "insulin glargine", "ryzodeg": "insulin degludec insulin aspart",
    # --- Kardiyoloji ve Kan Sulandırıcılar ---
    "klogel-a": "klopidogrel asetilsalisilik asit",
    "klogel a": "klopidogrel asetilsalisilik asit",
    "plavix": "klopidogrel", "karum": "klopidogrel", "pingel": "klopidogrel", "planor": "klopidogrel",
    "klogel": "klopidogrel", "clopra": "klopidogrel", "diloxol": "klopidogrel", "atervix": "klopidogrel", "opgrel": "klopidogrel", "baclan": "klopidogrel",
    "coraspin": "asetilsalisilik asit", "ecopirin": "asetilsalisilik asit", "aspirin": "asetilsalisilik asit", "babyprin": "asetilsalisilik asit",
    "coralan": "ivabradin", "ivabran": "ivabradin",
    "eliquis": "apiksaban", "xarelto": "rivaroksaban", "pradaxa": "dabigatran", "lixiana": "edoksaban",
    # --- Düşük molekül ağırlıklı heparinler (DMAH) ---
    "oksapar": "enoksaparin", "clexane": "enoksaparin", "enoksa": "enoksaparin", "venoksa": "enoksaparin", "parix": "enoksaparin",
    "fraxiparine": "nadroparin", "fraxiparin": "nadroparin",
    "fragmin": "dalteparin",
    "innohep": "tinzaparin",
    "hibor": "bemiparin",
    # --- Statinler ---
    "ator": "atorvastatin", "alvastin": "atorvastatin", "lipitor": "atorvastatin", "atorvio": "atorvastatin", "tarden": "atorvastatin", "divator": "atorvastatin", "cholvast": "atorvastatin", "kolestor": "atorvastatin",
    "crestor": "rosuvastatin", "rovu": "rosuvastatin", "rosucard": "rosuvastatin", "roselip": "rosuvastatin", "rosuvas": "rosuvastatin", "lipovas": "rosuvastatin",
    "zocor": "simvastatin", "lescol": "fluvastatin", "pravachol": "pravastatin", "livalo": "pitavastatin", "alipza": "pitavastatin",
    # --- Osteoporoz ---
    "fosamax": "alendronat", "actonel": "risedronat", "bonviva": "ibandronik asit", "aclasta": "zoledronik asit",
    "prolia": "denosumab",
    # --- Prostat (BPH) ---
    "xatral": "alfuzosin",
    "flomax": "tamsulosin", "tamprost": "tamsulosin", "omniprost": "tamsulosin", "prostamisin": "tamsulosin",
    "hytrin": "terazosin", "teraprost": "terazosin",
    "cardura": "doksazosin", "doxacor": "doksazosin", "kardozin": "doksazosin",
    "urorec": "silodosin", "silodyx": "silodosin",
    "proscar": "finasterid", "prosterid": "finasterid", "dilaprost": "finasterid",
    "avodart": "dutasterid", "dutaprost": "dutasterid",
    "duodart": "dutasterid tamsulosin", "prostacom": "dutasterid tamsulosin",
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
    norm = normalize(metin.replace("-", " "))
    bulunan: dict[str, str] = {}
    if not norm:
        return bulunan

    barkodlar = katalog.barkodlari_bul(metin)
    kamu_kodlari = katalog.kamu_kodlarini_bul(metin)
    katalogla_eslesen_kimlik_var = any(
        (barkod and katalog.bul(barkod) is not None) for barkod in barkodlar
    ) or any(
        (kkod and katalog.kamu_kodu_ile_bul(kkod) is not None) for kkod in kamu_kodlari
    )
    if (barkodlar or kamu_kodlari) and not katalogla_eslesen_kimlik_var:
        return bulunan

    for marka, icerik in MARKALAR.items():
        marka_norm = normalize(marka.replace("-", " "))
        if re.search(rf"\b{re.escape(marka_norm)}\b", norm):
            norm += " " + normalize(icerik)
    for barkod in barkodlar:
        kayit = katalog.bul(barkod)
        if kayit and kayit.get("e"):
            norm += " " + normalize(kayit["e"])
    for kkod in kamu_kodlari:
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