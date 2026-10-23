"""SGK EK-4/A Excel dosyasından tüm hedef branş ilaçlarını (Barkod, Kamu No,
Ticari İsim ve Etken Madde) çıkarıp veri/katalog.json ve sut/markalar_uretilen.py
dosyalarına otomatik entegre eder."""

from __future__ import annotations

import json
import re
from pathlib import Path
import pandas as pd

# Excel dosyasının adı (proje klasöründeki adını buraya yazabilirsin)
# Excel dosyasını hem ana klasörde hem de sut klasöründe otomatik arar
EXCEL_YOLU = Path("ek4a.xlsx.xlsx")
KATALOG_YOLU = Path("veri/katalog.json")
MARKALAR_YOLU = Path("sut/markalar_uretilen.py")

# 1. EK-4/A EŞDEĞER İLAÇ GRUBU -> ETKEN MADDE TABLOSU
# Aynı eşdeğer gruptaki tüm jenerik markalar aynı etken maddeye sahiptir!
ESDEGER_GRUP_HARITASI: dict[str, str] = {
    # --- ACE İnhibitörleri ve Kombinasyonları ---
    "E017": "enalapril",
    "E029": "kaptopril",
    "E036": "lisinopril",
    "E365A": "ramipril", "E365B": "ramipril", "E365C": "ramipril",
    "E365D": "ramipril hidroklorotiyazid", "E365E": "ramipril hidroklorotiyazid",
    "E365F": "ramipril hidroklorotiyazid", "E365G": "ramipril hidroklorotiyazid",
    "E442A": "zofenopril", "E442B": "zofenopril hidroklorotiyazid",
    "E471A": "benazepril hidroklorotiyazid", "E471B": "benazepril", "E471C": "benazepril hidroklorotiyazid",
    "E472A": "fosinopril", "E472B": "fosinopril", "E472C": "fosinopril hidroklorotiyazid",
    "E473A": "silazapril", "E473B": "silazapril", "E473C": "silazapril", "E473D": "silazapril hidroklorotiyazid",
    "E475A": "perindopril", "E475B": "perindopril", "E475C": "perindopril", "E475D": "perindopril",
    "E475E": "perindopril indapamid", "E475F": "perindopril indapamid",
    "E658": "perindopril amlodipin",  # Triplixam / Normotri aşağıda ayrıca indapamid alır
    "E753": "enalapril lerkanidipin",
    "E779": "trandolapril verapamil",

    # --- ARB ve Kombinasyonları ---
    "E239A": "kandesartan", "E239B": "kandesartan", "E239C": "kandesartan", "E239D": "kandesartan",
    "E239E": "kandesartan hidroklorotiyazid", "E239F": "kandesartan hidroklorotiyazid", "E239G": "kandesartan hidroklorotiyazid",
    "E244A": "telmisartan", "E244B": "telmisartan",
    "E244C": "telmisartan hidroklorotiyazid", "E244D": "telmisartan hidroklorotiyazid",
    "E272A": "losartan", "E272C": "losartan",
    "E272B": "losartan hidroklorotiyazid", "E272D": "losartan hidroklorotiyazid",
    "E335A": "olmesartan", "E335B": "olmesartan", "E335C": "olmesartan",
    "E335D": "olmesartan hidroklorotiyazid", "E335E": "olmesartan hidroklorotiyazid",
    "E335F": "olmesartan hidroklorotiyazid", "E335G": "olmesartan hidroklorotiyazid",
    "E335H": "olmesartan amlodipin", "E335I": "olmesartan amlodipin", "E335J": "olmesartan amlodipin",
    "E374A": "irbesartan", "E374B": "irbesartan", "E374C": "irbesartan",
    "E374D": "irbesartan hidroklorotiyazid", "E374E": "irbesartan hidroklorotiyazid", "E374F": "irbesartan hidroklorotiyazid",
    "E433A": "valsartan", "E433B": "valsartan", "E433C": "valsartan", "E433D": "valsartan",
    "E433E": "valsartan hidroklorotiyazid", "E433F": "valsartan hidroklorotiyazid",
    "E433G": "valsartan hidroklorotiyazid", "E433H": "valsartan hidroklorotiyazid",
    "E551A": "eprosartan", "E551B": "eprosartan hidroklorotiyazid",
    "E635": "valsartan amlodipin",
    "E851": "kandesartan amlodipin",

    # --- Kalsiyum Kanal Blokerleri (KKB) ---
    "E002": "amlodipin",
    "E015": "diltiazem",
    "E074": "verapamil",
    "E174": "nifedipin",
    "E639": "benidipin",
    "E661": "amlodipin atorvastatin",
    "E877": "lerkanidipin",

    # --- Beta Blokörler ---
    "E086A": "atenolol", "E086B": "atenolol", "E086C": "atenolol klortalidon", "E086D": "atenolol klortalidon",
    "E172": "metoprolol",
    "E249": "sotalol",
    "E340": "karvedilol",
    "E405": "bisoprolol",
    "E450": "nebivolol",
    "E721": "esmolol",

    # --- Diüretikler ---
    "E027": "indapamid",
    "E126": "furosemid",
    "E668": "eplerenon",
    "E776": "spironolakton",
    "E805": "spironolakton hidroklorotiyazid",

    # --- Antidiyabetikler ve İnsülinler ---
    "E025": "gliklazid",
    "E040": "metformin",
    "E120": "akarboz",
    "E186": "glibenklamid",
    "E264": "glimepirid",
    "E353": "pioglitazon",
    "E562": "pioglitazon metformin",
    "E638": "sitagliptin metformin",
    "E682": "sitagliptin",
    "E728": "insulin glargine",
    "E845A": "vildagliptin",
    "E845B": "vildagliptin metformin", "E845C": "vildagliptin metformin",
    "E919": "linagliptin",
    "E923": "dapagliflozin",
    "E929": "insulin degludec insulin aspart",
    "E944": "linagliptin metformin",
    "E954": "empagliflozin",
    "E978": "empagliflozin metformin",
    "E985": "dapagliflozin metformin",

    # --- Statinler / Kolesterol ---
    "E008": "atorvastatin",
    "E407": "pravastatin",
    "E434": "rosuvastatin",
    "E807": "pitavastatin",

    # --- Kan Sulandırıcılar / Kardiyoloji / NOAK / DMAH ---
    "E084": "asetilsalisilik asit",
    "E274": "klopidogrel",
    "E427": "enoksaparin",
    "E826": "apiksaban",
    "E866": "rivaroksaban",
    "E874": "tikagrelor",
    "E938": "prasugrel",
    "E966": "edoksaban",

    # --- Osteoporoz ---
    "E242": "alendronat",
    "E375": "zoledronik asit",
    "E573": "ibandronik asit",
    "E583": "zoledronik asit",
    "E599": "ibandronik asit",

    # --- Prostat (BPH) ---
    "E021": "finasterid",
    "E254": "doksazosin",
    "E403": "terazosin",
    "E409": "tamsulosin",
    "E561": "alfuzosin",
    "E613": "dutasterid",
}

