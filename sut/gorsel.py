"""Fotoğraftan rapor ve reçete verisi çıkarma.

Bu modül SADECE okuma yapar -- hiçbir SUT kuralına göre karar vermez.
Karar verme işini motor.py yapar. Bu ayrım kasıtlı: okuma hatası ile
kural hatası birbirine karışmasın diye.
"""

from __future__ import annotations

import json
import os
import time

from dotenv import load_dotenv
from google import genai
from PIL import Image

load_dotenv()

# Modeller sırayla denenir: ilkinin kotası dolarsa ya da yanıt vermezse sıradakine geçilir.
# Her modelin ücretsiz kotası ayrıdır. Değiştirmek için .env dosyasına şunu yazın:
#   GEMINI_MODELLER=model1,model2,model3
_VARSAYILAN_MODELLER = [
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]
_ortam = os.environ.get("GEMINI_MODELLER", "").strip()
MODELLER = [m.strip() for m in _ortam.split(",") if m.strip()] or _VARSAYILAN_MODELLER
MODEL_ADI = MODELLER[0]

_RAPOR_PROMPT = """Bu bir Türk sağlık kurulu veya uzman hekim raporu fotoğrafı.
Görüntüdeki bilgileri aşağıdaki JSON şemasına göre çıkar.

SADECE net şekilde okuyabildiğin bilgileri yaz. Emin olmadığın veya
görünmeyen her alana null yaz. ASLA TAHMİN ETME, ASLA UYDURMA.

Şema:
{
  "rapor_no": string veya null,
  "duzenleme_tarihi": raporun düzenlenme/başlangıç tarihi, "YYYY-MM-DD" formatında string veya null,
  "bitis_tarihi": raporun bitiş/geçerlilik süresi sonu, "YYYY-MM-DD" formatında string veya null,
  "rapor_tipi": string veya null,
  "tani_kodlari": ["Raporda 'Tanı Bilgileri' veya 'ICD-10' kısmında yazan tüm tanı kodlarını (Örn: E78.0, I10, M81.0, E11.9 gibi harf ve rakamdan oluşan kodları veya 20.00, 04.05 gibi rapor kodlarını) eksiksiz bul ve liste olarak yaz."],
  "hekim_branslari": rapordaki hekim branşlarının listesi, yoksa boş liste [],
  "ilaclar": [{"ad": string, "adet": sayı veya null}, ...], yoksa boş liste [],
  "serbest_metin": raporun tüm serbest metin / açıklama / not alanlarının BİREBİR kopyası,
  "ldl_degeri": raporda yazan ilk/en güncel LDL kolesterol değeri (sayı) veya null,
  "ldl_2_degeri": raporda önceki/ikinci bir LDL değeri varsa (sayı) veya null,
  "tarih": LDL veya tahlil tarihi ("YYYY-MM-DD" formatında) veya null,
  "idame_tedavisi": true veya false (Raporda idame, devam tedavisi veya daha önceden statin kullandığına dair ibare varsa true),
  "alti_ay_ara": true veya false (Raporda 6 ay ara, ara verilmiştir vb. ibare geçiyorsa true),
  "risk_faktorleri": Raporda hastanın tanılarında veya serbest metninde aşağıdaki risk faktörlerinden biri veya birkaçı geçiyorsa, KESİNLİKLE AŞAĞIDAKİ YAZIM ŞEKLİYLE BİREBİR AYNI OLACAK ŞEKİLDE listeye ekle (yoksa boş liste []):
    - "Diyabet (Diabetes Mellitus)"
    - "Hipertansiyon"
    - "Geçirilmiş MI / Akut Koroner Sendrom"
    - "Geçirilmiş İnme"
    - "Koroner Arter Hastalığı (KAH)"
    - "Periferik Arter Hastalığı (PAH)"
    - "Abdominal Aort Anevrizması"
    - "Karotis Arter Hastalığı"
    - "Ailede erken kardiyovasküler hastalık öyküsü"
    - "65 yaş ve üzeri"
}

SADECE bu JSON'u döndür. Başka hiçbir açıklama veya markdown ekleme.
"""

_PROMPT = _RAPOR_PROMPT  # eski isim, geriye dönük uyum

