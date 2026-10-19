"""Kural motoru."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
            kanit="Birlikte yazılan ürünler: " + ", ".join(urunler),
        )
    ]


_TIP2DM_DESENI = re.compile(r"tip\s*-?\s*2\s*(dm|diyabet)")


def _tani_kodu_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []
    onekler = tuple(k.upper() for k in kural.get("tani_onekleri", []))
    if not onekler:
        return []
    eslesen = [t for t in (rapor.tani_kodlari or []) if t.upper().startswith(onekler)]
    if not eslesen:
        return []
    etiket = ", ".join(tetikleyen)
    baslik = kural.get("baslik", "Tanı Kodu ve İbare Kontrolü")
    birlesik = normalize((rapor.serbest_metin or "") + " " + ((recete.aciklama if recete else "") or ""))
    if _TIP2DM_DESENI.search(birlesik):
        return [Bulgu(kural_id=kural["id"], seviye="BILGI", baslik=baslik, mesaj=kural.get("mesaj_var", "Gereken ifade mevcut.").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tanı kodu: {', '.join(eslesen)} · Tetikleyen ürün: {etiket}")]
    return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=baslik, mesaj=kural.get("mesaj_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tanı kodu: {', '.join(eslesen)} · Tetikleyen ürün: {etiket}")]


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
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
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
            return [Bulgu(kural_id=kural["id"], seviye="UYARI", baslik=baslik, mesaj="Raporsuz reçetede hekim branşı girilmemiş. " + kural.get("mesaj_brans_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {etiket}")]
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


def _tani_kodu_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    tetikleyen = [e for e, s in _gruplar(havuz, "urun") if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    beklenen = tuple(k.upper() for k in kural.get("zorunlu_kodlar", []))
    if not beklenen:
        return []
    rapordakiler = rapor.tani_kodlari or []
    if any(any(t.upper().startswith(b) for b in beklenen) for t in rapordakiler):
        return []
    return [Bulgu(kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=kural.get("baslik", "Tanı Kodu Eksik"), mesaj=kural.get("mesaj_yok", "").strip(), sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {', '.join(tetikleyen)} | Aranan: {', '.join(beklenen)}")]


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
    tetikleyen = [e for e, s in _gruplar(havuz, "urun") if _tetiklendi_mi(kural.get("tetikleyici", {}), s)]
    if not tetikleyen:
        return []
    etiket = ", ".join(tetikleyen)
    sut = kural.get("sut_madde", "SUT 4.2.15.D")

    if recete is not None and not recete.rapor_var:
        return [Bulgu(kural_id=kural["id"] + "_RAPORSUZ", seviye="HATA", baslik="NOAK Raporsuz Ödenmez!", mesaj="Yeni nesil oral antikoagülanlar (Eliquis, Xarelto, Pradaxa, Lixiana) raporsuz ödenmez. Sağlık Kurulu Raporu zorunludur.", sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}")]

    metin = normalize(rapor.serbest_metin or "")
    kodlar = [k.upper() for k in (rapor.tani_kodlari or [])]
    bulgular: list[Bulgu] = []

    varfarin_var = any(w in metin for w in ("varfarin", "warfarin", "coumadin", "kumadin"))
    iki_ay_var = bool(re.search(r"\b(2|iki)\s*ay", metin))
    bes_olcum_uc_var = ("5" in metin or "bes" in metin) and ("3" in metin or "uc" in metin)
    inr_var = "inr" in metin

    if varfarin_var and iki_ay_var and bes_olcum_uc_var and inr_var:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_VARFARIN_OK", seviye="BILGI", baslik="NOAK Zorunlu Varfarin / INR Şartı Tamam", mesaj="Raporda 'En az 2 ay varfarin kullanımı ve son 5 ölçümün en az 3'ünde INR değerinin 2-3 arasında tutulamadığı' zorunlu ibaresi eksiksiz tespit edildi.", sut_madde=sut, kanit=f"Tetikleyen: {etiket}"))
    elif varfarin_var or inr_var:
        eksikler = []
        if not iki_ay_var:
            eksikler.append("'en az 2 ay süreyle kullanım'")
        if not bes_olcum_uc_var:
            eksikler.append("'son 5 ölçümün en az 3'ünde'")
        if not inr_var:
            eksikler.append("'hedeflenen INR (2-3) değerinin tutulamaması'")
        bulgular.append(Bulgu(kural_id=kural["id"] + "_VARFARIN_EKSIK_DETAY", seviye="HATA", baslik="KESİNTİ RİSKİ: Varfarin / INR İbaresi Eksik Yazılmış!", mesaj=f"Raporda Varfarin/INR bahsi geçiyor ANCAK zorunlu SUT kalıbındaki şu unsurlar tespit edilemedi: {', '.join(eksikler)}. Sağlık kurulu raporunda 'En az 2 ay süre ile varfarin kullanılmasından sonra en az birer hafta ara ile yapılan son 5 ölçümün en az 3'ünde varfarin ile hedeflenen INR değerinin 2-3 arasında tutulamadığı' açıkça belirtilmelidir.", sut_madde=sut, kanit=f"Eksik unsurlar: {', '.join(eksikler)}"))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_VARFARIN_YOK", seviye="HATA", baslik="KESİNTİ RİSKİ: Zorunlu Varfarin (Coumadin) İbaresi Yok!", mesaj="NOAK'ların SGK tarafından ödenebilmesi için Sağlık Kurulu Raporunda: 'En az 2 ay süre ile varfarin kullanılmasından sonra en az birer hafta ara ile yapılan son 5 ölçümün en az 3'ünde varfarin ile hedeflenen INR değerinin 2-3 arasında tutulamadığı' ibaresinin yer alması ZORUNLUDUR.", sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}"))

    for kalip in ("mekanik protez", "mekanik kapak", "orta ciddi mitral darlik", "ciddi mitral darlik"):
        if kalip in metin:
            idx = metin.find(kalip)
            cevre = metin[max(0, idx - 25): idx + len(kalip) + 35]
            if not any(neg in cevre for neg in ("olmayan", "bulunmayan", "yok", "degil", "haric", "disinda")):
                bulgular.append(Bulgu(kural_id=kural["id"] + "_KAPAK_ENGELI", seviye="HATA", baslik="KESİNTİ RİSKİ: Mekanik Protez Kapak / Mitral Darlık!", mesaj="NOAK grubu ilaçlar yalnızca NONVALVULER Atriyal Fibrilasyonda ödenir. Orta-ciddi mitral darlığı veya mekanik protez kapağı olan hastalarda ÖDENMEZ!", sut_madde=sut, kanit="Raporda mekanik kapak / mitral darlık ifadesi tespit edildi."))
                break

    dvt_pe_var = any(k in metin for k in ("derin ven", "dvt", "pulmoner emboli", "pulmoner tromboemboli", "venoz tromboemboli", "vte")) or any(k.startswith(("I80", "I82", "I26")) for k in kodlar)
    nvaf_var = any(k in metin for k in ("atriyal fibrilasyon", "atrial fibrilasyon", "nvaf", "nonvalvuler", "non valvuler", "af ")) or any(k.startswith("I48") for k in kodlar)

    if nvaf_var:
        bulunan_riskler = []
        yas = getattr(rapor, "hasta_yasi", None)
        if (yas is not None and yas >= 75) or any(x in metin for x in ("75 yas", "75 ve uzeri", ">= 75", ">=75")):
            bulunan_riskler.append(">= 75 Yaş")
        if any(x in metin for x in ("inme", "gia", "gecici iskemik", "svo", "serebrovaskuler", "emboli oykusu")):
            bulunan_riskler.append("İnme / GİA Öyküsü")
        if any(x in metin for x in ("kalp yetmezligi", "kalp yetersizligi", "nyha", "ef <", "ef %", "kky")):
            bulunan_riskler.append("Kalp Yetmezliği (NYHA >= II)")
        if any(x in metin for x in ("diyabet", "diabetes", "dm", "seker hastaligi")) or any(k.startswith(("E10", "E11", "E12", "E13", "E14")) for k in kodlar):
            bulunan_riskler.append("Diyabet (DM)")
        if any(x in metin for x in ("hipertansiyon", "ht", "yuksek tansiyon")) or any(k.startswith(("I10", "I11", "I12", "I13", "I15")) for k in kodlar):
            bulunan_riskler.append("Hipertansiyon (HT)")

        if bulunan_riskler:
            bulgular.append(Bulgu(kural_id=kural["id"] + "_NVAF_RISK_OK", seviye="BILGI", baslik="NVAF Risk Faktörü ve Sağlık Kurulu Kontrolü", mesaj=f"NVAF endikasyonu için gerekli risk faktörü tespit edildi ({', '.join(bulunan_riskler)}). Raporun SAĞLIK KURULU RAPORU (Heyet) olduğunu teyit ediniz.", sut_madde=sut, kanit=f"Tespit edilen risk faktörleri: {', '.join(bulunan_riskler)}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"] + "_NVAF_RISK_YOK", seviye="HATA", baslik="KESİNTİ RİSKİ: NVAF Risk Faktörü Belirtilmemiş!", mesaj="Nonvalvuler AF (NVAF) raporlarında; 'İnme/GİA öyküsü', '>= 75 yaş', 'Kalp Yetmezliği (NYHA >= II)', 'Diyabet' veya 'Hipertansiyon' risk faktörlerinden EN AZ BİRİNİN belirtilmesi zorunludur!", sut_madde=sut, kanit="Raporda NVAF risk faktörü bulunamadı."))
    elif dvt_pe_var:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_DVT_PE_OK", seviye="BILGI", baslik="DVT / Pulmoner Embolizm Endikasyonu", mesaj="Raporda DVT / PE endikasyonu tespit edildi. Sağlık Kurulu Raporu olduğunu teyit ediniz.", sut_madde=sut, kanit=f"Tetikleyen: {etiket}"))
    else:
        bulgular.append(Bulgu(kural_id=kural["id"] + "_ENDIKASYON_YOK", seviye="UYARI", baslik="NOAK Endikasyonu (NVAF veya DVT/PE) Tespit Edilemedi", mesaj="NOAK'lar yalnızca Nonvalvuler AF veya DVT/PE endikasyonlarında ödenir. Rapor teşhisini kontrol ediniz.", sut_madde=sut, kanit=f"Tetikleyen: {etiket}"))

    bulgular.append(Bulgu(kural_id=kural["id"] + "_GECMIS_UYARI", seviye="BILGI", baslik="Medula İlaç Geçmişi: NOAK Değişim Kuralı Hatırlatması", mesaj="Medula ilaç geçmişinde farklı bir NOAK aktif görünüyorsa sistem yeni ilacı ödemez! Eski ilacın bitmiş olması veya hekim dilekçesi ile SGK'dan pasife alınması şarttır.", sut_madde=sut, kanit=f"Reçete/Rapor NOAK: {etiket}"))
    return bulgular


def calistir(rapor: Rapor, recete: Recete | None, ks: KuralSeti) -> Sonuc:
    havuz: list[Ilac] = list(rapor.ilaclar)
    if recete and ks.ayarlar.get("receteyi_de_degerlendir", True):
        havuz += list(recete.ilaclar)

    rapor_yok = recete is not None and not recete.rapor_var
    bulgular: list[Bulgu] = []

    for kural in ks.kurallar:
        tip = kural.get("tip")

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
            bulgular += _tani_kodu_ibare_kurali(kural, rapor, recete, havuz)
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