# 2. EŞDEĞER KODU OLMAYAN VEYA ÖZEL KOMBİNASYON OLAN İLAÇLAR İÇİN İSİM KALIPLARI
OZEL_ISIM_HARITASI: list[tuple[str, str]] = [
    ("TRIPLIXAM", "perindopril indapamid amlodipin"),
    ("NORMOTRI", "perindopril indapamid amlodipin"),
    ("PERILOPIN PLUS", "perindopril indapamid amlodipin"),
    ("EXFORGE HCT", "valsartan amlodipin hidroklorotiyazid"),
    ("CARDOFIX PLUS", "valsartan amlodipin hidroklorotiyazid"),
    ("EXCALIBA PLUS", "olmesartan amlodipin hidroklorotiyazid"),
    ("OLMECOMB PLUS", "olmesartan amlodipin hidroklorotiyazid"),
    ("SEVIKAR HCT", "olmesartan amlodipin hidroklorotiyazid"),
    ("CANLOX PLUS", "kandesartan amlodipin hidroklorotiyazid"),
    ("TANSIFA PLUS", "kandesartan amlodipin hidroklorotiyazid"),
    ("IRDAPIN PLUS", "irbesartan amlodipin hidroklorotiyazid"),
    ("IRDAPIN", "irbesartan amlodipin"),
    ("KARVEA DUO", "irbesartan amlodipin"),
    ("TELMODIP PLUS", "telmisartan amlodipin hidroklorotiyazid"),
    ("TELMODIP", "telmisartan amlodipin"),
    ("TWYNSTA", "telmisartan amlodipin"),
    ("NEVIMOL PLUS", "nebivolol hidroklorotiyazid"),
    ("VASOXEN PLUS", "nebivolol hidroklorotiyazid"),
    ("NEXIVOL PLUS", "nebivolol hidroklorotiyazid"),
    ("KARDORITM PLUS", "bisoprolol hidroklorotiyazid"),
    ("CONCOR PLUS", "bisoprolol hidroklorotiyazid"),
    ("ENTRESTO", "sakubitril valsartan"),
    ("ONEPTUS", "sakubitril valsartan"),
    ("NEPRILEX", "sakubitril valsartan"),
    ("OVEFRAN", "sakubitril valsartan"),
    ("AZEDOK", "azilsartan"),
    ("EDARBI", "azilsartan"),
    ("GOPTEN", "trandolapril"),
    ("PLENDIL", "felodipin"),
    ("ADALAT", "nifedipin"),
    ("LACIPIL", "lasidipin"),
    ("SUTRIL", "torasemid"),
    ("TOREM", "torasemid"),
    ("DIDERALL", "propranolol"),
    ("LOKREN", "betaksolol"),
    ("ONGLYZA", "saksagliptin"),
    ("KOMBIGLYZE", "saksagliptin metformin"),
    ("JENTADUETO", "linagliptin metformin"),
    ("XIGDUO", "dapagliflozin metformin"),
    ("BYETTA", "eksenatid"),
    ("HUMALOG", "insulin lispro"),
    ("NOVORAPID", "insulin aspart"),
    ("FIASP", "insulin aspart"),
    ("NOVOMIX", "insulin aspart"),
    ("APIDRA", "insulin glulisin"),
    ("TOUJEO", "insulin glargine"),
    ("ABASAGLAR", "insulin glargine"),
    ("LEVEMIR", "insulin detemir"),
    ("TRESIBA", "insulin degludec"),
    ("SOLIQUA", "insulin glargine"),
    ("SIMVAKOL", "simvastatin"),
    ("ZOCOR", "simvastatin"),
    ("LESCOL", "fluvastatin"),
    ("LIVALO", "pitavastatin"),
    ("ALIPZA", "pitavastatin"),
    ("KLOGEL-A", "klopidogrel asetilsalisilik asit"),
    ("KLOGEL A", "klopidogrel asetilsalisilik asit"),
    ("CORALAN", "ivabradin"),
    ("IVABRAN", "ivabradin"),
    ("PRADAXA", "dabigatran"),
    ("DABIGAT", "dabigatran"),
    ("HIBOR", "bemiparin"),
    ("FRAXIPARIN", "nadroparin"),
    ("FRAGMIN", "dalteparin"),
    ("INNOHEP", "tinzaparin"),
    ("COUMADIN", "varfarin"),
    ("ORFARIN", "varfarin"),
    ("PROLIA", "denosumab"),
    ("ACTONEL", "risedronat"),
    ("RISENDROS", "risedronat"),
    ("OSTEOACT", "risedronat"),
    ("UROREC", "silodosin"),
    ("SILODYX", "silodosin"),
    ("DUODART", "dutasterid tamsulosin"),
    ("PROSTACOM", "dutasterid tamsulosin"),
    ("COMBIPROST", "dutasterid tamsulosin"),
]


