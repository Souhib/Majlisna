"""Arabic-script forms of every Undercover and Codenames term.

Keyed by the exact Latin string stored in ``Word.word`` / ``CodenamesWord.word``.
Each value is ``(ar, ar_vocalized)``:

* ``ar`` — the term as it is normally written, without harakat. The rule is the
  bare noun as it would be printed on a card ("صبر", "حج", "توحيد"); the
  definite article only where the term is conventionally written with it:
  surah names ("الفاتحة", "البقرة"), the Book itself ("القرآن" — bare "قرآن" is
  the common noun "a recitation"), places and names that carry it ("المدينة",
  "الطائف", "الزبير", "اليسع"), dynasties ("العباسيون").
* ``ar_vocalized`` — the same with full or conventional harakat. The LAST word is
  in pausal form (no final case vowel). Every earlier word of a multi-word name
  (construct phrase, "ibn" chain, noun + adjective) carries its case vowel,
  because it is never in pause: "لَيْلَةُ الْقَدْر", "خَالِدُ بْنُ الْوَلِيد",
  "الْحَجَرُ الْأَسْوَد". Left bare, "لَيْلَة الْقَدْر" reads as a stop after
  "laylah". ``None`` wherever the vocalisation is not certain — a missing vowel
  is better than a wrong one on a prophet's or a place's name.

No honorifics inside the term ("محمد", not "محمد ﷺ"). A Latin term that is
spelled the same in two packs shares one row: "Ikhlas" is both the surah and the
virtue, written "الإخلاص" for both.

``tests/scripts/test_term_script_data.py`` fails if a seeded word has no entry
here, so adding a word to either game means adding its line below.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.schemas.term_script import TermScriptEntry

TERM_SCRIPTS: dict[str, tuple[str, str | None]] = {
    # --- Prophets & Messengers ---
    "Adam": ("آدم", "آدَم"),
    "Nuh": ("نوح", "نُوح"),
    "Ibrahim": ("إبراهيم", "إِبْرَاهِيم"),
    "Ismail": ("إسماعيل", "إِسْمَاعِيل"),
    "Ishaq": ("إسحاق", "إِسْحَاق"),
    "Yaqub": ("يعقوب", "يَعْقُوب"),
    "Yusuf": ("يوسف", "يُوسُف"),
    "Musa": ("موسى", "مُوسَى"),
    "Harun": ("هارون", "هَارُون"),
    "Dawud": ("داود", "دَاوُد"),
    "Sulayman": ("سليمان", "سُلَيْمَان"),
    "Isa": ("عيسى", "عِيسَى"),
    "Muhammad": ("محمد", "مُحَمَّد"),
    "Ayyub": ("أيوب", "أَيُّوب"),
    "Yunus": ("يونس", "يُونُس"),
    "Idris": ("إدريس", "إِدْرِيس"),
    "Hud": ("هود", "هُود"),
    "Salih": ("صالح", "صَالِح"),
    "Shuayb": ("شعيب", "شُعَيْب"),
    "Lut": ("لوط", "لُوط"),
    "Dhul-Kifl": ("ذو الكفل", "ذُو الْكِفْل"),
    "Ilyas": ("إلياس", "إِلْيَاس"),
    "Al-Yasa": ("اليسع", "الْيَسَع"),
    "Zakariya": ("زكريا", "زَكَرِيَّا"),
    "Yahya": ("يحيى", "يَحْيَى"),
    # --- Quran & Surahs ---
    # The name of the Book takes the article; bare قرآن is the common noun.
    "Quran": ("القرآن", "الْقُرْآن"),
    "Fatiha": ("الفاتحة", "الْفَاتِحَة"),
    "Baqarah": ("البقرة", "الْبَقَرَة"),
    # Muqatta'at letters: read letter by letter, not vocalised like a word.
    "Yasin": ("يس", None),
    "Taha": ("طه", None),
    "Mulk": ("الملك", "الْمُلْك"),
    "Kahf": ("الكهف", "الْكَهْف"),
    "Maryam": ("مريم", "مَرْيَم"),
    "Naba": ("النبأ", "النَّبَأ"),
    "Ikhlas": ("الإخلاص", "الْإِخْلَاص"),
    "Falaq": ("الفلق", "الْفَلَق"),
    "Nas": ("الناس", "النَّاس"),
    "Waqiah": ("الواقعة", "الْوَاقِعَة"),
    "Dukhan": ("الدخان", "الدُّخَان"),
    "Hadid": ("الحديد", "الْحَدِيد"),
    "Furqan": ("الفرقان", "الْفُرْقَان"),
    "Nur": ("النور", "النُّور"),
    "Ayah": ("آية", "آيَة"),
    "Juz": ("جزء", "جُزْء"),
    "Hizb": ("حزب", "حِزْب"),
    "Tanzil": ("تنزيل", "تَنْزِيل"),
    "Tafsir": ("تفسير", "تَفْسِير"),
    "Tajweed": ("تجويد", "تَجْوِيد"),
    "Tilawah": ("تلاوة", "تِلَاوَة"),
    "Mushaf": ("مصحف", "مُصْحَف"),
    # --- Islamic History ---
    "Hijrah": ("هجرة", "هِجْرَة"),
    "Badr": ("بدر", "بَدْر"),
    "Uhud": ("أحد", "أُحُد"),
    "Khandaq": ("الخندق", "الْخَنْدَق"),
    "Hudaybiyyah": ("الحديبية", "الْحُدَيْبِيَة"),
    "Mecca": ("مكة", "مَكَّة"),
    "Medina": ("المدينة", "الْمَدِينَة"),
    "Abyssinia": ("الحبشة", "الْحَبَشَة"),
    "Taif": ("الطائف", "الطَّائِف"),
    "Tabuk": ("تبوك", "تَبُوك"),
    "Khaybar": ("خيبر", "خَيْبَر"),
    "Caliphate": ("خلافة", "خِلَافَة"),
    "Umayyad": ("الأمويون", "الْأُمَوِيُّون"),
    "Abbasid": ("العباسيون", "الْعَبَّاسِيُّون"),
    "Ottoman": ("العثمانيون", "الْعُثْمَانِيُّون"),
    "Fatimid": ("الفاطميون", "الْفَاطِمِيُّون"),
    "Seljuk": ("السلاجقة", "السَّلَاجِقَة"),
    "Andalusia": ("الأندلس", "الْأَنْدَلُس"),
    "Baghdad": ("بغداد", "بَغْدَاد"),
    "Damascus": ("دمشق", "دِمَشْق"),
    "Cordoba": ("قرطبة", "قُرْطُبَة"),
    "Jerusalem": ("القدس", "الْقُدْس"),
    "Hattin": ("حطين", None),
    "Ain Jalut": ("عين جالوت", "عَيْنُ جَالُوت"),
    "Timbuktu": ("تمبكتو", None),
    # --- Pillars, Worship & Rituals ---
    "Shahada": ("شهادة", "شَهَادَة"),
    "Salah": ("صلاة", "صَلَاة"),
    "Zakat": ("زكاة", "زَكَاة"),
    "Sawm": ("صوم", "صَوْم"),
    "Hajj": ("حج", "حَجّ"),
    "Umrah": ("عمرة", "عُمْرَة"),
    "Sadaqah": ("صدقة", "صَدَقَة"),
    "Wudu": ("وضوء", "وُضُوء"),
    "Tayammum": ("تيمم", "تَيَمُّم"),
    "Adhan": ("أذان", "أَذَان"),
    "Iqamah": ("إقامة", "إِقَامَة"),
    "Qiyam": ("قيام", "قِيَام"),
    "Sujud": ("سجود", "سُجُود"),
    "Ruku": ("ركوع", "رُكُوع"),
    "Tashahhud": ("تشهد", "تَشَهُّد"),
    "Tasleem": ("تسليم", "تَسْلِيم"),
    "Takbir": ("تكبير", "تَكْبِير"),
    "Tahmid": ("تحميد", "تَحْمِيد"),
    "Tasbih": ("تسبيح", "تَسْبِيح"),
    "Istighfar": ("استغفار", "اِسْتِغْفَار"),
    "Dhikr": ("ذكر", "ذِكْر"),
    "Dua": ("دعاء", "دُعَاء"),
    "Tawaf": ("طواف", "طَوَاف"),
    "Sai": ("سعي", "سَعْي"),
    "Ihram": ("إحرام", "إِحْرَام"),
    "Itikaf": ("اعتكاف", "اِعْتِكَاف"),
    "Janazah": ("جنازة", "جَنَازَة"),
    "Jummah": ("جمعة", "جُمُعَة"),
    "Khutbah": ("خطبة", "خُطْبَة"),
    "Taraweeh": ("تراويح", "تَرَاوِيح"),
    "Tahajjud": ("تهجد", "تَهَجُّد"),
    "Iftar": ("إفطار", "إِفْطَار"),
    # The pre-dawn meal is سَحور; سُحور is the act of eating it.
    "Suhoor": ("سحور", "سَحُور"),
    "Laylat al-Qadr": ("ليلة القدر", "لَيْلَةُ الْقَدْر"),
    "Eid al-Fitr": ("عيد الفطر", "عِيدُ الْفِطْر"),
    "Eid al-Adha": ("عيد الأضحى", "عِيدُ الْأَضْحَى"),
    # Qurbani is the Urdu/Persian name; the Arabic word for the Eid sacrifice is أضحية.
    "Qurbani": ("أضحية", "أُضْحِيَّة"),
    "Aqiqah": ("عقيقة", "عَقِيقَة"),
    "Isra": ("إسراء", "إِسْرَاء"),
    "Miraj": ("معراج", "مِعْرَاج"),
    "Mawlid": ("مولد", "مَوْلِد"),
    # --- Faith, Values & Concepts ---
    "Tawhid": ("توحيد", "تَوْحِيد"),
    "Iman": ("إيمان", "إِيمَان"),
    "Ihsan": ("إحسان", "إِحْسَان"),
    "Taqwa": ("تقوى", "تَقْوَى"),
    "Tawakkul": ("توكل", "تَوَكُّل"),
    "Sabr": ("صبر", "صَبْر"),
    "Shukr": ("شكر", "شُكْر"),
    "Tawbah": ("توبة", "تَوْبَة"),
    "Adl": ("عدل", "عَدْل"),
    "Rahma": ("رحمة", "رَحْمَة"),
    "Hikmah": ("حكمة", "حِكْمَة"),
    "Ilm": ("علم", "عِلْم"),
    "Amanah": ("أمانة", "أَمَانَة"),
    "Sidq": ("صدق", "صِدْق"),
    "Haya": ("حياء", "حَيَاء"),
    "Birr": ("بر", "بِرّ"),
    "Husn": ("حسن", "حُسْن"),
    "Khushu": ("خشوع", "خُشُوع"),
    "Wara": ("ورع", "وَرَع"),
    "Zuhd": ("زهد", "زُهْد"),
    "Ukhuwwah": ("أخوة", "أُخُوَّة"),
    "Iffah": ("عفة", "عِفَّة"),
    "Hilm": ("حلم", "حِلْم"),
    "Shura": ("شورى", "شُورَى"),
    "Rifq": ("رفق", "رِفْق"),
    "Jihad": ("جهاد", "جِهَاد"),
    "Barakah": ("بركة", "بَرَكَة"),
    "Fitrah": ("فطرة", "فِطْرَة"),
    "Nafs": ("نفس", "نَفْس"),
    "Ruh": ("روح", "رُوح"),
    # Divine decree is قَدَر; "Laylat al-Qadr" above is قَدْر.
    "Qadr": ("قدر", "قَدَر"),
    "Rizq": ("رزق", "رِزْق"),
    "Hidayah": ("هداية", "هِدَايَة"),
    "Niyyah": ("نية", "نِيَّة"),
    "Halal": ("حلال", "حَلَال"),
    "Haram": ("حرام", "حَرَام"),
    # --- Islamic Sciences ---
    "Hadith": ("حديث", "حَدِيث"),
    "Sunnah": ("سنة", "سُنَّة"),
    "Fiqh": ("فقه", "فِقْه"),
    "Aqeedah": ("عقيدة", "عَقِيدَة"),
    "Usul": ("أصول", "أُصُول"),
    "Seerah": ("سيرة", "سِيرَة"),
    "Nahw": ("نحو", "نَحْو"),
    "Sarf": ("صرف", "صَرْف"),
    "Balagha": ("بلاغة", "بَلَاغَة"),
    "Mantiq": ("منطق", "مَنْطِق"),
    "Falsafa": ("فلسفة", "فَلْسَفَة"),
    "Kalam": ("كلام", "كَلَام"),
    "Tasawwuf": ("تصوف", "تَصَوُّف"),
    "Ijtihad": ("اجتهاد", "اِجْتِهَاد"),
    "Ijma": ("إجماع", "إِجْمَاع"),
    "Qiyas": ("قياس", "قِيَاس"),
    "Isnad": ("إسناد", "إِسْنَاد"),
    "Matn": ("متن", "مَتْن"),
    "Jarh": ("جرح", "جَرْح"),
    "Maqasid": ("مقاصد", "مَقَاصِد"),
    "Ilm al-Rijal": ("علم الرجال", "عِلْمُ الرِّجَال"),
    # --- Companions & Figures ---
    "Abu Bakr": ("أبو بكر", "أَبُو بَكْر"),
    "Umar": ("عمر", "عُمَر"),
    "Uthman": ("عثمان", "عُثْمَان"),
    "Ali": ("علي", "عَلِيّ"),
    "Bilal": ("بلال", "بِلَال"),
    "Khalid": ("خالد", "خَالِد"),
    "Khalid ibn al-Walid": ("خالد بن الوليد", "خَالِدُ بْنُ الْوَلِيد"),
    "Khadijah": ("خديجة", "خَدِيجَة"),
    "Aisha": ("عائشة", "عَائِشَة"),
    "Fatimah": ("فاطمة", "فَاطِمَة"),
    "Hafsa": ("حفصة", "حَفْصَة"),
    "Hamza": ("حمزة", "حَمْزَة"),
    "Salman": ("سلمان", "سَلْمَان"),
    "Abu Hurairah": ("أبو هريرة", "أَبُو هُرَيْرَة"),
    "Zubayr": ("الزبير", "الزُّبَيْر"),
    "Talha": ("طلحة", "طَلْحَة"),
    "Saad": ("سعد", "سَعْد"),
    "Umar ibn Abdul Aziz": ("عمر بن عبد العزيز", "عُمَرُ بْنُ عَبْدِ الْعَزِيز"),
    "Tariq ibn Ziyad": ("طارق بن زياد", "طَارِقُ بْنُ زِيَاد"),
    "Saladin": ("صلاح الدين", "صَلَاحُ الدِّين"),
    "Ibn Battuta": ("ابن بطوطة", "ابْنُ بَطُّوطَة"),
    # --- Daily Life & Culture ---
    "Hijab": ("حجاب", "حِجَاب"),
    "Niqab": ("نقاب", "نِقَاب"),
    "Thobe": ("ثوب", "ثَوْب"),
    # The kufi cap is a طاقية; "كوفية" is the keffiyeh headscarf, another garment.
    "Kufi": ("طاقية", "طَاقِيَّة"),
    "Miswak": ("مسواك", "مِسْوَاك"),
    "Attar": ("عطر", "عِطْر"),
    "Dates": ("تمر", "تَمْر"),
    "Zamzam": ("زمزم", "زَمْزَم"),
    "Oud": ("عود", "عُود"),
    "Henna": ("حناء", "حِنَّاء"),
    # Phrases keep their case endings: they are read as a sentence, not a noun.
    "Waqf": ("وقف", "وَقْف"),
    "Nikah": ("نكاح", "نِكَاح"),
    # --- Sacred Places & Architecture ---
    "Kaaba": ("الكعبة", "الْكَعْبَة"),
    "Al-Aqsa": ("الأقصى", "الْأَقْصَى"),
    "Dome of the Rock": ("قبة الصخرة", "قُبَّةُ الصَّخْرَة"),
    "Black Stone": ("الحجر الأسود", "الْحَجَرُ الْأَسْوَد"),
    "Arafat": ("عرفات", "عَرَفَات"),
    "Muzdalifah": ("مزدلفة", "مُزْدَلِفَة"),
    "Mina": ("منى", "مِنَى"),
    "Safa": ("الصفا", "الصَّفَا"),
    "Marwa": ("المروة", "الْمَرْوَة"),
    "Quba": ("قباء", "قُبَاء"),
    "Hira": ("حراء", "حِرَاء"),
    "Thawr": ("ثور", "ثَوْر"),
    "Jabal Nur": ("جبل النور", "جَبَلُ النُّور"),
    "Masjid": ("مسجد", "مَسْجِد"),
    "Mihrab": ("محراب", "مِحْرَاب"),
    "Minbar": ("منبر", "مِنْبَر"),
    "Minaret": ("مئذنة", "مِئْذَنَة"),
}


def term_script_entries() -> list[TermScriptEntry]:
    """The seed data as typed upsert entries."""
    return [TermScriptEntry(term=term, ar=ar, ar_vocalized=vocalized) for term, (ar, vocalized) in TERM_SCRIPTS.items()]


async def seed_term_scripts(session: AsyncSession) -> None:
    """Upsert the Arabic forms of every game term.

    Idempotent and safe on production: inserts missing terms, rewrites changed
    ones, touches nothing else. Correcting a spelling here and re-running
    ``--seed`` is how a fix reaches the server.
    """
    result = await TermScriptController(session).upsert(term_script_entries())
    print(
        f"  Term scripts: {result.inserted} inserted, {result.updated} updated, "
        f"{result.unchanged} unchanged ({len(TERM_SCRIPTS)} total)"
    )
