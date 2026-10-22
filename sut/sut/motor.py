"""Kural motoru."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from . import ilac
from .metin import ibare_ara, normalize
from .semalar import Bulgu, Ilac, Rapor, Recete, Sonuc


@dataclass
class KuralSeti:
    surum: str
    kaynak: str
    ayarlar: dict
    ibareler: dict
    kurallar: list[dict]


def yukle(yol: str | Path) -> KuralSeti:
    veri = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    return KuralSeti(
        surum=str(veri.get("surum", "")),
        kaynak=veri.get("kaynak", ""),
        ayarlar=veri.get("ayarlar", {}),
        ibareler=veri.get("ibareler", {}),
        kurallar=veri.get("kurallar", []),
    )


def _ay_ekle(tarih: date, ay: int) -> date:
    yil = tarih.year + (tarih.month - 1 + ay) // 12
    yeni_ay = (tarih.month - 1 + ay) % 12 + 1
    son_gun = calendar.monthrange(yil, yeni_ay)[1]
    return date(yil, yeni_ay, min(tarih.day, son_gun))


def _sadece_ht_icin_doksazosin_mi(i: Ilac, tum_kodlar: list[str]) -> bool:
    """Ürün yalnızca doksazosin (Cardura vb.) içeriyorsa ve tanılarda N40 olmayıp
    Hipertansiyon (I10-I15) varsa True döner (BPH kurallarından muaf tutulur)."""
    maddeler = set(i.etken_maddeler.keys())
    if maddeler != {"doksazosin"}:
        return False
    n40_var = any(k.upper().startswith("N40") for k in tum_kodlar)
    ht_var = any(k.upper().startswith(("I10", "I11", "I12", "I13", "I15")) for k in tum_kodlar)
    return ht_var and not n40_var


def _gruplar(havuz: list[Ilac], kapsam: str) -> list[tuple[str, set[str]]]:
    if not havuz:
        return []
    if kapsam == "tumu":
        etiket = " + ".join(i.ad for i in havuz)
        tum_siniflar: set[str] = set()
        for i in havuz:
            tum_siniflar |= i.siniflar
        if not tum_siniflar:
            tum_siniflar = ilac.siniflari_bul(etiket)
        return [(etiket, tum_siniflar)]
    return [(i.ad, i.siniflar) for i in havuz]


def _tetiklendi_mi(tetikleyici: dict, siniflar: set[str]) -> bool:
    hepsi = set(tetikleyici.get("hepsi_bulunmali", []))
    herhangi = set(tetikleyici.get("herhangi_bulunmali", []))
    hicbiri = set(tetikleyici.get("hicbiri_bulunmamali", []))

    if hepsi and not hepsi.issubset(siniflar):
        return False
    if herhangi and not (herhangi & siniflar):
        return False
    if hicbiri & siniflar:
        return False
    return bool(hepsi or herhangi)


OLUMSUZLUK_KOKLERI = (
    "alinamam", "alinamad", "alinmad", "alinmam",
    "saglanamam", "saglanamad", "saglanmad", "saglanmam",
)


def _olumsuz_mu(cumle: str | None) -> bool:
    n = normalize(cumle or "")
    return any(kok in n for kok in OLUMSUZLUK_KOKLERI)


def _ibare_kurali(kural: dict, ks: KuralSeti, rapor: Rapor, etiket: str) -> Bulgu:
    tanim = ks.ibareler.get(kural.get("ibare", ""), {})
    sonuc = ibare_ara(
        rapor.serbest_metin,
        tanim.get("kaliplar", []),
        esik=float(tanim.get("esik", 0.85)),
    )
    baslik = kural.get("baslik", "İbare Kontrolü")

    if sonuc.bulundu and not _olumsuz_mu(sonuc.kanit):
        return Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=baslik,
            mesaj=kural.get("mesaj_yok", "").strip()
            + " Raporda benzer bir cümle var ama olumsuzluk içermiyor.",
            sut_madde=kural.get("sut_madde"),
            kanit=f"Bulunan cümle: {sonuc.kanit}",
            guven=round(sonuc.oran, 3),
        )

    if sonuc.bulundu:
        return Bulgu(
            kural_id=kural["id"],
            seviye="BILGI",
            baslik=baslik,
            mesaj=kural.get("mesaj_var", "İbare bulundu.").strip(),
            sut_madde=kural.get("sut_madde"),
            kanit=sonuc.kanit or None,
            guven=round(sonuc.oran, 3),
        )

    return Bulgu(
        kural_id=kural["id"],
        seviye=kural.get("seviye", "HATA"),
        baslik=baslik,
        mesaj=kural.get("mesaj_yok", "Gerekli ibare bulunamadı.").strip(),
        sut_madde=kural.get("sut_madde"),
        kanit=f"Tetikleyen ürün: {etiket}",
        guven=round(sonuc.oran, 3),
    )


def _ayrik_urun_kurali(kural: dict, havuz: list[Ilac]) -> list[Bulgu]:
    hedef = set(kural.get("siniflar", []))
    if not hedef or not havuz:
        return []
    havuzda: set[str] = set()
    for i in havuz:
        havuzda |= i.siniflar
    if not hedef.issubset(havuzda):
        return []
    for i in havuz:
        if hedef.issubset(i.siniflar):
            return []
    tasiyicilar = [i.ad for i in havuz if i.siniflar & hedef]
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "BILGI"),
            baslik=kural.get("baslik", "Ayrı Ürün Notu"),
            mesaj=kural.get("mesaj", "").strip(),
            sut_madde=kural.get("sut_madde"),
            kanit="Ayrı ürünler: " + ", ".join(tasiyicilar),
        )
    ]


def _kapsam_kurali(kural: dict, rapor: Rapor, recete: Recete | None) -> list[Bulgu]:
    if recete is None or not rapor.ilaclar:
        return []
    rapor_maddeleri: set[str] = set()
    for i in rapor.ilaclar:
        rapor_maddeleri |= set(i.etken_maddeler)
    muaf = [frozenset(s) for s in kural.get("muaf_siniflar", [])]
    bulgular: list[Bulgu] = []
    for r_ilac in recete.ilaclar:
        maddeler = set(r_ilac.etken_maddeler)
        if not maddeler or frozenset(r_ilac.siniflar) in muaf:
            continue
        if not maddeler.issubset(rapor_maddeleri):
            eksik = ", ".join(sorted(maddeler - rapor_maddeleri))
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"],
                    seviye=kural.get("seviye", "HATA"),
                    baslik=kural.get("baslik", "Rapor Kapsam Kontrolü"),
                    mesaj=f"Reçetedeki '{r_ilac.ad}' raporda yer almıyor.",
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Raporda bulunmayan etken madde: {eksik}",
                )
            )
    return bulgular


def _raporsuz_recete_kurali(kural: dict, ks: KuralSeti, recete: Recete | None) -> list[Bulgu]:
    if recete is None or recete.rapor_var:
        return []
    arb_urunleri = [i for i in recete.ilaclar if "ARB" in i.siniflar]
    if not arb_urunleri:
        return []
    sut = kural.get("sut_madde")
    etiket = ", ".join(i.ad for i in arb_urunleri)
    bulgular: list[Bulgu] = []
    azami = int(kural.get("azami_kutu", 1))
    if recete.arb_kutu_adedi is None:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_KUTU", seviye="UYARI",
            baslik="Raporsuz reçetede kutu sayısı girilmemiş",
            mesaj=f"Raporsuz ARB reçetesinde ayda en fazla {azami} kutu yazılabilir.",
            sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}",
        ))
    elif recete.arb_kutu_adedi > azami:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_KUTU", seviye=kural.get("seviye", "HATA"),
            baslik="Raporsuz ARB reçetesinde kutu sınırı aşılmış",
            mesaj=f"Raporsuz ARB reçetesinde ayda en fazla {azami} kutu yazılabilir.",
            sut_madde=sut,
            kanit=f"Girilen kutu sayısı: {recete.arb_kutu_adedi} · Tetikleyen ürün: {etiket}",
        ))
    kombine = [i.ad for i in arb_urunleri if "KKB" in i.siniflar]
    if kombine:
        ibare_kurali = {
            "id": kural["id"] + "_IBARE",
            "baslik": "Raporsuz ARB + KKB reçetesinde monoterapi ibaresi",
            "ibare": kural.get("ibare", ""),
            "seviye": kural.get("seviye", "HATA"),
            "sut_madde": sut,
            "mesaj_yok": "Raporsuz reçetede ARB + KKB içeren ürün var. Monoterapi ibaresi tespit edilemedi.",
            "mesaj_var": "Reçete açıklamasında gereken monoterapi ibaresi mevcut.",
        }
        bulgular.append(_ibare_kurali(ibare_kurali, ks, Rapor(serbest_metin=recete.aciklama), ", ".join(kombine)))
    return bulgular


def _tarih_kurali(kural: dict, rapor: Rapor, recete: Recete | None) -> list[Bulgu]:
    if recete is None or recete.tarih is None:
        return []
    sorunlar: list[str] = []
    if rapor.duzenleme_tarihi and recete.tarih < rapor.duzenleme_tarihi:
        sorunlar.append(f"reçete tarihi rapor düzenleme tarihinden ({rapor.duzenleme_tarihi}) önce")
    if rapor.bitis_tarihi and recete.tarih > rapor.bitis_tarihi:
        sorunlar.append(f"reçete tarihi rapor bitiş tarihinden ({rapor.bitis_tarihi}) sonra")
    if not sorunlar:
        return []
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural.get("baslik", "Rapor Tarih Kontrolü"),
            mesaj="Rapor bu reçeteyi kapsamıyor: " + "; ".join(sorunlar) + ".",
            sut_madde=kural.get("sut_madde"),
            kanit=f"Reçete tarihi: {recete.tarih}",
        )
    ]


def _tekil_sinif_kurali(kural: dict, havuz: list[Ilac]) -> list[Bulgu]:
    sinif = kural.get("sinif")
    azami = int(kural.get("azami_urun", 1))
    if not sinif:
        return []
    etken_maddeler: set[str] = set()
    urunler: list[str] = []
    for i in havuz:
        for ad, s in i.etken_maddeler.items():
            if s == sinif:
                etken_maddeler.add(ad)
                if i.ad not in urunler:
                    urunler.append(i.ad)
    if len(etken_maddeler) <= azami:
        return []
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural.get("baslik", "Kombinasyon Yasağı"),
            mesaj=kural.get("mesaj", "").strip(),
            sut_madde=kural.get("sut_madde"),
            kanit=f"Tespit edilen etken maddeler: {', '.join(sorted(etken_maddeler))} (Ürünler: {', '.join(urunler)})",
        )
    ]


_TIP2DM_DESENI = re.compile(r"tip\s*-?\s*2\s*(dm|diyabet)")
_GEBELIK_HAFTA_DESENI = re.compile(r"(\d+\s*\.?\s*gebelik\s+hafta|\d+\s*\.?\s*hafta\w*\s+gebe|gebelig\w*\s+\d+\s*\.?\s*hafta|gebelik\s+hafta)")


def _tani_kodu_ibare_kurali(
    kural: dict, ks: KuralSeti, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]
) -> list[Bulgu]:
    """Belirli tanı kodu önekleri (ör. E12-E14 veya gebelik O22/O30/Z32-Z35) +
    tetikleyici ilaç sınıfı varsa, rapor ya da reçete metninde ilgili ibareyi arar."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []

    onekler = tuple(str(k).upper() for k in kural.get("tani_onekleri", []))
    if not onekler:
        return []

    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])
    eslesen = [t for t in tum_kodlar if t.upper().startswith(onekler)]
    if not eslesen:
        return []

    etiket = ", ".join(tetikleyen)
    baslik = kural.get("baslik", "Tanı Kodu ve İbare Kontrolü")
    birlesik_ham = (rapor.serbest_metin or "") + " " + ((recete.aciklama if recete else "") or "")
    birlesik_norm = normalize(birlesik_ham)

    ibare_adi = kural.get("ibare")
    bulundu = False
    kanit_metni = ""

    if ibare_adi and ibare_adi in ks.ibareler:
        tanim = ks.ibareler[ibare_adi]
        sonuc = ibare_ara(
            birlesik_ham,
            tanim.get("kaliplar", []),
            esik=float(tanim.get("esik", 0.75)),
        )
        if sonuc.bulundu:
            bulundu = True
            kanit_metni = sonuc.kanit
        elif ibare_adi == "gebelik_haftasi_ifadesi":
            m = _GEBELIK_HAFTA_DESENI.search(birlesik_norm)
            if m:
                bulundu = True
                kanit_metni = m.group(0)
    else:
        m = _TIP2DM_DESENI.search(birlesik_norm)
        if m:
            bulundu = True
            kanit_metni = m.group(0)

    if bulundu:
        return [
            Bulgu(
                kural_id=kural["id"],
                seviye="BILGI",
                baslik=baslik,
                mesaj=kural.get("mesaj_var", "Gereken ifade mevcut.").strip(),
                sut_madde=kural.get("sut_madde"),
                kanit=f"Tanı kodu: {', '.join(eslesen)} · Bulunan ifade: '{kanit_metni}' · Ürün: {etiket}",
            )
        ]
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=baslik,
            mesaj=kural.get("mesaj_yok", "").strip(),
            sut_madde=kural.get("sut_madde"),
            kanit=f"Tanı kodu: {', '.join(eslesen)} · Tetikleyen ürün: {etiket}",
        )
    ]


