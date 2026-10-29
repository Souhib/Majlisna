"""Rules every game's content keeps, checked on the seed data that --seed upserts to production.

- No Kalimat hint names its own word: a player could type the answer straight from the rung.
- Western digits only (house rule): no Eastern Arabic digit anywhere in seed_data.
- No weak hadith: known da'if or fabricated sayings must not come back, in any language.
- Every MCQ question has four distinct choices in each language and a valid answer index.

Each finder takes its data as an argument, so it can be pointed at an older copy of a file
(``git show HEAD:<file>`` into a temp path) to show that the test catches what it claims to.
"""

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from majlisna.api.utils.text_match import (
    fold_arabic_letters,
    fold_arabic_spellings,
    normalize_answer,
    strip_arabic_article,
    strip_article,
)
from scripts.seed_data import codenames_data, mcqquiz_data, term_script_data, undercover_data, wordquiz_data

SEED_DATA_DIR = Path(wordquiz_data.__file__).resolve().parent
LOCALES_DIR = Path(__file__).resolve().parents[3] / "front" / "src" / "i18n" / "locales"
SEED_MODULES = (wordquiz_data, mcqquiz_data, codenames_data, undercover_data, term_script_data)

_WORD = re.compile(r"\w+")
_EASTERN_ARABIC_DIGIT = re.compile("[٠-٩۰-۹]")
# One-letter conjunctions and prepositions written joined to the next word: "فصبر", "بالصبر".
_ARABIC_PROCLITICS = ("و", "ف", "ب", "ل", "ك")
_ARABIC_LAM_ARTICLE = "لل"  # "للصلاة": lam + article
_MIN_STEM_LENGTH = 3

MCQ_CHOICE_KEYS = ("0", "1", "2", "3")
LANGUAGES = ("en", "ar", "fr")

# Da'if, mawdu' or baseless sayings and stories taken out of the content (graded on dorar.net,
# sunnah.com, islamqa.info or islamweb.net). One distinctive phrase per wording, so a legitimate
# text never matches; add the phrase here whenever such a report is removed.
WEAK_HADITH_PHRASES = (
    # "الدعاء مخ العبادة" (Tirmidhi 3371, da'if)
    "مخ العبادة",
    "essence of worship",
    "brain of worship",
    "essence de l'adoration",
    # "الدعاء سلاح المؤمن" (mawdu', al-Da'ifa 179)
    "سلاح المؤمن",
    "weapon of the believer",
    "arme du croyant",
    # "أدبني ربي فأحسن تأديبي" (no sound chain)
    "أدبني ربي فأحسن تأديبي",
    "my lord taught me my adab",
    "mon seigneur m'a enseigné",
    # Yasin, "the heart of the Qur'an" (Tirmidhi 2887, mawdu'), and recited over the dead (da'if)
    "قلب القرآن",
    "heart of the quran",
    "cœur du coran",
    "تقرأ غالبا على الميت",
    "recited for the deceased",
    "récitée pour les défunts",
    # Ar-Rahman, "the bride of the Qur'an" (munkar, al-Da'ifa 1350)
    "عروس القرآن",
    "bride of the quran",
    "arus al quran",
    "mariée du coran",
    # Al-Waqi'ah against poverty (da'if, Da'if al-Jami' 5773)
    "لم تصبه فاقة",
    "كل ليلة للرزق",
    "protection from poverty",
    "nightly for rizq",
    "chaque nuit pour le rizq",
    # Al-An'am escorted by 70,000 angels (da'if)
    "يشيعها سبعون ألف ملك",
    "accompanied by 70,000 angels",
    "70 000 anges",
    # The hafiz interceding for ten relatives, his parents crowned with light (da'if)
    "يشفع لعشرة",
    "intercede for ten",
    "intercédera pour dix",
    "يتوج والداه بنور",
    "يتوجان بنور",
    "crowned with light",
    "couronnés de lumière",
    # "أنا مدينة العلم وعلي بابها" (mawdu', al-Da'ifa 2955)
    "أنا مدينة العلم",
    "بباب مدينة العلم",
    "باب العلم",
    "city of knowledge",
    "gate of knowledge",
    "bab al ilm",
    "cité du savoir",
    "porte du savoir",
    # "سلمان منا أهل البيت" (da'if jiddan)
    "سلمان منا أهل البيت",
    "he is from ahl al bayt",
    # "Paradise longs for Ali, Ammar and Salman" (Tirmidhi 3797, da'if)
    "الجنة تشتاق",
    "paradise longs for",
    "le paradis l'aspire",
    # Prayer in al-Aqsa worth 500 (da'if)
    "تعادل 500 صلاة",
    "بخمسمائة صلاة",
    "500 times more",
    "500 fois plus",
    # The spider and the dove at Thawr (al-Da'ifa 1129)
    "نسج عنكبوت",
    "عششت حمامة",
    "وضعت حمامة بيضها",
    "spider spun a web",
    "spider wove a web",
    "dove laid eggs",
    "dove nested",
    "une araignée tissa",
    "une araignée et une colombe",
    "colombe pondit",
    # Shu'ayb, "the orator of the prophets" (no sound chain)
    "خطيب الأنبياء",
    "orator of the prophets",
    "orateur des prophètes",
    # Idris, "the first to write with the pen" (Abu Dharr's long hadith, very weak)
    "أول من خط بالقلم",
    "أول من كتب بالقلم",
    "first to write with a pen",
    "premier à écrire avec",
    # Adam as "Safiyyullah" (Tirmidhi 3616, da'if)
    "safiyyullah",
    # "الجنة تحت أقدام الأمهات" (mawdu'; the sound wording is Nasa'i 3104, "تحت رجليها")
    "الجنة تحت أقدام الأمهات",
    "feet of mothers",
    "pieds des mères",
    # "اذهبوا فأنتم الطلقاء" (no established chain)
    "فأنتم الطلقاء",
    "you are all free",
    "vous êtes tous libres",
    # "فلنعم الأمير أميرها" (Ahmad 18957, da'if)
    "فلنعم الأمير أميرها",
    "how excellent is the commander",
    # "من آذى ذميًا فقد آذاني" (da'if)
    "من آذى ذميًا",
    "whoever harms a dhimmi",
    "whoever harms one has harmed me",
    "qui nuit à l'un d'eux m'a nui",
    # "أدبوا أولادكم على ثلاث خصال" (da'if)
    "أدبوا أولادكم",
    "teach your children three things",
    "enseignez à vos enfants trois",
    # Abyssinia, "a land of justice" (Ibn Ishaq, mu'dal)
    "إنها أرض عدل",
    "a land of justice",
    "une terre de justice",
)