def ticari_kok_ayikla(ilac_adi: str) -> str:
    """'EXFORGE 10 MG/160 MG 28 FTB' -> 'exforge',
       'CARDOFIX PLUS 10/160/12,5 MG' -> 'cardofix plus'"""
    temiz = re.sub(r"\(.*?\)", "", ilac_adi).strip()
    kelimeler = temiz.split()
    secilen = []
    for k in kelimeler:
        if any(ch.isdigit() for ch in k) or k.upper() in {
            "MG", "ML", "MCG", "IU", "U", "GR", "G", "FTB", "TB", "TAB", "TABLET",
            "KAP", "KAPSUL", "AMP", "FLK", "FLAKON", "FILM", "KAPLI", "SR", "MR",
            "XR", "XL", "CR", "ZOK", "ZOC", "SDK", "PENFILL", "FLEXPEN", "SOLOSTAR",
            "KWIKPEN", "FLEXTOUCH", "ANTI", "ANTI-XA", "IV", "IM", "SC",
        }:
            break
        secilen.append(k.lower())
    return " ".join(secilen).strip(" -*.,")


def calistir():
    df = pd.read_excel(EXCEL_YOLU, sheet_name="EK-4A", skiprows=2)

    katalog_sozluk: dict[str, dict] = {}
    if KATALOG_YOLU.exists():
        try:
            katalog_sozluk = json.loads(KATALOG_YOLU.read_text(encoding="utf-8"))
        except Exception:
            katalog_sozluk = {}

    markalar_sozluk: dict[str, str] = {}
    eklenen_barkod = 0

    for _, satir in df.iterrows():
        ad = str(satir.get("İlaç Adı") or "").strip()
        if not ad or ad == "nan":
            continue
        ad_upper = ad.upper()
        kamu_no = str(satir.get("Kamu No") or "").strip()
        esdeger = str(satir.get("Eşdeğer İlaç Grubu") or "").strip().upper()

        etken = None
        # 1) Önce özel isim/kombinasyon eşleşmesine bak
        for kalip, madde in OZEL_ISIM_HARITASI:
            if kalip in ad_upper:
                etken = madde
                break

        # 2) Eşdeğer İlaç Grubu tam veya 4 karakterli önek eşleşmesine bak
        if not etken and esdeger and esdeger != "NAN":
            for parca in esdeger.split("/"):
                parca = parca.strip()
                if parca in ESDEGER_GRUP_HARITASI:
                    etken = ESDEGER_GRUP_HARITASI[parca]
                    break
                if parca[:4] in ESDEGER_GRUP_HARITASI:
                    etken = ESDEGER_GRUP_HARITASI[parca[:4]]
                    break

        # PLUS içeren 2'li kombinasyonlarda HCTZ ekle (henüz eklenmemişse)
        if etken and " PLUS" in ad_upper and "hidroklorotiyazid" not in etken and "indapamid" not in etken and "metformin" not in etken:
            if any(x in etken for x in ("valsartan", "losartan", "irbesartan", "kandesartan", "telmisartan", "olmesartan", "ramipril", "enalapril", "lisinopril", "fosinopril", "benazepril", "zofenopril")):
                etken += " hidroklorotiyazid"
            elif "vildagliptin" in etken or "linagliptin" in etken or "sitagliptin" in etken:
                etken += " metformin"

        # Barkodları çıkar (Güncel Barkod + Eski Barkodlar)
        barkodlar = []
        g_barkod = satir.get("Güncel Barkod")
        if pd.notna(g_barkod):
            try:
                b_str = str(int(float(g_barkod)))
                if len(b_str) == 13:
                    barkodlar.append(b_str)
            except Exception:
                pass
        eski_b = str(satir.get("Eski Barkodlar") or "")
        barkodlar.extend(re.findall(r"(?<!\d)\d{13}(?!\d)", eski_b))

        for b in set(barkodlar):
            kayit = {"k": kamu_no, "a": ad}
            if etken:
                kayit["e"] = etken
            katalog_sozluk[b] = kayit
            eklenen_barkod += 1

        if etken:
            kok = ticari_kok_ayikla(ad)
            if len(kok) >= 3:
                markalar_sozluk[kok] = etken

    # 1. veri/katalog.json dosyasını kaydet
    KATALOG_YOLU.parent.mkdir(parents=True, exist_ok=True)
    KATALOG_YOLU.write_text(
        json.dumps(katalog_sozluk, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2. sut/markalar_uretilen.py dosyasını kaydet
    satirlar = ['"""EK-4/A Excel dosyasından otomatik üretildi."""\n\nURETILEN: dict[str, str] = {\n']
    for k, v in sorted(markalar_sozluk.items()):
        satirlar.append(f"    {k!r}: {v!r},\n")
    satirlar.append("}\n")
    MARKALAR_YOLU.write_text("".join(satirlar), encoding="utf-8")

    print(f"Tamamlandı! {eklenen_barkod} barkod 'veri/katalog.json' içine, "
          f"{len(markalar_sozluk)} ticari marka 'sut/markalar_uretilen.py' içine yazıldı.")


if __name__ == "__main__":
    calistir()