def _cok_kaynakli_ibare_kurali(kural: dict, ks: KuralSeti, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []
    etiket = ", ".join(tetikleyen)
    birlesik_metin = (rapor.serbest_metin or "") + "\n" + ((recete.aciklama if recete else "") or "")
    return [_ibare_kurali(kural, ks, Rapor(serbest_metin=birlesik_metin), etiket)]


def _raporsuz_yasakli_urun_kurali(kural: dict, recete: Recete | None) -> list[Bulgu]:
    if recete is None or recete.rapor_var:
        return []
    anahtarlar = [normalize(a) for a in kural.get("markalar", [])]
    if not anahtarlar:
        return []
    bulgular: list[Bulgu] = []
    for i in recete.ilaclar:
        ad_norm = normalize(i.ad)
        for a in anahtarlar:
            if re.search(rf"\b{re.escape(a)}\b", ad_norm):
                bulgular.append(Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=kural.get("baslik", "Raporsuz Ödenmeyen Ürün"), mesaj=kural.get("mesaj", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {i.ad}"))
                break
    return bulgular


def _brans_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])
    suzulen_havuz = [i for i in havuz if not _sadece_ht_icin_doksazosin_mi(i, tum_kodlar)]
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(suzulen_havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []
    etiket = ", ".join(tetikleyen)
    izinli = [normalize(b) for b in kural.get("izinli_branslar", [])]
    baslik = kural.get("baslik", kural.get("baslik_yok", "Hekim Branş Kontrolü"))

    def izinli_mi(brans: str) -> bool:
        b = normalize(brans)
        return any(i in b for i in izinli)

    raporsuz = recete is not None and not recete.rapor_var
    if raporsuz:
        brans = recete.hekim_bransi
        if not brans:
            return [Bulgu(kural_id=kural["id"], seviye="UYARI", baslik=baslik, mesaj="Raporsuz reçetede hekim branşı girilmemiş. " + kural.get("mesaj_brans_yok", kural.get("mesaj_yok", "")).strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {etiket}")]
        if not izinli_mi(brans):
            return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=baslik, mesaj=kural.get("mesaj_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Reçeteyi yazan branş: {brans} · Tetikleyen ürün: {etiket}")]
        return []

    branslar = rapor.hekim_branslari or []
    if not branslar:
        return [Bulgu(kural_id=kural["id"], seviye="UYARI", baslik=baslik, mesaj="Rapor hekim branşı girilmemiş; raporu çıkaran hekimin branşını kontrol edin.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {etiket}")]
    if not any(izinli_mi(b) for b in branslar):
        return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=baslik, mesaj=kural.get("mesaj_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Rapor branşı: {', '.join(branslar)} · Tetikleyen ürün: {etiket}")]
    return []


def _doz_bul(urun_adi: str) -> float | None:
    eslesme = re.search(r"(\d+(?:[.,]\d+)?)\s*mg", urun_adi, re.IGNORECASE)
    return float(eslesme.group(1).replace(",", ".")) if eslesme else None


def _doz_siniri_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyici = kural.get("tetikleyici", {})
    hedef_madde = tetikleyici.get("herhangi_bulunmali", [""])[0]
    tetikleyen_urunler = [e for e, s in _gruplar(havuz, "urun") if hedef_madde in s]
    if not tetikleyen_urunler:
        return []
    min_doz = float(kural.get("min_doz", 999))
    izinli = [normalize(b) for b in kural.get("izinli_branslar", [])]
    baslik = kural.get("baslik", "Doz Sınırı Kontrolü")
    bulgular = []
    for urun in tetikleyen_urunler:
        doz = _doz_bul(urun)
        if doz is None or doz < min_doz:
            continue
        if recete is not None and not recete.rapor_var:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik=baslik, mesaj=f"Yüksek doz statin ({min_doz} mg ve üzeri) raporsuz ödenmez.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {urun} (Okunan doz: {doz} mg)"))
            continue
        branslar = rapor.hekim_branslari or []
        if not branslar:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="UYARI", baslik=baslik, mesaj=f"Rapor hekim branşı girilmemiş. {min_doz} mg ve üzeri doz için rapor branşı kontrol edilmeli.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {urun}"))
            continue
        if not any(any(i in normalize(b) for i in izinli) for b in branslar):
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik=baslik, mesaj=kural.get("mesaj_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Rapor branşı: {', '.join(branslar)} · Tetikleyen ürün: {urun} (Okunan doz: {doz} mg)"))
    return bulgular