class HintLeak(NamedTuple):
    word: str
    rung: str
    lang: str
    answer: str
    hint: str


class WeakHadithHit(NamedTuple):
    location: str
    phrase: str
    text: str


def canonical(text: str) -> str:
    """The Word Quiz comparison form: no diacritics or accents, lowercase, Arabic letters folded."""
    return fold_arabic_spellings(fold_arabic_letters(normalize_answer(text)))


def phrase_key(text: str) -> str:
    """Whole words of ``text``, space-padded, so ``in`` only ever matches whole words."""
    return " " + " ".join(_WORD.findall(fold_arabic_letters(normalize_answer(text)))) + " "


def hint_word_forms(word: str) -> set[str]:
    """What a hint word can be read as: itself, without the article, without a joined proclitic."""
    forms = {word, strip_arabic_article(word)}
    if word.startswith(_ARABIC_LAM_ARTICLE) and len(word) > len(_ARABIC_LAM_ARTICLE) + 1:
        forms.add(word[len(_ARABIC_LAM_ARTICLE) :])
    if word.startswith(_ARABIC_PROCLITICS) and len(word) > _MIN_STEM_LENGTH:
        forms.update({word[1:], strip_arabic_article(word[1:])})
    return forms


def answer_word_sequences(word: Mapping) -> set[tuple[str, ...]]:
    """Every answer the Word Quiz accepts for ``word``, as word sequences (with and without "al")."""
    answers = [word.get("word_en"), word.get("word_ar"), word.get("word_fr")]
    for lang_answers in word.get("accepted_answers", {}).values():
        answers.extend(lang_answers)
    sequences = set()
    for answer in filter(None, answers):
        for part in (answer, *answer.split("/")):
            for form in {canonical(part), strip_article(canonical(part))}:
                words = tuple(strip_arabic_article(w) for w in _WORD.findall(form))
                if words:
                    sequences.add(words)
    return sequences


def contains_sequence(hint_words: list[set[str]], answer: tuple[str, ...]) -> bool:
    size = len(answer)
    return any(all(answer[j] in hint_words[i + j] for j in range(size)) for i in range(len(hint_words) - size + 1))