_RECETE_PROMPT = """Bu bir Türk e-reçete ekranı veya fotoğrafı (eczane otomasyonu
ya da MEDULA görünümü olabilir).
Görüntüdeki bilgileri aşağıdaki JSON şemasına göre çıkar.

SADECE net şekilde okuyabildiğin bilgileri yaz. Emin olmadığın veya
görünmeyen her alana null yaz. ASLA TAHMİN ETME, ASLA UYDURMA.
Hasta adı, T.C. kimlik numarası, doktor adı gibi kişisel bilgileri ÇIKARMA.

Reçete ekranının düzeni: Üst kısımda bir başlık bölümü vardır; burada
"Reçete Tarihi" (gg/aa/yyyy biçiminde), "Doktor Brans", ve "E-Reçete No"
veya "Seri No" gibi alanlar bulunur. Altında "İlaç Bilgileri" bölümünde her
ilaç için bir blok vardır: "Adı : ..." satırı (ilaç adı ve parantez içinde
barkod), aynı satırda "Adet : N" (yazılan KUTU sayısı), "Kullanım : Günde
1 x 1.0" (günlük doz) ve "Kullanım Şekli" bulunur. Altında "Teşhis/Tanı - ..."
satırı ve yeşil kutuda "Ambalaj Adet : 28,00 Adet" (kutunun içindeki tablet
sayısı) yer alır. Sayfanın altında "Açıklama Listesi" ve "Tanı Listesi"
bölümleri vardır.

ÇOK ÖNEMLİ UYARI: "Protokol No" alanı (örnek: "A-461145-2-001-A-280926-00000659"
biçiminde, harf-sayı karışık uzun bir kod) RAPOR BİLGİSİ DEĞİLDİR. Bu sadece
reçetenin gönderim protokol numarasıdır, genelde başlıkta ve her ilacın
"Teşhis/Tanı" satırında tekrar eder. Bunu rapor_bilgisi alanına YAZMA, tamamen
görmezden gel. rapor_bilgisi alanı SADECE ekranda açıkça "Rapor No",
"Rapor Tarihi" veya benzer bir rapor ifadesi varsa doldurulur.

Şema:
{
  "recete_no": "E-Reçete No" varsa onun değeri, yoksa "Seri No" değeri,
    ikisi de yoksa null,
  "tarih": "Reçete Tarihi" alanındaki tarih, "YYYY-MM-DD" formatında, yoksa null,
  "hekim_bransi": "Doktor Brans" alanındaki değer (string) veya null,
  "ilaclar": [{"ad": "Adı :" satırındaki ilaç adı (barkod dahil, olduğu gibi),
    "adet": "Adet : N" alanındaki N sayısı (tam sayı) veya null}, ...],
    yoksa boş liste [],
  "aciklama": şu iki yerdeki metinlerin BİREBİR kopyası, her biri ayrı satırda:
    (1) "Açıklama Listesi" bölümündeki "Reçete Açıklama" sütunu (Protokol No
    tekrarından farklı, GERÇEK bir açıklama cümlesi varsa onu da ekle),
    (2) her ilacın altındaki "Teşhis/Tanı - ..." satırının "-" işaretinden
    sonraki metni, EĞER bu metin Protokol No tekrarı DEĞİLSE (ör. "tok",
    "HT" gibi kısa tanı kodları ya da gerçek bir cümle). Protokol No
    tekrarıysa o satırı atla. Hiçbiri yoksa "",
  "rapor_bilgisi": yukarıdaki uyarıyı dikkate alarak, ekranda GERÇEKTEN bir
    rapor numarası/tarihi/ifadesi varsa aynen kopyası, yoksa null
}

ÖNEMLİ: "adet" alanına "Adet :" değerini yaz. "Ambalaj Adet" (kutunun içindeki
tablet sayısı) ya da günlük doz (1 x 1.0) ASLA kutu sayısı değildir.

SADECE bu JSON'u döndür. Başka hiçbir açıklama, markdown işareti
veya yorum ekleme.
"""


def _json_ayikla(metin: str) -> str:
    """Modelin bazen JSON'u kod bloğu işaretleri içine sarmasına karşı savunma."""
    cit = "`" * 3
    metin = metin.strip()
    if metin.startswith(cit):
        parcalar = metin.split(cit)
        metin = parcalar[1] if len(parcalar) > 1 else metin
        if metin.startswith("json"):
            metin = metin[4:]
    return metin.strip()