def _ldl_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    hedef_maddeler = kural.get("tetikleyici", {}).get("herhangi_bulunmali", [])
    tetikleyen_urunler = [e for e, s in _gruplar(havuz, "urun") if any(m in s for m in hedef_maddeler)]
    if not tetikleyen_urunler:
        return []
    etiket = ", ".join(tetikleyen_urunler)
    bulgular = []
    if rapor.idame_mi:
        if rapor.ldl_degeri is None:
            bulgular.append(Bulgu(kural_id=kural["id"]+"_IDAME_EKS", seviye="HATA", baslik="Eksik Bilgi (İdame Rapor)", mesaj="İdame raporlarında hastanın tedaviye İLK BAŞLADIĞI tarihteki LDL değeri raporda MUTLAKA belirtilmelidir.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {etiket}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"]+"_IDAME_OK", seviye="BILGI", baslik="İdame Rapor Kriterleri", mesaj="İdame rapor seçildi ve başlangıç LDL değeri mevcut. Hastanın tedaviye 6 aydan uzun süre ara vermediğini kontrol edin.", sut_madde=kural.get("sut_madde"), kanit=f"Başlangıç LDL: {rapor.ldl_degeri} | Tetikleyen: {etiket}"))
        return bulgular
    if rapor.ldl_degeri is None:
        return [Bulgu(kural_id=kural["id"]+"_LDL_EKS", seviye="UYARI", baslik="LDL Değeri Eksik", mesaj="İlk raporlarda tahlildeki LDL değeri girilmelidir.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {etiket}")]
    ldl = rapor.ldl_degeri
    iki_tahlil = False
    if rapor.ldl_degeri_2 is not None and rapor.ldl_tarihi_2 is not None and rapor.ldl_tarihi is not None:
        gun_farki = abs((rapor.ldl_tarihi - rapor.ldl_tarihi_2).days)
        if gun_farki >= 7:
            iki_tahlil = True
            ldl = min(rapor.ldl_degeri, rapor.ldl_degeri_2)
        else:
            return [Bulgu(kural_id=kural["id"]+"_GUN_FARKI", seviye="HATA", baslik="Tahlil Süresi Yetersiz", mesaj="İki LDL tahlili arasında en az 7 gün olmalıdır.", sut_madde=kural.get("sut_madde"), kanit=f"Fark: {gun_farki} gün")]
    if rapor.ldl_tarihi and rapor.duzenleme_tarihi and (rapor.duzenleme_tarihi - rapor.ldl_tarihi).days > 185:
        return [Bulgu(kural_id=kural["id"]+"_TARIH", seviye="HATA", baslik="Tahlil Tarihi Eski", mesaj="Tahlil tarihi, rapor düzenleme tarihinden en fazla 6 ay önce olabilir.", sut_madde=kural.get("sut_madde"), kanit=f"Tahlil: {rapor.ldl_tarihi.strftime('%d.%m.%Y')}")]
    elif not rapor.ldl_tarihi:
        bulgular.append(Bulgu(kural_id=kural["id"]+"_TAR_EKS", seviye="UYARI", baslik="Tahlil Tarihi Eksik", mesaj="6 aylık geçerlilik süresinin kontrolü için tahlil tarihini girin.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {etiket}"))
    riskler = rapor.risk_faktorleri or []
    yuksek_risk_listesi = ["Diyabet (Diabetes Mellitus)", "Geçirilmiş MI / Akut Koroner Sendrom", "Geçirilmiş İnme", "Koroner Arter Hastalığı (KAH)", "Periferik Arter Hastalığı (PAH)", "Abdominal Aort Anevrizması", "Karotis Arter Hastalığı"]
    ek_risk_listesi = ["Hipertansiyon", "Ailede erken kardiyovasküler hastalık öyküsü", "65 yaş ve üzeri"]
    hastadaki_yuksek = [r for r in riskler if r in yuksek_risk_listesi]
    hastadaki_ek = [r for r in riskler if r in ek_risk_listesi]
    ek_sayi = len(hastadaki_ek)
    if hastadaki_yuksek:
        if ldl > 70:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 70 ve Yüksek Risk", mesaj="Yüksek riskli hastalık mevcut. Tek tahlil yeterlidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Hastalık: {', '.join(hastadaki_yuksek)}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="LDL Kriteri Sağlanmadı", mesaj="Yüksek riskli hastalıklarda LDL > 70 olmalıdır.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    elif ldl > 190:
        bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI" if iki_tahlil else "HATA", baslik="LDL > 190" if iki_tahlil else "Eksik Tahlil (LDL > 190)", mesaj="LDL > 190 ve 2 tahlil mevcut." if iki_tahlil else "LDL > 190 iken en az 1 hafta arayla 2 tahlil gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    elif ldl > 160:
        if ek_sayi >= 2 and iki_tahlil:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 160", mesaj="LDL > 160, en az 2 ek risk ve 2 tahlil mevcut.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
        elif ek_sayi < 2:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Yetersiz Ek Risk Faktörü", mesaj="LDL 160-190 arasında en az 2 ek risk faktörü gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Girilen: {ek_sayi}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Eksik Tahlil (LDL > 160)", mesaj="LDL 160-190 arasında 1 hafta arayla 2 tahlil gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    elif ldl > 130:
        if ek_sayi >= 3 and iki_tahlil:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 130", mesaj="LDL > 130, en az 3 ek risk ve 2 tahlil mevcut.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
        elif ek_sayi < 3:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Yetersiz Ek Risk Faktörü", mesaj="LDL 130-160 arasında en az 3 ek risk faktörü gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Girilen: {ek_sayi}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Eksik Tahlil (LDL > 130)", mesaj="LDL 130-160 arasında 1 hafta arayla 2 tahlil gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="LDL Kriteri Sağlanmadı", mesaj="LDL 130'un altında ve yüksek riskli hastalık yok.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    return bulgular