def find_hint_leaks(words: Iterable[Mapping]) -> list[HintLeak]:
    leaks = []
    for word in words:
        answers = answer_word_sequences(word)
        for rung, hint in word["hints"].items():
            for lang, text in hint.items():
                hint_words = [hint_word_forms(w) for w in _WORD.findall(canonical(text))]
                found = next((a for a in sorted(answers) if contains_sequence(hint_words, a)), None)
                if found:
                    leaks.append(HintLeak(word["word_en"], rung, lang, " ".join(found), text))
    return leaks


def find_eastern_digits(paths: Iterable[Path]) -> list[str]:
    hits = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _EASTERN_ARABIC_DIGIT.search(line):
                hits.append(f"{path.name}:{number}: {line.strip()[:100]}")
    return hits


def iter_strings(value: object, location: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from iter_strings(item, f"{location}.{key}")
    elif isinstance(value, list | tuple | set | frozenset):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{location}[{index}]")


def module_strings(modules: Iterable[ModuleType]) -> Iterator[tuple[str, str]]:
    """Every string a seed module holds in its public data (dicts, lists, constants)."""
    for module in modules:
        stem = module.__name__.rsplit(".", 1)[-1]
        for name, value in vars(module).items():
            if not name.startswith("_") and isinstance(value, str | list | tuple | set | frozenset | dict):
                yield from iter_strings(value, f"{stem}.{name}")


def locale_strings(paths: Iterable[Path]) -> Iterator[tuple[str, str]]:
    for path in paths:
        yield from iter_strings(json.loads(path.read_text(encoding="utf-8")), path.name)


def find_weak_hadith(strings: Iterable[tuple[str, str]]) -> list[WeakHadithHit]:
    keys = {phrase: phrase_key(phrase) for phrase in WEAK_HADITH_PHRASES}
    hits = []
    for location, text in strings:
        text_key = phrase_key(text)
        hits.extend(WeakHadithHit(location, phrase, text) for phrase, key in keys.items() if key in text_key)
    return hits


def mcq_question_errors(index: int, question: Mapping) -> list[str]:
    choices = question.get("choices", {})
    errors = []
    if tuple(sorted(choices)) != MCQ_CHOICE_KEYS:
        errors.append(f"#{index}: choices {sorted(choices)}, expected {list(MCQ_CHOICE_KEYS)}")
    for lang in LANGUAGES:
        texts = [str((choices.get(key) or {}).get(lang) or "").strip() for key in MCQ_CHOICE_KEYS]
        if not all(texts):
            errors.append(f"#{index}: a choice has no {lang} text")
        elif len(set(texts)) != len(texts):
            errors.append(f"#{index}: two {lang} choices are the same: {texts}")
    answer = question.get("correct_answer_index")
    if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(MCQ_CHOICE_KEYS):
        errors.append(f"#{index}: correct_answer_index {answer!r}")
    return errors


def find_mcq_structure_errors(questions: Iterable[Mapping]) -> list[str]:
    return [error for index, question in enumerate(questions) for error in mcq_question_errors(index, question)]


def test_no_kalimat_hint_names_its_own_word():
    # Prepare
    words = wordquiz_data.QUIZ_WORDS

    # Act
    leaks = find_hint_leaks(words)

    # Assert
    assert leaks == [], "\n".join(
        f"{leak.word} — hint {leak.rung} [{leak.lang}] contains '{leak.answer}': {leak.hint}" for leak in leaks
    )


def test_seed_data_uses_western_digits_only():
    # Prepare
    paths = sorted(SEED_DATA_DIR.glob("*.py"))

    # Act
    hits = find_eastern_digits(paths)

    # Assert
    assert paths
    assert hits == [], "Eastern Arabic digits (house rule: 0-9):\n" + "\n".join(hits)


def test_no_known_weak_hadith_in_seed_data_or_locales():
    # Prepare
    locale_paths = sorted(LOCALES_DIR.glob("*.json"))
    strings = [*module_strings(SEED_MODULES), *locale_strings(locale_paths)]

    # Act
    hits = find_weak_hadith(strings)

    # Assert
    assert locale_paths, f"no locale found in {LOCALES_DIR}"
    assert hits == [], "\n".join(f"{hit.location}: '{hit.phrase}' in {hit.text[:120]!r}" for hit in hits)


def test_every_mcq_question_has_four_distinct_choices_and_a_valid_answer():
    # Prepare
    questions = mcqquiz_data.MCQ_QUESTIONS

    # Act
    errors = find_mcq_structure_errors(questions)

    # Assert
    assert questions
    assert errors == [], "\n".join(errors)