def _openai_oku(prompt: str, resim) -> dict:
    """Yedek okuyucu (isteğe bağlı): .env içinde OPENAI_API_KEY varsa kullanılır.

    Model adı için .env'ye OPENAI_MODEL=... yazabilirsiniz.
    """
    import base64
    import io

    from openai import OpenAI  # yalnızca kullanılırsa gerekir

    model = os.environ.get("OPENAI_MODEL", "gpt-5.4")
    tampon = io.BytesIO()
    resim.convert("RGB").save(tampon, format="PNG")
    veri = base64.b64encode(tampon.getvalue()).decode()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    yanit = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + veri}},
            ],
        }],
    )
    sonuc = json.loads(_json_ayikla(yanit.choices[0].message.content))
    if isinstance(sonuc, dict):
        sonuc["_model"] = "openai:" + model
    return sonuc


def _resmi_kucult_ve_gonder(resim_yolu) -> Image.Image:
    """Görüntüyü hızlı yükleme için sıkıştırır ve küçültür."""
    img = Image.open(resim_yolu)
    
    # Görüntü çok büyükse küçült (max 1600 piksel)
    max_boyut = 1600
    if max(img.size) > max_boyut:
        oran = max_boyut / float(max(img.size))
        yeni_boyut = (int(img.size[0] * oran), int(img.size[1] * oran))
        img = img.resize(yeni_boyut, Image.Resampling.LANCZOS)
        
    # Siyah arka plan hatalarını önlemek ve boyutu küçültmek için RGB'ye çevir
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    return img

def _gonder(prompt: str, resim_yolu) -> dict:
    """Görüntüyü Gemini'ye gönderir, JSON (dict) döndürür."""
    anahtar = os.environ.get("GEMINI_API_KEY")
    if not anahtar:
        raise RuntimeError(".env dosyasında GEMINI_API_KEY bulunamadı.")

    # FOTOĞRAFI GÖNDERMEDEN ÖNCE HIZLICA KÜÇÜLTÜYORUZ
    resim = _resmi_kucult_ve_gonder(resim_yolu)
    
    client = genai.Client(api_key=anahtar)

    hatalar: list[str] = []
    kota_hatasi = False
    for model in MODELLER:
        for deneme in range(3):  # Deneme sayısını 5'ten 3'e düşürdük (hızlı pes etsin, yedeğe geçsin)
            try:
                yanit = client.models.generate_content(
                    model=model,
                    contents=[prompt, resim],
                )
                sonuc = json.loads(_json_ayikla(yanit.text))
                if isinstance(sonuc, dict):
                    sonuc["_model"] = model
                return sonuc
            except json.JSONDecodeError as e:
                hatalar.append(f"{model}: yanıt geçerli JSON değildi ({e})")
                break
            except Exception as e:
                mesaj = str(e)
                hatalar.append(f"{model}: {mesaj[:120]}")

                if "429" in mesaj or "RESOURCE_EXHAUSTED" in mesaj:
                    kota_hatasi = True
                    break

                if ("503" in mesaj or "UNAVAILABLE" in mesaj) and deneme < 2:
                    bekle = 2 * (deneme + 1)  # Bekleme süresini de 4 saniyeden 2 saniyeye düşürdük
                    time.sleep(bekle)
                    continue
                break

    if os.environ.get("OPENAI_API_KEY"):
        try:
            return _openai_oku(prompt, resim)
        except Exception as e:
            hatalar.append(f"openai: {str(e)[:150]}")

    if kota_hatasi and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "API kotası doldu. Dakikalık limitse 1-2 dakika bekleyin."
        )
    raise RuntimeError("Tüm modeller başarısız oldu: " + " | ".join(hatalar[-3:]))


def rapor_oku(resim_yolu) -> dict:
    """Rapor fotoğrafını okuyup ham dict döndürür."""
    return _gonder(_RAPOR_PROMPT, resim_yolu)


def recete_oku(resim_yolu) -> dict:
    """Reçete fotoğrafını okuyup ham dict döndürür."""
    return _gonder(_RECETE_PROMPT, resim_yolu)