def _doksazosin_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Doksazosin (Cardura vb.) hem Hipertansiyon (I10-I15) hem BPH (N40) için kullanılır.
    Girilen tanı koduna göre hangi Medula uyarı kodunun seçileceğini bildirir."""
    doks_urunler = [i.ad for i in havuz if "doksazosin" in i.etken_maddeler]
    if not doks_urunler:
        return []

    etiket = ", ".join(dict.fromkeys(doks_urunler))
    sut = kural.get("sut_madde", "SUT 13.3 / EK-4/A")
    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])

    n40_var = any(k.upper().startswith("N40") for k in tum_kodlar)
    ht_var = any(k.upper().startswith(("I10", "I11", "I12", "I13", "I15")) for k in tum_kodlar)

    if ht_var and not n40_var:
        return [Bulgu(
            kural_id=kural["id"] + "_HT",
            seviye="BILGI",
            baslik="Doksazosin (Cardura): Hipertansiyon Endikasyonu ve Uyarı Kodu",
            mesaj=(
                f"Reçete/Raporda Hipertansiyon tanı kodu mevcut, N40 (BPH) tanı kodu yok. "
                f"'{etiket}' Hipertansiyon endikasyonunda değerlendirildi (Üroloji branş şartı aranmaz). "
                "Medula'da mutlaka HİPERTANSİYON UYARI KODU seçilmelidir!"
            ),
            sut_madde=sut,
            kanit=f"Ürün: {etiket} · Tanı: Hipertansiyon"
        )]
    elif n40_var and not ht_var:
        return [Bulgu(
            kural_id=kural["id"] + "_BPH",
            seviye="BILGI",
            baslik="Doksazosin (Cardura): BPH (Prostat) Endikasyonu ve Uyarı Kodu",
            mesaj=(
                f"Reçete/Raporda N40 (BPH) tanı kodu mevcut. "
                f"'{etiket}' Prostat (BPH - SUT 13.3) kapsamında değerlendirildi (Üroloji uzmanı şartı ve 1 yıllık rapor süresi aranır). "
                "Medula'da mutlaka BPH UYARI KODU seçilmelidir!"
            ),
            sut_madde=sut,
            kanit=f"Ürün: {etiket} · Tanı: N40 (BPH)"
        )]
    elif n40_var and ht_var:
        return [Bulgu(
            kural_id=kural["id"] + "_IKISI",
            seviye="BILGI",
            baslik="Doksazosin (Cardura): Hem Hipertansiyon Hem BPH (N40) Tanısı Mevcut",
            mesaj=(
                f"Belgede hem Hipertansiyon (I10-I15) hem de BPH (N40) tanı kodu yer alıyor. "
                "Reçeteyi yazan hekim branşına ve rapor türüne göre Medula'da uygun uyarı kodunu (HT tanısıyla Aile Hekimi/Dahiliye yazdıysa Hipertansiyon uyarı kodu; Üroloji BPH için yazdıysa BPH uyarı kodu) seçiniz."
            ),
            sut_madde=sut,
            kanit=f"Ürün: {etiket} · Tanılar: {', '.join(tum_kodlar)}"
        )]
    return []


def _tani_kodu_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])
    suzulen_havuz = [i for i in havuz if not _sadece_ht_icin_doksazosin_mi(i, tum_kodlar)]
    tetikleyen = [e for e, s in _gruplar(suzulen_havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    beklenen = tuple(k.upper() for k in kural.get("zorunlu_kodlar", []))
    if not beklenen:
        return []

    raporsuz = recete is not None and not recete.rapor_var
    if raporsuz and kural.get("raporsuz_tani_kaynagi") == "recete":
        kaynak_kodlar = (recete.tani_kodlari if recete else []) or []
    elif not raporsuz and kural.get("raporlu_tani_kaynagi") == "rapor":
        kaynak_kodlar = rapor.tani_kodlari or []
    else:
        kaynak_kodlar = tum_kodlar

    eslesenler = [t for t in kaynak_kodlar if any(t.upper().startswith(b) for b in beklenen)]
    if eslesenler:
        if kural.get("mesaj_var"):
            return [Bulgu(
                kural_id=kural["id"] + "_OK",
                seviye="BILGI",
                baslik=kural.get("baslik", "Tanı Kodu Kontrolü"),
                mesaj=kural["mesaj_var"].strip(),
                sut_madde=kural.get("sut_madde"),
                kanit=f"Bulunan Tanı Kodu: {', '.join(eslesenler)} · Ürün: {', '.join(tetikleyen)}"
            )]
        return []

    return [Bulgu(
        kural_id=kural["id"],
        seviye=kural.get("seviye", "HATA"),
        baslik=kural.get("baslik", "Tanı Kodu Eksik"),
        mesaj=kural.get("mesaj_yok", "").strip(),
        sut_madde=kural.get("sut_madde"),
        kanit=f"Tetikleyen: {', '.join(tetikleyen)} | Aranan: {', '.join(beklenen)} | Mevcut: {', '.join(kaynak_kodlar) if kaynak_kodlar else 'Yok'}"
    )]


def _rapor_yetki_sure_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    raporsuz = recete is not None and not recete.rapor_var
    if kural.get("yalniz_raporlu", True) and raporsuz:
        return []

    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])
    suzulen_havuz = [i for i in havuz if not _sadece_ht_icin_doksazosin_mi(i, tum_kodlar)]
    tetikleyen = [e for e, s in _gruplar(suzulen_havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []

    etiket = ", ".join(tetikleyen)
    sut = kural.get("sut_madde")
    baslik = kural.get("baslik", "Rapor Yetki ve Süre Kontrolü")
    bulgular: list[Bulgu] = []

    if not rapor.duzenleme_tarihi or not rapor.bitis_tarihi:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_TARIH_EKSIK",
            seviye="UYARI",
            baslik=baslik,
            mesaj="Rapor düzenleme veya bitiş tarihi eksik; azami rapor süresi doğrulanamadı.",
            sut_madde=sut,
            kanit=f"Tetikleyen ürün: {etiket}"
        ))
        return bulgular

    azami_ay = int(kural.get("azami_sure_ay", 12))
    azami_bitis = _ay_ekle(rapor.duzenleme_tarihi, azami_ay)
    etkili_bitis = min(rapor.bitis_tarihi, azami_bitis)

    if rapor.bitis_tarihi > azami_bitis:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_SURE_ASIMI",
            seviye=kural.get("seviye", "HATA"),
            baslik=baslik,
            mesaj=kural.get("mesaj_yok", "").strip() + f" (Rapor süresi azami {azami_ay} takvim ayını aşıyor!)",
            sut_madde=sut,
            kanit=f"Düzenleme: {rapor.duzenleme_tarihi.strftime('%d.%m.%Y')} · Bitiş: {rapor.bitis_tarihi.strftime('%d.%m.%Y')} · Azami Bitiş ({azami_ay} ay): {azami_bitis.strftime('%d.%m.%Y')}"
        ))

    if kural.get("recete_tarihi_rapor_araliginda_olmali", True) and recete and recete.tarih:
        if recete.tarih < rapor.duzenleme_tarihi or recete.tarih > etkili_bitis:
            bulgular.append(Bulgu(
                kural_id=kural["id"] + "_RECETE_ARALIK_DISI",
                seviye=kural.get("seviye", "HATA"),
                baslik=baslik,
                mesaj=f"Reçete tarihi ({recete.tarih.strftime('%d.%m.%Y')}), raporun geçerli tarih aralığı ({rapor.duzenleme_tarihi.strftime('%d.%m.%Y')} - {etkili_bitis.strftime('%d.%m.%Y')}) dışında!",
                sut_madde=sut,
                kanit=f"Tetikleyen ürün: {etiket}"
            ))

    return bulgular


def _etken_madde_birliktelik_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    hedef_maddeler = {normalize(m) for m in kural.get("etken_maddeler", [])}
    azami = int(kural.get("azami_farkli_etken_madde", 1))
    if not hedef_maddeler:
        return []

    tum_kodlar = list(rapor.tani_kodlari or []) + (list(recete.tani_kodlari or []) if recete else [])
    ht_tani_var = any(k.upper().startswith(("I10", "I11", "I12", "I13", "I15")) for k in tum_kodlar)

    kapsam = kural.get("kapsam", "belge_ayri")
    belge_listeleri: list[tuple[str, list[Ilac]]] = []
    if kapsam == "belge_ayri":
        if rapor.ilaclar:
            belge_listeleri.append(("Rapor", rapor.ilaclar))
        if recete and recete.ilaclar:
            belge_listeleri.append(("Reçete", recete.ilaclar))
    else:
        belge_listeleri.append(("Toplam", havuz))

    bulgular: list[Bulgu] = []
    sut = kural.get("sut_madde")
    baslik = kural.get("baslik", "Etken Madde Birliktelik Kontrolü")

    for belge_adi, liste in belge_listeleri:
        bulunan_maddeler: set[str] = set()
        ilgili_urunler: list[str] = []
        for urun in liste:
            urun_maddeleri = {normalize(k) for k in urun.etken_maddeler.keys()}
            kesisim = urun_maddeleri & hedef_maddeler
            if kesisim:
                bulunan_maddeler |= kesisim
                if urun.ad not in ilgili_urunler:
                    ilgili_urunler.append(urun.ad)

        if len(bulunan_maddeler) > azami:
            kanit_metni = f"{belge_adi} içinde birlikte bulunanlar: {', '.join(sorted(bulunan_maddeler))} ({', '.join(ilgili_urunler)})"
            if not kural.get("hipertansiyon_istisnasi_yok", False) and "doksazosin" in bulunan_maddeler and ht_tani_var:
                bulgular.append(Bulgu(
                    kural_id=kural["id"] + f"_{belge_adi.upper()}_HT_ISTISNA",
                    seviye="BILGI",
                    baslik=baslik,
                    mesaj=kural.get("mesaj_istisna", "Hipertansiyon tanı kodu ve Doksazosin mevcut olduğundan kombinasyon kısıtlaması uygulanmadı.").strip(),
                    sut_madde=sut,
                    kanit=kanit_metni
                ))
                continue

            bulgular.append(Bulgu(
                kural_id=kural["id"] + f"_{belge_adi.upper()}",
                seviye=kural.get("seviye", "HATA"),
                baslik=baslik,
                mesaj=kural.get("mesaj", "").strip(),
                sut_madde=sut,
                kanit=kanit_metni
            ))

    return bulgular


# Yaygın SGK Rapor Kodları ve altında beklenen ICD-10 önekleri
RAPOR_KODU_ICD_UYUMU: dict[str, tuple[str, tuple[str, ...]]] = {
    "04.05": ("Arteriyel Hipertansiyon", ("I10", "I11", "I12", "I13", "I15")),
    "04.02": ("Koroner Arter Hastalığı", ("I20", "I21", "I22", "I24", "I25", "Z95")),
    "04.01": ("Kalp Yetmezliği", ("I50", "I11.0", "I13.0", "I42")),
    "04.04": ("Periferik ve Serebral Damar Hastalıkları", ("I63", "I64", "I65", "I66", "I67", "I69", "I70", "I73", "G45")),
    "04.08": ("Herediter / Kazanılmış Faktör Eksiklikleri / Tromboz", ("I26", "I80", "I82", "D68", "O22", "Z34", "Z35")),
    "07.02.1": ("Diabetes Mellitus", ("E10", "E11", "E12", "E13", "E14")),
    "08.01": ("Lipid Metabolizması Bozuklukları", ("E78",)),
}


def _rapor_kodu_bilgi_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    raporsuz = recete is not None and not recete.rapor_var
    if kural.get("yalniz_raporlu", True) and raporsuz:
        return []
    tetikleyen = [e for e, s in _gruplar(havuz, kural.get("kapsam", "tumu")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []

    girilen_rkodlar = [k.strip() for k in (getattr(rapor, "rapor_kodlari", None) or []) if k.strip()]
    beklenen_rkodlar = [str(k).strip() for k in kural.get("yaygin_rapor_kodlari", [])]

    if beklenen_rkodlar and girilen_rkodlar:
        if any(any(g.startswith(b) for b in beklenen_rkodlar) for g in girilen_rkodlar):
            return [Bulgu(
                kural_id=kural["id"] + "_OK",
                seviye="BILGI",
                baslik=kural.get("baslik", "Rapor Kodu Doğrulandı"),
                mesaj=f"Rapor kodu ({', '.join(girilen_rkodlar)}) uyumlu.",
                sut_madde=kural.get("sut_madde"),
                kanit=f"Rapor Kodu: {', '.join(girilen_rkodlar)} · Ürün: {', '.join(tetikleyen)}"
            )]

    return [Bulgu(
        kural_id=kural["id"],
        seviye=kural.get("seviye", "BILGI"),
        baslik=kural.get("baslik", "Rapor Kodu Bilgilendirmesi"),
        mesaj=kural.get("mesaj", "").strip(),
        sut_madde=kural.get("sut_madde"),
        kanit=f"Mevcut Rapor Kodu: {', '.join(girilen_rkodlar) if girilen_rkodlar else 'Belirtilmedi'} · Tetikleyen: {', '.join(tetikleyen)}"
    )]


def _rapor_kodu_icd_uyum_kontrolu(rapor: Rapor, recete: Recete | None) -> list[Bulgu]:
    """Raporda üst başlık olarak girilen Rapor Kodu (örn. 04.05) ile altındaki ICD-10
    tanı kodlarının (örn. I10) birbiriyle örtüşüp örtüşmediğini otomatik denetler."""
    if recete is not None and not recete.rapor_var:
        return []
    rkodlar = [k.strip() for k in (getattr(rapor, "rapor_kodlari", None) or []) if k.strip()]
    icd_kodlar = [k.strip().upper() for k in (rapor.tani_kodlari or []) if k.strip() and not k.strip()[0].isdigit()]
    if not rkodlar or not icd_kodlar:
        return []

    bulgular: list[Bulgu] = []
    for rkod in rkodlar:
        for anahtar, (ad, beklenen_icdler) in RAPOR_KODU_ICD_UYUMU.items():
            if rkod.startswith(anahtar):
                eslesen_icd = [i for i in icd_kodlar if i.startswith(beklenen_icdler)]
                if not eslesen_icd:
                    bulgular.append(Bulgu(
                        kural_id=f"RAPOR_ICD_UYUMSUZ_{anahtar}",
                        seviye="UYARI",
                        baslik=f"Rapor Kodu ({rkod}) ile Alt ICD-10 Tanı Kodu Uyumsuzluğu!",
                        mesaj=(
                            f"Raporda '{rkod} - {ad}' rapor kodu yer alıyor ancak bu rapor kodunun altında beklenen "
                            f"ICD-10 tanı kodlarından ({', '.join(beklenen_icdler)}...) hiçbiri tespit edilemedi! "
                            "Medula'da üst rapor kodu ile alt ICD-10 kodunun uyumlu olduğundan emin olun."
                        ),
                        sut_madde="SGK Medula Rapor/ICD-10 Kontrolü",
                        kanit=f"Rapor Kodu: {rkod} · Rapordaki ICD-10 Kodları: {', '.join(icd_kodlar)}"
                    ))
    return bulgular


def _yasakli_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyen = [e for e, s in _gruplar(havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    metin = normalize(rapor.serbest_metin or "")
    bulunanlar = [k for k in kural.get("yasakli_kaliplar", []) if normalize(k) in metin]
    if not bulunanlar and any(a in metin for a in ("asa", "aspirin", "asetilsalisilik", "coraspin", "ecopirin")):
        if any(x in metin for x in ("intolerans", "duyarlilik", "alerji", "kontrendik", "gis kanama", "mide kanama")):
            bulunanlar = ["ASA (Aspirin) intoleransı / kontrendikasyonu ibaresi"]
    if bulunanlar:
        asa_urunleri = [i.ad for i in havuz if "ASA" in i.siniflar]
        hedef = ", ".join(asa_urunleri) if asa_urunleri else ", ".join(tetikleyen)
        return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=kural.get("baslik", "Çelişen İbare Tespit Edildi"), mesaj=kural.get("mesaj", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"ASA İçeren Ürün: {hedef} | Rapordaki Engel: '{bulunanlar[0]}'")]
    return []


def _aranan_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyen = [e for e, s in _gruplar(havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    metin = (rapor.serbest_metin or "").lower()
    bulunanlar = [k for k in kural.get("aranan_kaliplar", []) if k.lower() in metin]
    if bulunanlar:
        return [Bulgu(kural_id=kural["id"] + "_VAR", seviye="BILGI", baslik=kural.get("baslik_var", "Şartlar Sağlandı"), mesaj=kural.get("mesaj_var", "Raporda gerekli ibare tespit edildi.").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Bulunan İbare: '{bulunanlar[0].upper()}'")]
    return [Bulgu(kural_id=kural["id"] + "_YOK", seviye=kural.get("seviye", "UYARI"), baslik=kural.get("baslik_yok", "Eksik İbare"), mesaj=kural.get("mesaj_yok", "Gerekli ibare bulunamadı.").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen Ürün: {', '.join(tetikleyen)}")]


def _osteoporoz_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyen = [e for e, s in _gruplar(havuz, "urun") if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    metin = (rapor.serbest_metin or "").lower()
    yas = getattr(rapor, "hasta_yasi", 65) or 65
    t_skoru = getattr(rapor, "t_skoru", None)
    if yas >= 75:
        return [Bulgu(kural_id=kural["id"]+"_YAS", seviye="BILGI", baslik="75 Yaş Üzeri (Skor Aranmaz)", mesaj=f"Hasta {yas} yaşında. 75 yaş ve üzeri hastalarda T-Skoru aranmaksızın ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Girilen Yaş: {yas}")]
    if "patolojik kırık" in metin or "patolojik kirik" in metin:
        if t_skoru is not None and t_skoru <= -1.0:
            return [Bulgu(kural_id=kural["id"]+"_KIRIK_OK", seviye="BILGI", baslik="Patolojik Kırık Mevcut", mesaj=f"Raporda kırık mevcut. T-Skoru ({t_skoru}) <= -1.0. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"T-Skoru: {t_skoru}")]
        elif t_skoru is None:
            return [Bulgu(kural_id=kural["id"]+"_KIRIK_EKS", seviye="HATA", baslik="T-Skoru Eksik", mesaj="Kırığı olan hastalarda T-Skorunun en az -1.0 olması gerekir.", sut_madde=kural.get("sut_madde"), kanit="")]
        return [Bulgu(kural_id=kural["id"]+"_KIRIK_HATA", seviye="HATA", baslik="Kırık Var Ama Skor Yetersiz!", mesaj=f"Patolojik kırığı olanlarda T-Skoru en fazla -1.0 olabilir. Girilen: {t_skoru}.", sut_madde=kural.get("sut_madde"), kanit=f"T-Skoru: {t_skoru}")]
    if t_skoru is None:
        return [Bulgu(kural_id=kural["id"]+"_EKS", seviye="HATA", baslik="DEXA T-Skoru Eksik", mesaj="Osteoporoz tespiti için DEXA T-Skorunu girmelisiniz.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {', '.join(tetikleyen)}")]
    if yas >= 65:
        if t_skoru <= -2.5:
            return [Bulgu(kural_id=kural["id"]+"_65_OK", seviye="BILGI", baslik="65+ Yaş Uygun", mesaj=f"{yas} yaşındaki hastada T-Skoru ({t_skoru}) <= -2.5. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]
        return [Bulgu(kural_id=kural["id"]+"_65_HATA", seviye="HATA", baslik="Yetersiz T-Skoru!", mesaj=f"65 yaş ve üzeri hastalarda T-Skoru en az -2.5 olmalıdır. Girilen: {t_skoru}.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]
    if t_skoru <= -3.0:
        return [Bulgu(kural_id=kural["id"]+"_GENC_OK", seviye="BILGI", baslik="65 Yaş Altı Uygun", mesaj=f"{yas} yaşındaki hastada T-Skoru ({t_skoru}) <= -3.0. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]
    return [Bulgu(kural_id=kural["id"]+"_GENC_HATA", seviye="HATA", baslik="Yetersiz T-Skoru!", mesaj=f"65 yaş altı hastalarda T-Skoru en az -3.0 olmalıdır. Girilen: {t_skoru}.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]


def _rapor_suresi_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    if recete is not None and not recete.rapor_var:
        return []
    tetikleyen = [e for e, s in _gruplar(havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen or not rapor.duzenleme_tarihi or not rapor.bitis_tarihi:
        return []
    azami_gun = int(kural.get("azami_gun", 366))
    gun_farki = (rapor.bitis_tarihi - rapor.duzenleme_tarihi).days
    if gun_farki > azami_gun:
        return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=kural.get("baslik", "Rapor Süresi Aşıldı"), mesaj=kural.get("mesaj", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Rapor süresi: {gun_farki} gün ({rapor.duzenleme_tarihi.strftime('%d.%m.%Y')} - {rapor.bitis_tarihi.strftime('%d.%m.%Y')})")]
    return []


def _raporsuz_klopidogrel_kurali(kural: dict, recete: Recete | None) -> list[Bulgu]:
    if recete is None or recete.rapor_var:
        return []
    urunler = [i for i in recete.ilaclar if "KLOPIDOGREL" in i.siniflar]
    if not urunler:
        return []
    etiket = ", ".join(i.ad for i in urunler)
    sut = kural.get("sut_madde", "SUT 4.2.15.A")
    bulgular: list[Bulgu] = []
    if recete.arb_kutu_adedi is not None and recete.arb_kutu_adedi > 1:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_KUTU", seviye="HATA", baslik="Raporsuz Klopidogrel Kutu Sınırı Aşıldı! (Max 1 Kutu)", mesaj="Raporsuz Klopidogrel en fazla 4 haftalık doz (1 KUTU) olarak ödenir.", sut_madde=sut, kanit=f"Girilen kutu: {recete.arb_kutu_adedi} · Ürün: {etiket}"))
    bulgular.append(Bulgu(kural_id=kural["id"] + "_BILGI", seviye="UYARI", baslik="Raporsuz Klopidogrel Ödeme Şartı (Stent / Taburculuk)", mesaj="Raporsuz Klopidogrel yalnızca; koroner stent öncesi (24 saat içinde) veya stent/girişimsel işlem sonrası taburculuktan itibaren 4 haftalık doz (1 KUTU) olarak ilgili uzman hekimlerce reçete edilebilir.", sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}"))
    return bulgular


def _aile_hekimi_rapor_uyarisi(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    if recete is not None and not recete.rapor_var:
        return []
    tetikleyen = [e for e, s in _gruplar(havuz, kural.get("kapsam", "urun")) if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    branslar = [normalize(b) for b in (rapor.hekim_branslari or [])]
    if any("aile hekim" in b for b in branslar):
        return [Bulgu(kural_id=kural["id"], seviye="UYARI", baslik=kural.get("baslik", "Aile Hekimi Rapor Uyarısı"), mesaj=kural.get("mesaj", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Rapor Branşı: Aile Hekimliği · Ürün: {', '.join(tetikleyen)}")]
    return []


def _noak_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []

    etiket = ", ".join(tetikleyen)
    sut = kural.get("sut_madde", "SUT 4.2.15.D-1")

    if recete is not None and not recete.rapor_var:
        return [Bulgu(
            kural_id=kural["id"] + "_RAPORSUZ",
            seviye="HATA",
            baslik="KESİNTİ RİSKİ: NOAK Raporsuz Ödenmez!",
            mesaj="Dabigatran, Rivaroksaban, Edoksaban ve Apiksaban raporsuz olarak SGK kapsamında kesinlikle ödenmez.",
            sut_madde=sut,
            kanit=f"Tetikleyen ürün: {etiket}"
        )]

    metin = normalize(rapor.serbest_metin or "")
    kodlar = [k.upper().strip() for k in (rapor.tani_kodlari or [])]
    olumsuzluk_kelimeleri = ("olmayan", "bulunmayan", "yok", "yoktur", "degil", "izlenmedi", "saptanmadi", "mevcut degil", "haric")
    bulgular: list[Bulgu] = []

    # 1. Mitral Darlık
    mitral_gecti = "mitral" in metin
    mitral_olumsuz = False
    if mitral_gecti:
        for m in re.finditer(r"mitral", metin):
            pencere = metin[max(0, m.start() - 35): min(len(metin), m.end() + 65)]
            if any(neg in pencere for neg in olumsuzluk_kelimeleri):
                mitral_olumsuz = True
                break

    if mitral_gecti and mitral_olumsuz:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_MITRAL_OK", seviye="BILGI", baslik="1. Mitral Darlık Kontrolü: UYGUN", mesaj="Raporda hastada orta veya ciddi mitral darlık olmadığı yazılmış.", sut_madde=sut, kanit="orta/ciddi mitral darlık yok"))
    elif mitral_gecti and not mitral_olumsuz:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_MITRAL_VAR", seviye="HATA", baslik="1. Mitral Darlık Kontrolü: HATA (Mitral Darlık Mevcut / Olumsuzluk Yok)", mesaj="Raporda 'mitral darlık' ifadesi geçiyor ancak 'olmadığı / yoktur' ibaresi tespit edilemedi!", sut_madde=sut, kanit="Mitral darlık ifadesini kontrol edin."))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_MITRAL_EKS", seviye="HATA", baslik="1. Mitral Darlık Kontrolü: EKSİK İBARE!", mesaj="Raporda hastada 'orta veya ciddi mitral darlık olmadığı' açıkça belirtilmemiştir!", sut_madde=sut, kanit="Aranan ibare: 'orta-ciddi mitral darlık olmayan / yoktur'"))

    # 2. Mekanik Protez Kapak
    kapak_gecti = any(k in metin for k in ("mekanik protez", "mekanik kapak", "protez kapak", "kalp kapagi"))
    kapak_olumsuz = False
    if kapak_gecti:
        for kalip in ("mekanik protez", "mekanik kapak", "protez kapak", "kalp kapagi"):
            for m in re.finditer(kalip, metin):
                pencere = metin[max(0, m.start() - 35): min(len(metin), m.end() + 65)]
                if any(neg in pencere for neg in olumsuzluk_kelimeleri):
                    kapak_olumsuz = True
                    break

    if kapak_gecti and kapak_olumsuz:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_KAPAK_OK", seviye="BILGI", baslik="2. Mekanik Protez Kapak Kontrolü: UYGUN", mesaj="Raporda hastada mekanik protez kapağı olmadığı belirtilmiş.", sut_madde=sut, kanit="Mekanik protez kapak yok"))
    elif kapak_gecti and not kapak_olumsuz:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_KAPAK_VAR", seviye="HATA", baslik="2. Mekanik Protez Kapak Kontrolü: HATA (Protez Kapak Mevcut!)", mesaj="Raporda protez kapak ifadesi var ancak 'olmadığı / yoktur' ibaresi tespit edilemedi!", sut_madde=sut, kanit="Mekanik protez kapak ifadesini kontrol edin."))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_KAPAK_EKS", seviye="HATA", baslik="2. Mekanik Protez Kapak Kontrolü: EKSİK İBARE!", mesaj="Raporda hastada 'mekanik protez kapağı olmadığı' açıkça belirtilmemiştir!", sut_madde=sut, kanit="Aranan ibare: 'mekanik protez kapağı olmayan / yoktur'"))

    # 3. Teşhis Kontrolü
    nvaf_var = any(k in metin for k in ("nonvalvuler", "non valvuler", "nvaf", "atriyal fibrilasyon", "atrial fibrilasyon"))
    dvt_pe_var = any(k in metin for k in ("derin ven", "dvt", "pulmoner emboli", "pulmoner tromboemboli")) or any(k.startswith(("I80", "I82", "I26")) for k in kodlar)

    if any(k in metin for k in ("nonvalvuler", "non valvuler", "nvaf")):
        bulgular.append(Bulgu(kural_id=kural["id"] + "_NVAF_OK", seviye="BILGI", baslik="3. Teşhis Kontrolü: Non-Valvuler Atriyal Fibrilasyon (NVAF) Var", mesaj="Raporda Non-Valvuler Atriyal Fibrilasyon (NVAF) tanısı mevcut.", sut_madde=sut, kanit="Non-Valvuler Atriyal Fibrilasyon (NVAF) var"))
    elif nvaf_var or any(k.startswith("I48") for k in kodlar):
        bulgular.append(Bulgu(kural_id=kural["id"] + "_NVAF_UYARI", seviye="UYARI", baslik="3. Teşhis Kontrolü: AF Var Ama 'Non-Valvuler' İbaresi Eksik Olabilir", mesaj="Raporda Atriyal Fibrilasyon (I48) görülüyor ancak 'Non-Valvuler (NVAF)' kelimesi açıkça geçmiyor.", sut_madde=sut, kanit=f"Tanı kodları: {', '.join(kodlar) if kodlar else 'Yok'}"))
    elif dvt_pe_var:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_DVT_OK", seviye="BILGI", baslik="3. Teşhis Kontrolü: DVT / Pulmoner Embolizm (PE) Tanısı Var", mesaj="Raporda Derin Ven Trombozu (DVT) veya Pulmoner Embolizm (PE) teşhisi mevcut.", sut_madde=sut, kanit="DVT / PE Endikasyonu"))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_TESHIS_YOK", seviye="HATA", baslik="3. Teşhis Kontrolü: NVAF veya DVT/PE Teşhisi Bulunamadı!", mesaj="Raporda Non-Valvuler Atriyal Fibrilasyon (NVAF) veya DVT/PE teşhisi tespit edilemedi!", sut_madde=sut, kanit="NVAF teşhisi yok"))

    # 4. Risk Faktörü Kontrolü
    risk_detaylari = []
    yas = getattr(rapor, "hasta_yasi", None)
    if any(x in metin for x in ("inme oykusu", "gecirilmis inme", "iskemik inme", "inme", "svo")):
        risk_detaylari.append("İnme öyküsü raporda belirtilmiş")
    if any(x in metin for x in ("gecici iskemik atak", "gia oykusu", "gia", "tia")):
        risk_detaylari.append("Geçici iskemik atak (GİA) öyküsü raporda belirtilmiş")
    if (yas is not None and yas >= 75) or any(x in metin for x in ("75 yas", "75 ve uzeri", ">= 75", ">=75", "yetmis bes yas")):
        risk_detaylari.append("Hasta rapor düzenlendiği zaman 75 yaş ve üstüymüş")
    if any(x in metin for x in ("nyha sinif 2", "nyha sinif ii", "nyha 2", "nyha ii", "sinif ii kalp", "sinif 2 kalp")):
        risk_detaylari.append("NYHA Sınıf 2 Kalp Yetmezliği raporda belirtilmiş")
    if any(x in metin for x in ("nyha sinif 3", "nyha sinif iii", "nyha 3", "nyha iii", "sinif iii kalp", "sinif 3 kalp")):
        risk_detaylari.append("NYHA Sınıf 3 Kalp Yetmezliği raporda belirtilmiş")
    if any(x in metin for x in ("nyha sinif 4", "nyha sinif iv", "nyha 4", "nyha iv", "sinif iv kalp", "sinif 4 kalp")):
        risk_detaylari.append("NYHA Sınıf 4 Kalp Yetmezliği raporda belirtilmiş")
    if not any("NYHA" in r for r in risk_detaylari) and any(x in metin for x in ("kalp yetmezligi", "kalp yetersizligi", "nyha")):
        risk_detaylari.append("Kalp Yetmezliği (NYHA >= II) raporda belirtilmiş")
    if any(x in metin for x in ("diabetes mellitus", "diyabet", "tip 2 dm", "tip-2 dm", "dm ")):
        risk_detaylari.append("Rapor açıklamasında Diabetes Mellitus (DM) belirtilmiş")
    if any(k.startswith(("E10", "E11", "E12", "E13", "E14")) for k in kodlar):
        risk_detaylari.append("Raporda altta Diabetes Mellitus (DM) Tanı Kodu da var")
    if any(x in metin for x in ("hipertansiyon", "esansiyel hipertansiyon", "ht ")):
        risk_detaylari.append("Rapor açıklamasında Hipertansiyon (HT) belirtilmiş")
    if any(k.startswith(("I10", "I11", "I12", "I13", "I15")) for k in kodlar):
        risk_detaylari.append("Raporda altta Hipertansiyon (HT) Tanı Kodu da var")

    if risk_detaylari:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_RISK_OK", seviye="BILGI", baslik="4. Risk Faktörü Kontrolü: UYGUN (En Az Bir Risk Faktörü Var)", mesaj="Tespit edilen durumlar: " + " | ".join(risk_detaylari), sut_madde=sut, kanit=risk_detaylari[0]))
    elif not dvt_pe_var:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_RISK_YOK", seviye="HATA", baslik="4. Risk Faktörü Kontrolü: HATA (Hastada Durumlardan Hiçbiri Yok!)", mesaj="Raporda/Hastada aranan risk faktörlerinden (İnme, GİA, >=75 yaş, NYHA 2-3-4, DM veya HT) HİÇBİRİ tespit edilemedi!", sut_madde=sut, kanit="Hastada durumlardan hiçbiri yok"))

    # 5. Varfarin / INR
    varfarin_var = any(w in metin for w in ("varfarin", "warfarin", "coumadin", "kumadin"))
    iki_ay_var = bool(re.search(r"\b(2|iki)\s*ay", metin))
    bes_olcum_uc_var = ("5" in metin or "bes" in metin) and ("3" in metin or "uc" in metin)
    inr_var = "inr" in metin
    svo_istisnasi = varfarin_var and any(x in metin for x in ("serebrovaskuler olay", "svo gecir", "inme gecir"))

    if (varfarin_var and iki_ay_var and bes_olcum_uc_var and inr_var) or svo_istisnasi:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_VARFARIN_OK", seviye="BILGI", baslik="5. Varfarin / INR Yanıtsızlık İbaresi: UYGUN", mesaj="Raporda 'En az 2 aylık varfarin tedavisi sonrası en az 1'er hafta arayla yapılan son 5 ölçümün en az 3'ünde INR değerinin 2-3 arasında tutulamadığı' yazılı.", sut_madde=sut, kanit="INR sonucuyla ilgili uygun ibare var"))
    else:
        eksikler = []
        if not varfarin_var:
            eksikler.append("Varfarin/Coumadin kullanımı")
        if not iki_ay_var:
            eksikler.append("En az 2 ay süre şartı")
        if not bes_olcum_uc_var:
            eksikler.append("Son 5 ölçümün en az 3'ünde şartı")
        if not inr_var:
            eksikler.append("INR 2-3 arasında tutulamama şartı")
        bulgular.append(Bulgu(kural_id=kural["id"] + "_VARFARIN_HATA", seviye="HATA", baslik="5. Varfarin / INR Yanıtsızlık İbaresi: EKSİK VEYA HATALI!", mesaj=f"Raporda zorunlu Varfarin/INR cümlesinde şu unsurlar eksik: {', '.join(eksikler)}.", sut_madde=sut, kanit=f"Eksik: {', '.join(eksikler)}"))

    # 6. Tedavi Şeması (mg)
    ilac_metinleri = " ".join(i.ad for i in rapor.ilaclar) + " " + (rapor.serbest_metin or "")
    mg_semasi_var = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(mg|miligram)\b", ilac_metinleri, re.IGNORECASE))
    if mg_semasi_var:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_MG_SEMA_OK", seviye="BILGI", baslik="6. Tedavi Şeması (mg) Kontrolü: UYGUN", mesaj="Raporda mg cinsinden tedavi şeması var.", sut_madde=sut, kanit="mg cinsinden tedavi şeması var"))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_MG_SEMA_YOK", seviye="UYARI", baslik="6. Tedavi Şeması (mg) Kontrolü: MG DEĞERİ TESPİT EDİLEMEDİ!", mesaj="Raporda ilacın mg türünden tedavi şeması (Örn: 1x20 mg, 2x5 mg) mutlaka yer almalıdır!", sut_madde=sut, kanit="Okunan metinde 'mg' ifadesi bulunamadı."))

    # 7. Kurul Bilgisi
    bulgular.append(Bulgu(kural_id=kural["id"] + "_KURUL_BILGI", seviye="BILGI", baslik="7. Rapor Türü / Max Süre / Hekim Branşı Kontrolü", mesaj="1 yıl süreli SAĞLIK KURULU RAPORU (en az birinin Kardiyoloji veya Nöroloji uzmanı olması koşuluyla 3 uzman hekim) veya 24 ay sonunda ilgili uzman hekim raporu olmalıdır.", sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}"))
    return bulgular


def calistir(rapor: Rapor, recete: Recete | None, ks: KuralSeti) -> Sonuc:
    havuz: list[Ilac] = list(rapor.ilaclar)
    if recete and ks.ayarlar.get("receteyi_de_degerlendir", True):
        havuz += list(recete.ilaclar)

    rapor_yok = recete is not None and not recete.rapor_var
    bulgular: list[Bulgu] = []

    if ks.kurallar and ks.kurallar[0].get("id", "").startswith("KAPSAM"):
        bulgular += _rapor_kodu_icd_uyum_kontrolu(rapor, recete)

    for kural in ks.kurallar:
        tip = kural.get("tip")

        if tip == "doksazosin_kontrolu":
            bulgular += _doksazosin_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "kapsam_kontrolu":
            bulgular += _kapsam_kurali(kural, rapor, recete)
            continue
        if tip == "tarih_kontrolu":
            bulgular += _tarih_kurali(kural, rapor, recete)
            continue
        if tip == "ayrik_urun_notu":
            bulgular += _ayrik_urun_kurali(kural, havuz)
            continue
        if tip == "raporsuz_recete_kontrolu":
            bulgular += _raporsuz_recete_kurali(kural, ks, recete)
            continue
        if tip == "tekil_sinif_kontrolu":
            bulgular += _tekil_sinif_kurali(kural, havuz)
            continue
        if tip == "cok_kaynakli_ibare_kontrolu":
            bulgular += _cok_kaynakli_ibare_kurali(kural, ks, rapor, recete, havuz)
            continue
        if tip == "aranan_ibare_kontrolu":
            if not rapor_yok:
                bulgular += _aranan_ibare_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "raporsuz_yasakli_urun":
            bulgular += _raporsuz_yasakli_urun_kurali(kural, recete)
            continue
        if tip == "tani_kodu_ibare_kontrolu":
            bulgular += _tani_kodu_ibare_kurali(kural, ks, rapor, recete, havuz)
            continue
        if tip == "brans_kontrolu":
            bulgular += _brans_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "yasakli_ibare_kontrolu":
            bulgular += _yasakli_ibare_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "osteoporoz_kontrolu":
            bulgular += _osteoporoz_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "rapor_suresi_kontrolu":
            bulgular += _rapor_suresi_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "rapor_yetki_sure_kontrolu":
            bulgular += _rapor_yetki_sure_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "etken_madde_birliktelik_kontrolu":
            bulgular += _etken_madde_birliktelik_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "rapor_kodu_bilgi_notu":
            bulgular += _rapor_kodu_bilgi_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "raporsuz_klopidogrel_kontrolu":
            bulgular += _raporsuz_klopidogrel_kurali(kural, recete)
            continue
        if tip == "aile_hekimi_rapor_uyarisi":
            bulgular += _aile_hekimi_rapor_uyarisi(kural, rapor, recete, havuz)
            continue
        if tip == "noak_kontrolu":
            bulgular += _noak_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "doz_siniri_kontrolu":
            bulgular += _doz_siniri_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "ldl_kontrolu":
            bulgular += _ldl_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "tani_kodu_kontrolu":
            bulgular += _tani_kodu_kurali(kural, rapor, recete, havuz)
            continue
        if rapor_yok and tip == "ibare_kontrolu":
            continue

        gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
        tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
        if not tetikleyen:
            continue

        etiket = ", ".join(tetikleyen)
        if tip == "ibare_kontrolu":
            bulgular.append(_ibare_kurali(kural, ks, rapor, etiket))
        elif tip in ("bilgi_notu", "birliktelik_uyarisi"):
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"],
                    seviye=kural.get("seviye", "BILGI"),
                    baslik=kural.get("baslik", "Bilgi Notu"),
                    mesaj=kural.get("mesaj", "").strip(),
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Tetikleyen ürün: {etiket}",
                )
            )

    sirali = {"HATA": 0, "UYARI": 1, "BILGI": 2}
    bulgular.sort(key=lambda b: sirali[b.seviye])
    return Sonuc(bulgular=bulgular, kural_seti_surumu=ks.surum)