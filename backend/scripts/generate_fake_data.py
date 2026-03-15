#!/usr/bin/env python3
"""Script to generate fake data for IPG platform testing.

This script can be used to:
1. Create database tables and generate fake users, rooms, games, and seed data
2. Delete all data from the database (drop and recreate tables)
3. Seed Undercover word pairs (30+ Islamic term pairs)
4. Seed Codenames word packs (100+ Islamic terms in categories)
5. Seed achievement/challenge definitions
6. Create UserStats, UserAchievements, UserChallenges for test users
7. Create friendships and chat messages

Usage:
    # Create database tables and generate fake data
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c

    # Delete all data from the database
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -d

    # Seed game content only (safe for production)
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --seed
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -s

    # Custom data volumes
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c --users 50 --games 100

Options:
    --delete, -d         Delete all data by dropping and recreating tables
    --create-db, -c      Create tables and generate fake data
    --seed, -s           Seed game content only (safe for production)
    --users N            Number of additional random users to generate (default: 15)
    --games N            Number of games to generate (default: 30)

Note:
    You must use exactly ONE of: --delete or --create-db.
    These flags are mutually exclusive.
"""

import argparse
import asyncio
import random
import string
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.challenge import ChallengeController
from ipg.api.controllers.shared import get_password_hash
from ipg.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from ipg.api.models.chat import ChatMessage
from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack
from ipg.api.models.friendship import Friendship, FriendshipStatus
from ipg.api.models.game import GameType
from ipg.api.models.room import RoomStatus, RoomType
from ipg.api.models.stats import AchievementDefinition, UserAchievement, UserStats
from ipg.api.models.table import Game, Room, User
from ipg.api.models.undercover import TermPair, Word
from ipg.api.models.wordquiz import QuizWord
from ipg.database import create_app_engine, create_db_and_tables
from scripts.mcq_questions_data import seed_mcq_questions
from ipg.settings import Settings

# Lazy imports for dev-only dependencies (not in production image)
fake = None  # type: ignore[assignment]


# ── Test user accounts ──────────────────────────────────────────────────────

TEST_USERS = [
    {
        "username": "admin",
        "email_address": "admin@test.com",
        "password": "admin123",
        "country": "SAU",
        "bio": "Platform admin. Love organizing game nights!",
    },
    {
        "username": "user",
        "email_address": "user@test.com",
        "password": "user1234",
        "country": "ARE",
        "bio": "Casual player, always up for a round.",
    },
    {
        "username": "player",
        "email_address": "player@test.com",
        "password": "player123",
        "country": "MAR",
    },
    {
        "username": "ali",
        "email_address": "ali@test.com",
        "password": "ali12345",
        "country": "EGY",
        "bio": "Undercover champion. Try to catch me!",
    },
    {
        "username": "fatima",
        "email_address": "fatima@test.com",
        "password": "fatima12",
        "country": "TUN",
        "bio": "Spymaster extraordinaire.",
    },
    {
        "username": "omar",
        "email_address": "omar@test.com",
        "password": "omar1234",
        "country": "DZA",
    },
    {
        "username": "aisha",
        "email_address": "aisha@test.com",
        "password": "aisha123",
        "country": "JOR",
        "bio": "Here for the fun and the community.",
    },
    {
        "username": "yusuf",
        "email_address": "yusuf@test.com",
        "password": "yusuf123",
        "country": "TUR",
    },
    {
        "username": "maryam",
        "email_address": "maryam@test.com",
        "password": "maryam12",
        "country": "MYS",
        "bio": "Codenames is my favourite!",
    },
    {
        "username": "hamza",
        "email_address": "hamza@test.com",
        "password": "hamza123",
        "country": "PAK",
    },
    # Pool B accounts (for parallel E2E test execution)
    {
        "username": "user_b",
        "email_address": "user_b@test.com",
        "password": "user1234",
        "country": "ARE",
    },
    {
        "username": "player_b",
        "email_address": "player_b@test.com",
        "password": "player123",
        "country": "MAR",
    },
    {
        "username": "ali_b",
        "email_address": "ali_b@test.com",
        "password": "ali12345",
        "country": "EGY",
    },
    {
        "username": "fatima_b",
        "email_address": "fatima_b@test.com",
        "password": "fatima12",
        "country": "TUN",
    },
    {
        "username": "omar_b",
        "email_address": "omar_b@test.com",
        "password": "omar1234",
        "country": "DZA",
    },
    {
        "username": "aisha_b",
        "email_address": "aisha_b@test.com",
        "password": "aisha123",
        "country": "JOR",
    },
]


# ── Undercover word pairs (30+ Islamic term pairs) ──────────────────────────

UNDERCOVER_WORDS = [
    # Pillars of Islam
    {
        "word": "Hajj",
        "category": "Pillars of Islam",
        "short_description": "Pilgrimage to Mecca",
        "long_description": "The fifth pillar of Islam requiring able Muslims to make a pilgrimage to Mecca at least once.",
        "hint": {
            "en": "The annual pilgrimage to Mecca, one of the five pillars of Islam",
            "ar": "الحج السنوي إلى مكة، أحد أركان الإسلام الخمسة",
            "fr": "Le pèlerinage annuel à La Mecque, l'un des cinq piliers de l'islam",
        },
    },
    {
        "word": "Umrah",
        "category": "Islamic Rituals",
        "short_description": "Minor pilgrimage to Mecca",
        "long_description": "A voluntary pilgrimage to Mecca that can be performed at any time of the year.",
        "hint": {
            "en": "The minor pilgrimage to Mecca, can be performed at any time of year",
            "ar": "العمرة، الحج الأصغر إلى مكة، يمكن أداؤها في أي وقت من السنة",
            "fr": "Le petit pèlerinage à La Mecque, peut être accompli à tout moment de l'année",
        },
    },
    {
        "word": "Salah",
        "category": "Pillars of Islam",
        "short_description": "Islamic ritual prayer",
        "long_description": "The second pillar of Islam consisting of five daily prayers obligatory for all adult Muslims.",
        "hint": {
            "en": "The five daily prayers, the second pillar of Islam",
            "ar": "الصلوات الخمس اليومية، الركن الثاني من أركان الإسلام",
            "fr": "Les cinq prières quotidiennes, le deuxième pilier de l'islam",
        },
    },
    {
        "word": "Sawm",
        "category": "Pillars of Islam",
        "short_description": "Fasting during Ramadan",
        "long_description": "The fourth pillar of Islam observed during Ramadan where Muslims fast from dawn until sunset.",
        "hint": {
            "en": "Fasting from dawn to sunset during Ramadan, the fourth pillar of Islam",
            "ar": "الصيام من الفجر حتى غروب الشمس خلال رمضان، الركن الرابع من أركان الإسلام",
            "fr": "Le jeûne de l'aube au coucher du soleil pendant le Ramadan, le quatrième pilier de l'islam",
        },
    },
    {
        "word": "Zakat",
        "category": "Pillars of Islam",
        "short_description": "Compulsory charity",
        "long_description": "The third pillar of Islam requiring Muslims to give a fixed portion of their wealth to the needy.",
        "hint": {
            "en": "Obligatory charity — giving a fixed portion of wealth to the needy",
            "ar": "الزكاة — إعطاء نسبة محددة من المال للمحتاجين",
            "fr": "L'aumône obligatoire — donner une part fixe de sa richesse aux nécessiteux",
        },
    },
    {
        "word": "Sadaqah",
        "category": "Charitable Practices",
        "short_description": "Voluntary charity",
        "long_description": "Voluntary charitable acts extending beyond monetary donations to include acts of kindness.",
        "hint": {
            "en": "Voluntary charity and acts of kindness beyond obligatory giving",
            "ar": "الصدقة التطوعية وأعمال الخير التي تتجاوز العطاء الواجب",
            "fr": "La charité volontaire et les actes de bonté au-delà du don obligatoire",
        },
    },
    {
        "word": "Shahada",
        "category": "Pillars of Islam",
        "short_description": "Declaration of faith",
        "long_description": "The first pillar of Islam expressing faith in the oneness of Allah and prophethood of Muhammad.",
        "hint": {
            "en": "The declaration of faith — 'There is no god but Allah, and Muhammad is His messenger'",
            "ar": "شهادة أن لا إله إلا الله وأن محمداً رسول الله",
            "fr": "La déclaration de foi — 'Il n'y a de dieu qu'Allah et Muhammad est Son messager'",
        },
    },
    {
        "word": "Tawhid",
        "category": "Islamic Beliefs",
        "short_description": "Oneness of God",
        "long_description": "The principle of monotheism in Islam affirming the oneness and absolute sovereignty of God.",
        "hint": {
            "en": "The fundamental principle of God's oneness and absolute sovereignty",
            "ar": "المبدأ الأساسي لوحدانية الله وسيادته المطلقة",
            "fr": "Le principe fondamental de l'unicité de Dieu et de Sa souveraineté absolue",
        },
    },
    # Prophets and figures
    {
        "word": "Ibrahim",
        "category": "Prophets",
        "short_description": "Prophet Abraham in Islam",
        "long_description": "Prophet Ibrahim (Abraham) is considered the father of monotheism and a key prophet in Islam.",
        "hint": {
            "en": "Prophet Abraham, the father of monotheism and a key prophet in Islam",
            "ar": "النبي إبراهيم، أبو الأنبياء ورمز التوحيد في الإسلام",
            "fr": "Le prophète Abraham, père du monothéisme et prophète majeur de l'islam",
        },
    },
    {
        "word": "Ismail",
        "category": "Prophets",
        "short_description": "Prophet Ishmael in Islam",
        "long_description": "Prophet Ismail (Ishmael), son of Ibrahim, is regarded as a prophet and ancestor of the Arab people.",
        "hint": {
            "en": "Prophet Ishmael, son of Ibrahim and ancestor of the Arab people",
            "ar": "النبي إسماعيل، ابن إبراهيم وجد العرب",
            "fr": "Le prophète Ismaël, fils d'Ibrahim et ancêtre du peuple arabe",
        },
    },
    {
        "word": "Musa",
        "category": "Prophets",
        "short_description": "Prophet Moses in Islam",
        "long_description": "Prophet Musa (Moses) is one of the most frequently mentioned prophets in the Quran.",
        "hint": {
            "en": "Prophet Moses, one of the most mentioned prophets in the Quran",
            "ar": "النبي موسى، من أكثر الأنبياء ذكراً في القرآن الكريم",
            "fr": "Le prophète Moïse, l'un des prophètes les plus mentionnés dans le Coran",
        },
    },
    {
        "word": "Isa",
        "category": "Prophets",
        "short_description": "Prophet Jesus in Islam",
        "long_description": "Prophet Isa (Jesus) is a revered prophet in Islam, born miraculously to Maryam.",
        "hint": {
            "en": "Prophet Jesus, a revered prophet in Islam born miraculously to Maryam",
            "ar": "النبي عيسى، نبي مبجل في الإسلام ولد بمعجزة لمريم",
            "fr": "Le prophète Jésus, un prophète vénéré en islam né miraculeusement de Maryam",
        },
    },
    {
        "word": "Maryam",
        "category": "Islamic Figures",
        "short_description": "Mother of Prophet Isa",
        "long_description": "Maryam (Mary) is the only woman mentioned by name in the Quran, revered for her piety.",
        "hint": {
            "en": "Mary, the only woman mentioned by name in the Quran, mother of Prophet Isa",
            "ar": "مريم، المرأة الوحيدة المذكورة بالاسم في القرآن، أم النبي عيسى",
            "fr": "Marie, la seule femme mentionnée par son nom dans le Coran, mère du prophète Jésus",
        },
    },
    {
        "word": "Khadijah",
        "category": "Islamic Figures",
        "short_description": "First wife of the Prophet",
        "long_description": "Khadijah bint Khuwaylid was the first wife of Prophet Muhammad and the first person to accept Islam.",
        "hint": {
            "en": "First wife of Prophet Muhammad and the first person to accept Islam",
            "ar": "خديجة بنت خويلد، أولى زوجات النبي محمد وأول من أسلم",
            "fr": "Première épouse du Prophète Muhammad et première personne à accepter l'islam",
        },
    },
    # Places
    {
        "word": "Masjid",
        "category": "Islamic Places",
        "short_description": "Place of worship",
        "long_description": "A masjid (mosque) is a place of worship for Muslims, used for daily prayers and community gatherings.",
        "hint": {
            "en": "A mosque — the place of worship for Muslims, used for prayers and gatherings",
            "ar": "المسجد — مكان العبادة للمسلمين، يُستخدم للصلاة والتجمعات",
            "fr": "Une mosquée — le lieu de culte des musulmans, utilisé pour les prières et les rassemblements",
        },
    },
    {
        "word": "Mihrab",
        "category": "Islamic Architecture",
        "short_description": "Prayer niche in a mosque",
        "long_description": "The mihrab is a semicircular niche in the wall of a mosque that indicates the direction of Mecca.",
        "hint": {
            "en": "A semicircular niche in a mosque wall indicating the direction of Mecca",
            "ar": "محراب — تجويف نصف دائري في جدار المسجد يشير إلى اتجاه مكة",
            "fr": "Une niche semi-circulaire dans le mur d'une mosquée indiquant la direction de La Mecque",
        },
    },
    {
        "word": "Minbar",
        "category": "Islamic Architecture",
        "short_description": "Pulpit in a mosque",
        "long_description": "The minbar is a raised platform or pulpit in a mosque where the imam delivers the Friday sermon.",
        "hint": {
            "en": "A raised pulpit in a mosque where the imam delivers the Friday sermon",
            "ar": "المنبر — منصة مرتفعة في المسجد يلقي منها الإمام خطبة الجمعة",
            "fr": "Une chaire surélevée dans une mosquée où l'imam prononce le sermon du vendredi",
        },
    },
    {
        "word": "Minaret",
        "category": "Islamic Architecture",
        "short_description": "Tower of a mosque",
        "long_description": "A minaret is a tower from which the call to prayer (adhan) is traditionally broadcast.",
        "hint": {
            "en": "A tower from which the call to prayer is traditionally broadcast",
            "ar": "المئذنة — برج يُرفع منه الأذان تقليدياً",
            "fr": "Une tour d'où l'appel à la prière est traditionnellement lancé",
        },
    },
    {
        "word": "Kaaba",
        "category": "Islamic Places",
        "short_description": "Sacred cube structure in Mecca",
        "long_description": "The Kaaba is the most sacred site in Islam, located in the center of Masjid al-Haram in Mecca.",
        "hint": {
            "en": "The most sacred site in Islam, a cube structure at the center of Masjid al-Haram in Mecca",
            "ar": "الكعبة المشرفة — أقدس موقع في الإسلام، في وسط المسجد الحرام بمكة",
            "fr": "Le site le plus sacré de l'islam, une structure cubique au centre de Masjid al-Haram à La Mecque",
        },
    },
    {
        "word": "Medina",
        "category": "Islamic Places",
        "short_description": "City of the Prophet",
        "long_description": "Medina is the second holiest city in Islam where Prophet Muhammad migrated to and is buried.",
        "hint": {
            "en": "The second holiest city in Islam where the Prophet migrated to and is buried",
            "ar": "المدينة المنورة — ثاني أقدس مدينة في الإسلام حيث هاجر النبي ودُفن فيها",
            "fr": "La deuxième ville la plus sainte de l'islam où le Prophète a émigré et est enterré",
        },
    },
    # Concepts
    {
        "word": "Tawakkul",
        "category": "Islamic Concepts",
        "short_description": "Trust in God",
        "long_description": "Tawakkul is the Islamic concept of placing complete trust and reliance in God's plan.",
        "hint": {
            "en": "The Islamic concept of placing complete trust and reliance in God's plan",
            "ar": "التوكل على الله — الاعتماد الكامل على الله والثقة بتدبيره",
            "fr": "Le concept islamique de placer sa confiance totale en le plan de Dieu",
        },
    },
    {
        "word": "Sabr",
        "category": "Islamic Concepts",
        "short_description": "Patience",
        "long_description": "Sabr is the virtue of patience and perseverance in the face of hardship, a core Islamic concept.",
        "hint": {
            "en": "The virtue of patience and perseverance in the face of hardship",
            "ar": "الصبر — فضيلة التحمل والمثابرة في مواجهة الشدائد",
            "fr": "La vertu de patience et de persévérance face aux épreuves",
        },
    },
    {
        "word": "Shukr",
        "category": "Islamic Concepts",
        "short_description": "Gratitude",
        "long_description": "Shukr is the practice of showing gratitude to Allah for blessings, both in words and actions.",
        "hint": {
            "en": "The practice of showing gratitude to Allah for blessings, in words and actions",
            "ar": "الشكر — إظهار الامتنان لله على النعم بالقول والفعل",
            "fr": "La pratique de la gratitude envers Allah pour Ses bienfaits, en paroles et en actes",
        },
    },
    {
        "word": "Taqwa",
        "category": "Islamic Concepts",
        "short_description": "God-consciousness",
        "long_description": "Taqwa is the awareness of God in all aspects of life, often translated as piety or mindfulness.",
        "hint": {
            "en": "Awareness of God in all aspects of life, often translated as piety or mindfulness",
            "ar": "التقوى — الوعي بالله في جميع جوانب الحياة",
            "fr": "La conscience de Dieu dans tous les aspects de la vie, souvent traduite par piété",
        },
    },
    {
        "word": "Ihsan",
        "category": "Islamic Concepts",
        "short_description": "Excellence in worship",
        "long_description": "Ihsan means to worship Allah as if you see Him, and if you cannot see Him, He sees you.",
        "hint": {
            "en": "Excellence in worship — to worship Allah as if you see Him",
            "ar": "الإحسان — أن تعبد الله كأنك تراه، فإن لم تكن تراه فإنه يراك",
            "fr": "L'excellence dans l'adoration — adorer Allah comme si tu Le voyais",
        },
    },
    {
        "word": "Iman",
        "category": "Islamic Beliefs",
        "short_description": "Faith",
        "long_description": "Iman encompasses belief in God, His angels, His books, His messengers, the Last Day, and divine decree.",
        "hint": {
            "en": "Faith encompassing belief in God, angels, holy books, messengers, the Last Day, and divine decree",
            "ar": "الإيمان — التصديق بالله وملائكته وكتبه ورسله واليوم الآخر والقدر",
            "fr": "La foi englobant la croyance en Dieu, Ses anges, Ses livres, Ses messagers, le Jour dernier et le destin",
        },
    },
    {
        "word": "Jihad",
        "category": "Islamic Concepts",
        "short_description": "Struggle in God's way",
        "long_description": "Jihad represents struggle against evil inclinations and effort in the way of God.",
        "hint": {
            "en": "Struggle and effort in the way of God, including inner spiritual struggle",
            "ar": "الجهاد في سبيل الله، بما في ذلك الجهاد الروحي الداخلي",
            "fr": "L'effort et la lutte dans la voie de Dieu, y compris la lutte spirituelle intérieure",
        },
    },
    {
        "word": "Hijrah",
        "category": "Islamic History",
        "short_description": "Migration to Medina",
        "long_description": "The Hijrah is the migration of Prophet Muhammad from Mecca to Medina in 622 CE.",
        "hint": {
            "en": "The Prophet's migration from Mecca to Medina in 622 CE, start of the Islamic calendar",
            "ar": "هجرة النبي من مكة إلى المدينة عام 622 م، بداية التقويم الهجري",
            "fr": "La migration du Prophète de La Mecque à Médine en 622, début du calendrier islamique",
        },
    },
    # Practices
    {
        "word": "Wudu",
        "category": "Islamic Practices",
        "short_description": "Ablution before prayer",
        "long_description": "Wudu is the ritual washing performed by Muslims before prayer to achieve physical and spiritual purity.",
        "hint": {
            "en": "Ritual washing performed before prayer for physical and spiritual purity",
            "ar": "الوضوء — الغسل الطقسي قبل الصلاة لتحقيق الطهارة الجسدية والروحية",
            "fr": "L'ablution rituelle effectuée avant la prière pour la pureté physique et spirituelle",
        },
    },
    {
        "word": "Tayammum",
        "category": "Islamic Practices",
        "short_description": "Dry ablution",
        "long_description": "Tayammum is the Islamic act of dry ablution using clean earth when water is unavailable.",
        "hint": {
            "en": "Dry ablution using clean earth or sand when water is unavailable",
            "ar": "التيمم — الطهارة الجافة باستخدام التراب النظيف عند عدم توفر الماء",
            "fr": "L'ablution sèche utilisant de la terre propre lorsque l'eau n'est pas disponible",
        },
    },
    {
        "word": "Adhan",
        "category": "Islamic Practices",
        "short_description": "Call to prayer",
        "long_description": "The adhan is the Islamic call to prayer recited by the muezzin from the mosque five times daily.",
        "hint": {
            "en": "The Islamic call to prayer recited by the muezzin five times daily",
            "ar": "الأذان — النداء للصلاة الذي يرفعه المؤذن خمس مرات يومياً",
            "fr": "L'appel islamique à la prière récité par le muezzin cinq fois par jour",
        },
    },
    {
        "word": "Iqamah",
        "category": "Islamic Practices",
        "short_description": "Second call to prayer",
        "long_description": "The iqamah is the second call to prayer given immediately before the congregational prayer begins.",
        "hint": {
            "en": "The second call to prayer given just before the congregational prayer starts",
            "ar": "الإقامة — النداء الثاني للصلاة قبل بدء صلاة الجماعة مباشرة",
            "fr": "Le second appel à la prière donné juste avant le début de la prière en congrégation",
        },
    },
    {
        "word": "Dhikr",
        "category": "Islamic Practices",
        "short_description": "Remembrance of God",
        "long_description": "Dhikr is the devotional act of remembering God through phrases, prayers, or meditation.",
        "hint": {
            "en": "The devotional act of remembering God through phrases, prayers, or meditation",
            "ar": "الذكر — العبادة التأملية لذكر الله بالتسبيح والدعاء والتأمل",
            "fr": "L'acte dévotionnel de se souvenir de Dieu par des phrases, prières ou méditation",
        },
    },
    {
        "word": "Dua",
        "category": "Islamic Practices",
        "short_description": "Supplication",
        "long_description": "Dua is the act of supplication or personal prayer where Muslims directly communicate with God.",
        "hint": {
            "en": "Personal supplication or prayer where Muslims directly communicate with God",
            "ar": "الدعاء — التضرع الشخصي حيث يتواصل المسلم مباشرة مع الله",
            "fr": "La supplication personnelle où les musulmans communiquent directement avec Dieu",
        },
    },
    {
        "word": "Quran",
        "category": "Islamic Texts",
        "short_description": "Holy book of Islam",
        "long_description": "The Quran is the central religious text of Islam believed to be the direct word of God.",
        "hint": {
            "en": "The holy book of Islam, believed to be the direct word of God revealed to Prophet Muhammad",
            "ar": "القرآن الكريم — كلام الله المنزل على النبي محمد",
            "fr": "Le livre saint de l'islam, considéré comme la parole directe de Dieu révélée au Prophète Muhammad",
        },
    },
    {
        "word": "Hadith",
        "category": "Islamic Texts",
        "short_description": "Prophetic traditions",
        "long_description": "Hadiths are records of the sayings, actions, and approvals of Prophet Muhammad.",
        "hint": {
            "en": "Records of the sayings, actions, and approvals of Prophet Muhammad",
            "ar": "الأحاديث — سجلات أقوال وأفعال وتقريرات النبي محمد",
            "fr": "Les récits des paroles, actes et approbations du Prophète Muhammad",
        },
    },
    {
        "word": "Sunnah",
        "category": "Islamic Practices",
        "short_description": "Prophetic tradition and way of life",
        "long_description": "The Sunnah refers to the practices and teachings of Prophet Muhammad as a model for Muslims.",
        "hint": {
            "en": "The practices and teachings of Prophet Muhammad as a model for Muslim life",
            "ar": "السنة النبوية — ممارسات وتعاليم النبي محمد كنموذج للمسلمين",
            "fr": "Les pratiques et enseignements du Prophète Muhammad comme modèle de vie musulmane",
        },
    },
    {
        "word": "Fiqh",
        "category": "Islamic Sciences",
        "short_description": "Islamic jurisprudence",
        "long_description": "Fiqh is the body of Islamic jurisprudence dealing with the observance of rituals, morals, and social legislation.",
        "hint": {
            "en": "Islamic jurisprudence dealing with rituals, morals, and social legislation",
            "ar": "الفقه — علم الشريعة الإسلامية المتعلق بالعبادات والأخلاق والتشريعات",
            "fr": "La jurisprudence islamique traitant des rituels, de la morale et de la législation sociale",
        },
    },
    # Food and daily life
    {
        "word": "Halal",
        "category": "Islamic Law",
        "short_description": "Permissible",
        "long_description": "Halal refers to what is permissible under Islamic law, commonly used in reference to food.",
        "hint": {
            "en": "What is permissible under Islamic law, commonly used in reference to food",
            "ar": "الحلال — ما هو مباح في الشريعة الإسلامية، يُستخدم عادة للإشارة إلى الطعام",
            "fr": "Ce qui est permis par la loi islamique, couramment utilisé en référence à la nourriture",
        },
    },
    {
        "word": "Haram",
        "category": "Islamic Law",
        "short_description": "Forbidden",
        "long_description": "Haram refers to anything that is forbidden under Islamic law.",
        "hint": {
            "en": "Anything that is forbidden or prohibited under Islamic law",
            "ar": "الحرام — كل ما هو محظور في الشريعة الإسلامية",
            "fr": "Tout ce qui est interdit ou prohibé par la loi islamique",
        },
    },
    {
        "word": "Iftar",
        "category": "Ramadan",
        "short_description": "Breaking the fast",
        "long_description": "Iftar is the meal eaten by Muslims after sunset during Ramadan to break the daily fast.",
        "hint": {
            "en": "The meal eaten after sunset during Ramadan to break the daily fast",
            "ar": "الإفطار — الوجبة التي يتناولها المسلمون بعد غروب الشمس في رمضان",
            "fr": "Le repas pris après le coucher du soleil pendant le Ramadan pour rompre le jeûne",
        },
    },
    {
        "word": "Suhoor",
        "category": "Ramadan",
        "short_description": "Pre-dawn meal",
        "long_description": "Suhoor is the pre-dawn meal consumed by Muslims before beginning the fast during Ramadan.",
        "hint": {
            "en": "The pre-dawn meal consumed before beginning the daily fast during Ramadan",
            "ar": "السحور — الوجبة قبل الفجر التي يتناولها المسلمون قبل بدء الصيام في رمضان",
            "fr": "Le repas pré-aube consommé avant de commencer le jeûne quotidien pendant le Ramadan",
        },
    },
    # Special times and events
    {
        "word": "Laylat al-Qadr",
        "category": "Islamic Events",
        "short_description": "Night of Power",
        "long_description": "Laylat al-Qadr is the most sacred night in Islam, believed to be when the Quran was first revealed.",
        "hint": {
            "en": "The most sacred night in Islam, when the Quran was first revealed — better than a thousand months",
            "ar": "ليلة القدر — أقدس ليلة في الإسلام، نزل فيها القرآن، خير من ألف شهر",
            "fr": "La nuit la plus sacrée de l'islam, quand le Coran fut révélé — meilleure que mille mois",
        },
    },
    {
        "word": "Eid al-Fitr",
        "category": "Islamic Holidays",
        "short_description": "Festival of breaking the fast",
        "long_description": "Eid al-Fitr marks the end of Ramadan and is celebrated with prayers, feasts, and giving.",
        "hint": {
            "en": "The festival marking the end of Ramadan, celebrated with prayers, feasts, and charity",
            "ar": "عيد الفطر — العيد الذي يختتم شهر رمضان، يُحتفل به بالصلاة والولائم والصدقة",
            "fr": "La fête marquant la fin du Ramadan, célébrée avec prières, festins et charité",
        },
    },
    {
        "word": "Eid al-Adha",
        "category": "Islamic Holidays",
        "short_description": "Festival of sacrifice",
        "long_description": "Eid al-Adha commemorates Ibrahim's willingness to sacrifice his son and concludes the Hajj.",
        "hint": {
            "en": "The festival of sacrifice commemorating Ibrahim's willingness to sacrifice his son",
            "ar": "عيد الأضحى — يُحيي ذكرى استعداد إبراهيم للتضحية بابنه ويختتم موسم الحج",
            "fr": "La fête du sacrifice commémorant la volonté d'Ibrahim de sacrifier son fils",
        },
    },
    {
        "word": "Jummah",
        "category": "Islamic Practices",
        "short_description": "Friday congregational prayer",
        "long_description": "Jummah is the congregational prayer held every Friday, the most important prayer of the week.",
        "hint": {
            "en": "The congregational prayer held every Friday, the most important prayer of the week",
            "ar": "صلاة الجمعة — الصلاة الجماعية كل يوم جمعة، أهم صلاة في الأسبوع",
            "fr": "La prière en congrégation tenue chaque vendredi, la plus importante prière de la semaine",
        },
    },
]

# Word pairs (each pair contains two related but different Islamic terms)
UNDERCOVER_WORD_PAIRS = [
    ("Hajj", "Umrah"),
    ("Salah", "Sawm"),
    ("Zakat", "Sadaqah"),
    ("Shahada", "Tawhid"),
    ("Jihad", "Hijrah"),
    ("Ibrahim", "Ismail"),
    ("Musa", "Isa"),
    ("Maryam", "Khadijah"),
    ("Masjid", "Mihrab"),
    ("Minbar", "Minaret"),
    ("Kaaba", "Medina"),
    ("Tawakkul", "Sabr"),
    ("Shukr", "Taqwa"),
    ("Ihsan", "Iman"),
    ("Wudu", "Tayammum"),
    ("Adhan", "Iqamah"),
    ("Dhikr", "Dua"),
    ("Quran", "Hadith"),
    ("Sunnah", "Fiqh"),
    ("Halal", "Haram"),
    ("Iftar", "Suhoor"),
    ("Eid al-Fitr", "Eid al-Adha"),
    ("Laylat al-Qadr", "Jummah"),
    ("Salah", "Dua"),
    ("Zakat", "Hajj"),
    ("Quran", "Sunnah"),
    ("Sabr", "Shukr"),
    ("Taqwa", "Ihsan"),
    ("Masjid", "Kaaba"),
    ("Wudu", "Salah"),
    ("Ibrahim", "Musa"),
    ("Adhan", "Jummah"),
]


# ── Codenames word packs (100+ Islamic terms in categories) ─────────────────

CODENAMES_WORD_PACKS: dict[str, list[dict[str, str | dict[str, str]]]] = {
    "Prophets & Messengers": [
        {"word": "Adam", "hint": {"en": "The first human and prophet created by Allah", "ar": "أول إنسان ونبي خلقه الله", "fr": "Le premier humain et prophète créé par Allah"}},
        {"word": "Nuh", "hint": {"en": "Prophet Noah, who built the Ark to survive the great flood", "ar": "النبي نوح، الذي بنى السفينة للنجاة من الطوفان العظيم", "fr": "Le prophète Noé, qui construisit l'Arche pour survivre au déluge"}},
        {"word": "Ibrahim", "hint": {"en": "Prophet Abraham, father of monotheism", "ar": "النبي إبراهيم، أبو الأنبياء ورمز التوحيد", "fr": "Le prophète Abraham, père du monothéisme"}},
        {"word": "Ismail", "hint": {"en": "Prophet Ishmael, son of Ibrahim and ancestor of the Arabs", "ar": "النبي إسماعيل، ابن إبراهيم وجد العرب", "fr": "Le prophète Ismaël, fils d'Ibrahim et ancêtre des Arabes"}},
        {"word": "Ishaq", "hint": {"en": "Prophet Isaac, son of Ibrahim and father of Yaqub", "ar": "النبي إسحاق، ابن إبراهيم وأبو يعقوب", "fr": "Le prophète Isaac, fils d'Ibrahim et père de Yaqub"}},
        {"word": "Yaqub", "hint": {"en": "Prophet Jacob, also known as Israel, father of the twelve tribes", "ar": "النبي يعقوب، المعروف أيضاً بإسرائيل، أبو الأسباط الاثني عشر", "fr": "Le prophète Jacob, aussi connu comme Israël, père des douze tribus"}},
        {"word": "Yusuf", "hint": {"en": "Prophet Joseph, known for his beauty and the story of his brothers", "ar": "النبي يوسف، المعروف بجماله وقصته مع إخوته", "fr": "Le prophète Joseph, connu pour sa beauté et l'histoire de ses frères"}},
        {"word": "Musa", "hint": {"en": "Prophet Moses, who received the Torah and parted the sea", "ar": "النبي موسى، الذي أُنزلت عليه التوراة وشق البحر", "fr": "Le prophète Moïse, qui reçut la Torah et fendit la mer"}},
        {"word": "Harun", "hint": {"en": "Prophet Aaron, brother and helper of Musa", "ar": "النبي هارون، أخو موسى ومعاونه", "fr": "Le prophète Aaron, frère et assistant de Moïse"}},
        {"word": "Dawud", "hint": {"en": "Prophet David, king and psalmist who received the Zabur", "ar": "النبي داوود، الملك الذي أُنزل عليه الزبور", "fr": "Le prophète David, roi et psalmiste qui reçut le Zabour"}},
        {"word": "Sulayman", "hint": {"en": "Prophet Solomon, known for his wisdom and kingdom over humans and jinn", "ar": "النبي سليمان، المعروف بحكمته وملكه على الإنس والجن", "fr": "Le prophète Salomon, connu pour sa sagesse et son royaume sur les humains et les djinns"}},
        {"word": "Isa", "hint": {"en": "Prophet Jesus, born miraculously to Maryam", "ar": "النبي عيسى، ولد بمعجزة لمريم", "fr": "Le prophète Jésus, né miraculeusement de Maryam"}},
        {"word": "Muhammad", "hint": {"en": "The final Prophet and Messenger of Allah, seal of the prophets", "ar": "النبي محمد، خاتم الأنبياء والمرسلين", "fr": "Le dernier Prophète et Messager d'Allah, sceau des prophètes"}},
        {"word": "Ayyub", "hint": {"en": "Prophet Job, symbol of patience through severe trials", "ar": "النبي أيوب، رمز الصبر على البلاء الشديد", "fr": "Le prophète Job, symbole de patience face aux épreuves"}},
        {"word": "Yunus", "hint": {"en": "Prophet Jonah, who was swallowed by a whale and repented", "ar": "النبي يونس، الذي ابتلعه الحوت فتاب إلى الله", "fr": "Le prophète Jonas, avalé par une baleine et qui se repentit"}},
        {"word": "Idris", "hint": {"en": "Prophet Enoch, known for his piety and knowledge", "ar": "النبي إدريس، المعروف بتقواه وعلمه", "fr": "Le prophète Énoch, connu pour sa piété et son savoir"}},
        {"word": "Hud", "hint": {"en": "Prophet sent to the people of 'Ad, who rejected his message", "ar": "النبي هود، أُرسل إلى قوم عاد الذين رفضوا رسالته", "fr": "Prophète envoyé au peuple de 'Ad, qui rejeta son message"}},
        {"word": "Salih", "hint": {"en": "Prophet sent to the people of Thamud with the miracle of the she-camel", "ar": "النبي صالح، أُرسل إلى قوم ثمود بمعجزة الناقة", "fr": "Prophète envoyé au peuple de Thamoud avec le miracle de la chamelle"}},
        {"word": "Shuayb", "hint": {"en": "Prophet sent to the people of Madyan, known as the orator of the prophets", "ar": "النبي شعيب، أُرسل إلى أهل مدين، خطيب الأنبياء", "fr": "Prophète envoyé au peuple de Madyan, connu comme l'orateur des prophètes"}},
        {"word": "Lut", "hint": {"en": "Prophet Lot, nephew of Ibrahim who warned his people against immorality", "ar": "النبي لوط، ابن أخي إبراهيم الذي حذر قومه من الفاحشة", "fr": "Le prophète Loth, neveu d'Ibrahim qui avertit son peuple contre l'immoralité"}},
    ],
    "Quran & Surahs": [
        {"word": "Fatiha", "hint": {"en": "The Opening — first surah of the Quran, recited in every prayer", "ar": "الفاتحة — أول سورة في القرآن، تُقرأ في كل صلاة", "fr": "L'Ouverture — première sourate du Coran, récitée dans chaque prière"}},
        {"word": "Baqarah", "hint": {"en": "The Cow — longest surah in the Quran", "ar": "البقرة — أطول سورة في القرآن الكريم", "fr": "La Vache — la plus longue sourate du Coran"}},
        {"word": "Yasin", "hint": {"en": "Often called the heart of the Quran", "ar": "يس — تُسمى قلب القرآن", "fr": "Souvent appelée le cœur du Coran"}},
        {"word": "Rahman", "hint": {"en": "The Most Merciful — known for the refrain 'Which of your Lord's favors will you deny?'", "ar": "الرحمن — المعروفة بتكرار 'فبأي آلاء ربكما تكذبان'", "fr": "Le Tout Miséricordieux — connue pour le refrain 'Lequel des bienfaits de votre Seigneur nierez-vous ?'"}},
        {"word": "Mulk", "hint": {"en": "The Sovereignty — protects from the punishment of the grave", "ar": "الملك — تقي من عذاب القبر", "fr": "La Royauté — protège du châtiment de la tombe"}},
        {"word": "Kahf", "hint": {"en": "The Cave — recommended to read on Fridays, contains four stories", "ar": "الكهف — يُستحب قراءتها يوم الجمعة، تحتوي أربع قصص", "fr": "La Caverne — recommandée le vendredi, contient quatre récits"}},
        {"word": "Maryam", "hint": {"en": "Surah named after Mary, mother of Prophet Isa", "ar": "سورة مريم — سُميت على اسم مريم أم النبي عيسى", "fr": "Sourate nommée d'après Marie, mère du prophète Jésus"}},
        {"word": "Taha", "hint": {"en": "Surah beginning with mystical letters, recounts the story of Musa", "ar": "سورة طه — تبدأ بحروف مقطعة وتروي قصة موسى", "fr": "Sourate commençant par des lettres mystiques, raconte l'histoire de Moïse"}},
        {"word": "Naba", "hint": {"en": "The Great News — about the Day of Judgment", "ar": "النبأ — عن يوم القيامة", "fr": "La Nouvelle — à propos du Jour du Jugement"}},
        {"word": "Ikhlas", "hint": {"en": "Purity of Faith — equal to one-third of the Quran in reward", "ar": "الإخلاص — تعادل ثلث القرآن في الأجر", "fr": "La Pureté de la Foi — équivalente à un tiers du Coran en récompense"}},
        {"word": "Falaq", "hint": {"en": "The Daybreak — a protective surah seeking refuge from evil", "ar": "الفلق — سورة حماية يُستعاذ بها من الشر", "fr": "L'Aube naissante — sourate protectrice contre le mal"}},
        {"word": "Nas", "hint": {"en": "Mankind — the final surah, seeking refuge from the whisperer", "ar": "الناس — آخر سورة، يُستعاذ بها من الوسواس", "fr": "Les Hommes — dernière sourate, cherchant refuge contre le tentateur"}},
        {"word": "Ayah", "hint": {"en": "A verse of the Quran, also means 'sign' from God", "ar": "آية — جملة من القرآن، تعني أيضاً 'علامة' من الله", "fr": "Un verset du Coran, signifie aussi 'signe' de Dieu"}},
        {"word": "Juz", "hint": {"en": "One of 30 equal parts of the Quran", "ar": "جزء — واحد من ثلاثين جزءاً متساوياً من القرآن", "fr": "L'une des 30 parties égales du Coran"}},
        {"word": "Hizb", "hint": {"en": "Half a Juz — the Quran is divided into 60 Hizbs", "ar": "حزب — نصف جزء، القرآن مقسم إلى 60 حزباً", "fr": "La moitié d'un Juz — le Coran est divisé en 60 Hizbs"}},
        {"word": "Tanzil", "hint": {"en": "The revelation or sending down of the Quran from God", "ar": "التنزيل — إنزال القرآن من عند الله", "fr": "La révélation ou la descente du Coran de Dieu"}},
        {"word": "Tafsir", "hint": {"en": "Exegesis and interpretation of the Quran", "ar": "التفسير — شرح وتأويل القرآن الكريم", "fr": "L'exégèse et l'interprétation du Coran"}},
        {"word": "Tajweed", "hint": {"en": "The rules of proper Quran recitation and pronunciation", "ar": "التجويد — قواعد تلاوة القرآن ونطقه الصحيح", "fr": "Les règles de récitation correcte et de prononciation du Coran"}},
        {"word": "Tilawah", "hint": {"en": "The act of reciting the Quran aloud", "ar": "التلاوة — قراءة القرآن جهراً", "fr": "L'acte de réciter le Coran à voix haute"}},
        {"word": "Mushaf", "hint": {"en": "The physical written copy of the Quran", "ar": "المصحف — النسخة المكتوبة من القرآن الكريم", "fr": "L'exemplaire physique écrit du Coran"}},
    ],
    "Islamic History": [
        {"word": "Hijrah", "hint": {"en": "The Prophet's migration from Mecca to Medina in 622 CE", "ar": "هجرة النبي من مكة إلى المدينة عام 622 م", "fr": "La migration du Prophète de La Mecque à Médine en 622"}},
        {"word": "Badr", "hint": {"en": "First major battle of Islam, a decisive Muslim victory in 624 CE", "ar": "بدر — أول معركة كبرى في الإسلام، انتصار حاسم عام 624 م", "fr": "Première grande bataille de l'islam, victoire décisive des musulmans en 624"}},
        {"word": "Uhud", "hint": {"en": "Second major battle near Medina where Muslims faced setbacks", "ar": "أحد — ثاني معركة كبرى قرب المدينة حيث واجه المسلمون انتكاسة", "fr": "Deuxième grande bataille près de Médine où les musulmans subirent des revers"}},
        {"word": "Khandaq", "hint": {"en": "The Battle of the Trench — Muslims dug a defensive trench around Medina", "ar": "الخندق — حفر المسلمون خندقاً دفاعياً حول المدينة", "fr": "La bataille du Fossé — les musulmans creusèrent un fossé défensif autour de Médine"}},
        {"word": "Hudaybiyyah", "hint": {"en": "Peace treaty between Muslims and Quraysh that the Quran called a clear victory", "ar": "الحديبية — معاهدة سلام بين المسلمين وقريش وصفها القرآن بالفتح المبين", "fr": "Traité de paix entre les musulmans et Quraysh que le Coran qualifia de victoire éclatante"}},
        {"word": "Mecca", "hint": {"en": "The holiest city in Islam, birthplace of the Prophet and home of the Kaaba", "ar": "مكة المكرمة — أقدس مدينة في الإسلام، مسقط رأس النبي وموطن الكعبة", "fr": "La ville la plus sainte de l'islam, lieu de naissance du Prophète et de la Kaaba"}},
        {"word": "Medina", "hint": {"en": "The city of the Prophet, second holiest city in Islam", "ar": "المدينة المنورة — مدينة النبي، ثاني أقدس مدينة في الإسلام", "fr": "La ville du Prophète, deuxième ville la plus sainte de l'islam"}},
        {"word": "Abyssinia", "hint": {"en": "Land of the first Muslim migration, where the Negus gave them refuge", "ar": "الحبشة — أرض أول هجرة إسلامية حيث آواهم النجاشي", "fr": "Terre de la première migration musulmane, où le Négus leur donna refuge"}},
        {"word": "Taif", "hint": {"en": "City where the Prophet was rejected and stoned but forgave its people", "ar": "الطائف — المدينة التي رُفض فيها النبي ورُجم لكنه عفا عن أهلها", "fr": "Ville où le Prophète fut rejeté et lapidé mais pardonna à ses habitants"}},
        {"word": "Tabuk", "hint": {"en": "The last military expedition led by the Prophet in 630 CE", "ar": "تبوك — آخر غزوة قادها النبي عام 630 م", "fr": "La dernière expédition militaire menée par le Prophète en 630"}},
        {"word": "Khaybar", "hint": {"en": "Jewish fortress conquered by Muslims, known for Ali's bravery", "ar": "خيبر — حصن يهودي فتحه المسلمون، اشتهرت بشجاعة علي", "fr": "Forteresse juive conquise par les musulmans, connue pour la bravoure d'Ali"}},
        {"word": "Caliphate", "hint": {"en": "The Islamic system of governance after the Prophet's death", "ar": "الخلافة — نظام الحكم الإسلامي بعد وفاة النبي", "fr": "Le système de gouvernance islamique après la mort du Prophète"}},
        {"word": "Umayyad", "hint": {"en": "First hereditary Islamic dynasty, based in Damascus (661-750 CE)", "ar": "الأمويون — أول سلالة إسلامية وراثية، مقرها دمشق", "fr": "Première dynastie islamique héréditaire, basée à Damas (661-750)"}},
        {"word": "Abbasid", "hint": {"en": "Islamic dynasty known as the Golden Age of Islam, based in Baghdad", "ar": "العباسيون — السلالة المعروفة بالعصر الذهبي للإسلام، مقرها بغداد", "fr": "Dynastie islamique connue comme l'Âge d'or de l'islam, basée à Bagdad"}},
        {"word": "Ottoman", "hint": {"en": "Last major Islamic empire, ruled from Istanbul for over 600 years", "ar": "العثمانيون — آخر إمبراطورية إسلامية كبرى، حكمت من إسطنبول لأكثر من 600 عام", "fr": "Dernier grand empire islamique, gouvernant depuis Istanbul pendant plus de 600 ans"}},
        {"word": "Andalusia", "hint": {"en": "Muslim-ruled Iberian Peninsula, a beacon of learning and coexistence", "ar": "الأندلس — شبه الجزيرة الإيبيرية تحت الحكم الإسلامي، منارة للعلم والتعايش", "fr": "La péninsule ibérique sous domination musulmane, phare de savoir et de coexistence"}},
        {"word": "Baghdad", "hint": {"en": "Capital of the Abbasid Caliphate and center of the Islamic Golden Age", "ar": "بغداد — عاصمة الخلافة العباسية ومركز العصر الذهبي الإسلامي", "fr": "Capitale du califat abbasside et centre de l'Âge d'or islamique"}},
        {"word": "Damascus", "hint": {"en": "Capital of the Umayyad Caliphate, one of the oldest continuously inhabited cities", "ar": "دمشق — عاصمة الخلافة الأموية، من أقدم المدن المأهولة باستمرار", "fr": "Capitale du califat omeyyade, l'une des plus anciennes villes habitées en continu"}},
        {"word": "Cordoba", "hint": {"en": "Heart of Al-Andalus, famous for its Great Mosque and libraries", "ar": "قرطبة — قلب الأندلس، اشتهرت بمسجدها الكبير ومكتباتها", "fr": "Cœur d'Al-Andalus, célèbre pour sa Grande Mosquée et ses bibliothèques"}},
        {"word": "Jerusalem", "hint": {"en": "Al-Quds — third holiest city in Islam, site of Al-Aqsa Mosque", "ar": "القدس — ثالث أقدس مدينة في الإسلام، موقع المسجد الأقصى", "fr": "Al-Quds — troisième ville la plus sainte de l'islam, site de la mosquée Al-Aqsa"}},
    ],
    "Worship & Rituals": [
        {"word": "Salah", "hint": {"en": "The five daily ritual prayers, second pillar of Islam", "ar": "الصلوات الخمس اليومية، الركن الثاني من أركان الإسلام", "fr": "Les cinq prières rituelles quotidiennes, deuxième pilier de l'islam"}},
        {"word": "Zakat", "hint": {"en": "Obligatory charity, the third pillar of Islam", "ar": "الزكاة، الركن الثالث من أركان الإسلام", "fr": "L'aumône obligatoire, le troisième pilier de l'islam"}},
        {"word": "Sawm", "hint": {"en": "Fasting during Ramadan, the fourth pillar of Islam", "ar": "الصيام في رمضان، الركن الرابع من أركان الإسلام", "fr": "Le jeûne pendant le Ramadan, le quatrième pilier de l'islam"}},
        {"word": "Hajj", "hint": {"en": "The annual pilgrimage to Mecca, the fifth pillar of Islam", "ar": "الحج السنوي إلى مكة، الركن الخامس من أركان الإسلام", "fr": "Le pèlerinage annuel à La Mecque, le cinquième pilier de l'islam"}},
        {"word": "Shahada", "hint": {"en": "The declaration of faith, the first pillar of Islam", "ar": "الشهادة، الركن الأول من أركان الإسلام", "fr": "La déclaration de foi, le premier pilier de l'islam"}},
        {"word": "Wudu", "hint": {"en": "Ritual ablution with water before prayer", "ar": "الوضوء — الطهارة بالماء قبل الصلاة", "fr": "L'ablution rituelle avec de l'eau avant la prière"}},
        {"word": "Adhan", "hint": {"en": "The call to prayer announced five times daily", "ar": "الأذان — النداء للصلاة خمس مرات يومياً", "fr": "L'appel à la prière annoncé cinq fois par jour"}},
        {"word": "Iqamah", "hint": {"en": "The second call just before congregational prayer starts", "ar": "الإقامة — النداء الثاني قبل بدء صلاة الجماعة", "fr": "Le second appel juste avant le début de la prière en congrégation"}},
        {"word": "Qiyam", "hint": {"en": "Standing position in prayer, also refers to night prayer", "ar": "القيام — وضعية الوقوف في الصلاة، يشير أيضاً لصلاة الليل", "fr": "La position debout dans la prière, désigne aussi la prière nocturne"}},
        {"word": "Sujud", "hint": {"en": "Prostration — placing the forehead on the ground in prayer", "ar": "السجود — وضع الجبهة على الأرض في الصلاة", "fr": "La prosternation — poser le front au sol dans la prière"}},
        {"word": "Ruku", "hint": {"en": "Bowing position in prayer with hands on knees", "ar": "الركوع — الانحناء في الصلاة مع وضع اليدين على الركبتين", "fr": "La position inclinée dans la prière avec les mains sur les genoux"}},
        {"word": "Tashahhud", "hint": {"en": "The testimony recited while sitting in prayer", "ar": "التشهد — الشهادة التي تُقرأ أثناء الجلوس في الصلاة", "fr": "Le témoignage récité en position assise dans la prière"}},
        {"word": "Tasleem", "hint": {"en": "The greeting of peace that concludes the prayer", "ar": "التسليم — تحية السلام التي تختتم الصلاة", "fr": "La salutation de paix qui conclut la prière"}},
        {"word": "Takbir", "hint": {"en": "Saying 'Allahu Akbar' — God is the Greatest", "ar": "التكبير — قول 'الله أكبر'", "fr": "Dire 'Allahu Akbar' — Dieu est le Plus Grand"}},
        {"word": "Tahmid", "hint": {"en": "Saying 'Alhamdulillah' — Praise be to God", "ar": "التحميد — قول 'الحمد لله'", "fr": "Dire 'Alhamdulillah' — Louange à Dieu"}},
        {"word": "Tasbih", "hint": {"en": "Glorification of God by saying 'SubhanAllah'", "ar": "التسبيح — تمجيد الله بقول 'سبحان الله'", "fr": "La glorification de Dieu en disant 'SubhanAllah'"}},
        {"word": "Istighfar", "hint": {"en": "Seeking forgiveness from God by saying 'Astaghfirullah'", "ar": "الاستغفار — طلب المغفرة من الله بقول 'أستغفر الله'", "fr": "Demander pardon à Dieu en disant 'Astaghfirullah'"}},
        {"word": "Tawaf", "hint": {"en": "Circling the Kaaba seven times during Hajj or Umrah", "ar": "الطواف — الدوران حول الكعبة سبع مرات في الحج أو العمرة", "fr": "Faire sept tours autour de la Kaaba pendant le Hajj ou la Omra"}},
        {"word": "Sai", "hint": {"en": "Walking seven times between the hills of Safa and Marwa", "ar": "السعي — المشي سبع مرات بين الصفا والمروة", "fr": "Marcher sept fois entre les collines de Safa et Marwa"}},
        {"word": "Ihram", "hint": {"en": "The sacred state and white garments worn during Hajj or Umrah", "ar": "الإحرام — الحالة المقدسة واللباس الأبيض في الحج أو العمرة", "fr": "L'état sacré et les vêtements blancs portés pendant le Hajj ou la Omra"}},
    ],
    "Islamic Values": [
        {"word": "Tawakkul", "hint": {"en": "Complete trust and reliance in God's plan", "ar": "التوكل — الاعتماد الكامل على الله والثقة بتدبيره", "fr": "La confiance totale en le plan de Dieu"}},
        {"word": "Sabr", "hint": {"en": "Patience and perseverance through hardship", "ar": "الصبر — التحمل والمثابرة في مواجهة الشدائد", "fr": "La patience et la persévérance face aux épreuves"}},
        {"word": "Shukr", "hint": {"en": "Gratitude to Allah for His blessings", "ar": "الشكر — الامتنان لله على نعمه", "fr": "La gratitude envers Allah pour Ses bienfaits"}},
        {"word": "Taqwa", "hint": {"en": "God-consciousness and piety in all aspects of life", "ar": "التقوى — الوعي بالله والورع في جميع جوانب الحياة", "fr": "La conscience de Dieu et la piété dans tous les aspects de la vie"}},
        {"word": "Ihsan", "hint": {"en": "Excellence in worship — to worship God as if you see Him", "ar": "الإحسان — أن تعبد الله كأنك تراه", "fr": "L'excellence dans l'adoration — adorer Dieu comme si tu Le voyais"}},
        {"word": "Iman", "hint": {"en": "Faith — belief in God, angels, books, prophets, Last Day, and decree", "ar": "الإيمان — التصديق بالله وملائكته وكتبه ورسله واليوم الآخر والقدر", "fr": "La foi — croyance en Dieu, Ses anges, Ses livres, Ses prophètes, le Jour dernier et le destin"}},
        {"word": "Adl", "hint": {"en": "Justice and fairness, a fundamental principle in Islam", "ar": "العدل — العدالة والإنصاف، مبدأ أساسي في الإسلام", "fr": "La justice et l'équité, un principe fondamental en islam"}},
        {"word": "Rahma", "hint": {"en": "Mercy and compassion, a core attribute of Allah", "ar": "الرحمة — صفة أساسية من صفات الله", "fr": "La miséricorde et la compassion, un attribut fondamental d'Allah"}},
        {"word": "Hikmah", "hint": {"en": "Wisdom — the ability to apply knowledge with insight and judgment", "ar": "الحكمة — القدرة على تطبيق المعرفة بتبصر وحسن تقدير", "fr": "La sagesse — la capacité d'appliquer la connaissance avec discernement"}},
        {"word": "Ilm", "hint": {"en": "Knowledge — seeking it is an obligation upon every Muslim", "ar": "العلم — طلبه فريضة على كل مسلم", "fr": "La connaissance — la rechercher est une obligation pour tout musulman"}},
        {"word": "Amanah", "hint": {"en": "Trustworthiness and fulfilling responsibilities entrusted to you", "ar": "الأمانة — الثقة والوفاء بالمسؤوليات الموكلة إليك", "fr": "La fiabilité et l'accomplissement des responsabilités qui vous sont confiées"}},
        {"word": "Sidq", "hint": {"en": "Truthfulness and sincerity in speech and action", "ar": "الصدق — الحقيقة والإخلاص في القول والفعل", "fr": "La véracité et la sincérité en parole et en acte"}},
        {"word": "Haya", "hint": {"en": "Modesty and shyness — a branch of faith", "ar": "الحياء — شعبة من شعب الإيمان", "fr": "La pudeur et la modestie — une branche de la foi"}},
        {"word": "Tawbah", "hint": {"en": "Repentance — turning back to God after sin", "ar": "التوبة — الرجوع إلى الله بعد الذنب", "fr": "Le repentir — revenir à Dieu après le péché"}},
        {"word": "Ikhlas", "hint": {"en": "Sincerity — doing deeds purely for the sake of Allah", "ar": "الإخلاص — العمل خالصاً لوجه الله", "fr": "La sincérité — accomplir les actes uniquement pour l'amour d'Allah"}},
        {"word": "Birr", "hint": {"en": "Righteousness and goodness in all dealings", "ar": "البر — الصلاح والإحسان في جميع المعاملات", "fr": "La droiture et la bonté dans toutes les relations"}},
        {"word": "Husn", "hint": {"en": "Beauty and goodness, especially in character and conduct", "ar": "الحُسن — الجمال والطيب، خاصة في الأخلاق والسلوك", "fr": "La beauté et la bonté, surtout dans le caractère et la conduite"}},
        {"word": "Khushu", "hint": {"en": "Deep humility and focus in prayer and worship", "ar": "الخشوع — التواضع العميق والتركيز في الصلاة والعبادة", "fr": "L'humilité profonde et la concentration dans la prière et l'adoration"}},
        {"word": "Wara", "hint": {"en": "Scrupulousness — avoiding anything doubtful or suspicious", "ar": "الورع — تجنب كل ما هو مشبوه أو مشكوك فيه", "fr": "Le scrupule — éviter tout ce qui est douteux ou suspect"}},
        {"word": "Zuhd", "hint": {"en": "Asceticism — detachment from worldly pleasures for God's sake", "ar": "الزهد — الإعراض عن متع الدنيا في سبيل الله", "fr": "L'ascétisme — le détachement des plaisirs mondains pour l'amour de Dieu"}},
    ],
    "Islamic Sciences": [
        {"word": "Fiqh", "hint": {"en": "Islamic jurisprudence — understanding of religious laws and rulings", "ar": "الفقه — فهم الأحكام والتشريعات الدينية", "fr": "La jurisprudence islamique — compréhension des lois et jugements religieux"}},
        {"word": "Hadith", "hint": {"en": "The study of prophetic traditions and their chains of narration", "ar": "علم الحديث — دراسة الأحاديث النبوية وأسانيدها", "fr": "L'étude des traditions prophétiques et de leurs chaînes de narration"}},
        {"word": "Tafsir", "hint": {"en": "The science of Quranic interpretation and commentary", "ar": "علم التفسير — شرح وتأويل القرآن الكريم", "fr": "La science de l'interprétation et du commentaire coranique"}},
        {"word": "Aqeedah", "hint": {"en": "Islamic creed and theology — the study of core beliefs", "ar": "العقيدة — دراسة أصول الإيمان والمعتقدات", "fr": "Le credo et la théologie islamique — l'étude des croyances fondamentales"}},
        {"word": "Usul", "hint": {"en": "Principles of Islamic jurisprudence — methodology for deriving rulings", "ar": "أصول الفقه — منهجية استنباط الأحكام الشرعية", "fr": "Les principes de la jurisprudence islamique — méthodologie d'extraction des jugements"}},
        {"word": "Seerah", "hint": {"en": "The biographical study of Prophet Muhammad's life", "ar": "السيرة النبوية — دراسة حياة النبي محمد", "fr": "L'étude biographique de la vie du Prophète Muhammad"}},
        {"word": "Tajweed", "hint": {"en": "The science of correct Quran recitation and pronunciation", "ar": "علم التجويد — قواعد التلاوة الصحيحة للقرآن", "fr": "La science de la récitation et de la prononciation correctes du Coran"}},
        {"word": "Nahw", "hint": {"en": "Arabic grammar — essential for understanding the Quran", "ar": "النحو — القواعد العربية الضرورية لفهم القرآن", "fr": "La grammaire arabe — essentielle pour comprendre le Coran"}},
        {"word": "Sarf", "hint": {"en": "Arabic morphology — the study of word forms and patterns", "ar": "الصرف — دراسة أوزان الكلمات وأبنيتها", "fr": "La morphologie arabe — l'étude des formes et structures des mots"}},
        {"word": "Balagha", "hint": {"en": "Arabic rhetoric and eloquence, key to Quranic literary analysis", "ar": "البلاغة — علم الفصاحة العربية، مفتاح التحليل الأدبي للقرآن", "fr": "La rhétorique et l'éloquence arabes, clé de l'analyse littéraire coranique"}},
        {"word": "Mantiq", "hint": {"en": "Islamic logic — the science of correct reasoning", "ar": "المنطق — علم التفكير الصحيح", "fr": "La logique islamique — la science du raisonnement correct"}},
        {"word": "Falsafa", "hint": {"en": "Islamic philosophy — synthesis of Greek philosophy with Islamic thought", "ar": "الفلسفة الإسلامية — دمج الفلسفة اليونانية مع الفكر الإسلامي", "fr": "La philosophie islamique — synthèse de la philosophie grecque et de la pensée islamique"}},
        {"word": "Kalam", "hint": {"en": "Islamic theology — rational discourse about God's attributes and nature", "ar": "علم الكلام — الخطاب العقلاني حول صفات الله وطبيعته", "fr": "La théologie islamique — discours rationnel sur les attributs et la nature de Dieu"}},
        {"word": "Tasawwuf", "hint": {"en": "Islamic spirituality and mysticism — the inner dimension of worship", "ar": "التصوف — الروحانية الإسلامية والبعد الباطني للعبادة", "fr": "La spiritualité et le mysticisme islamiques — la dimension intérieure de l'adoration"}},
        {"word": "Ijtihad", "hint": {"en": "Independent scholarly reasoning to derive new legal rulings", "ar": "الاجتهاد — التفكير العلمي المستقل لاستنباط أحكام شرعية جديدة", "fr": "Le raisonnement savant indépendant pour dériver de nouveaux jugements juridiques"}},
    ],
}


# ── Helper functions ────────────────────────────────────────────────────────


def create_random_public_id() -> str:
    """Create a random 5-character public ID for rooms."""
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(5))


async def create_test_users(session: AsyncSession) -> list[User]:
    """Create the three fixed test users with hashed passwords.

    Returns:
        List of created User objects.
    """
    users = []
    for user_data in TEST_USERS:
        user = User(
            id=uuid4(),
            username=user_data["username"],
            email_address=user_data["email_address"],
            password=get_password_hash(user_data["password"]),
            country=user_data["country"],
            email_verified=True,
            bio=user_data.get("bio"),
        )
        session.add(user)
        users.append(user)

    await session.commit()
    for user in users:
        await session.refresh(user)

    print(f"  Created {len(users)} test users:")
    for u in TEST_USERS:
        print(f"    - {u['email_address']} / {u['password']}")

    return users


async def create_random_users(session: AsyncSession, count: int) -> list[User]:
    """Create additional random users with hashed passwords.

    Args:
        session: The database session.
        count: Number of random users to create.

    Returns:
        List of created User objects.
    """
    import pycountry

    country_codes = [c.alpha_3 for c in pycountry.countries]
    users = []

    for _ in range(count):
        user = User(
            id=uuid4(),
            username=fake.user_name(),
            email_address=fake.email(),
            password=get_password_hash(fake.password()),
            country=random.choice(country_codes),
        )
        session.add(user)
        users.append(user)

    await session.commit()
    for user in users:
        await session.refresh(user)

    print(f"  Created {count} random users")
    return users


async def create_rooms(session: AsyncSession, users: list[User], count: int = 5) -> list[Room]:
    """Create rooms with various statuses.

    Args:
        session: The database session.
        users: List of users who can own rooms.
        count: Number of rooms to create.

    Returns:
        List of created Room objects.
    """
    rooms = []
    for i in range(count):
        owner = random.choice(users)
        room = Room(
            id=uuid4(),
            public_id=create_random_public_id(),
            owner_id=owner.id,
            status=random.choice(list(RoomStatus)),
            password="".join(random.choice(string.digits) for _ in range(4)),
            type=random.choice(list(RoomType)),
            created_at=fake.date_time_between(start_date="-30d", end_date="now"),
        )
        session.add(room)
        rooms.append(room)

    await session.commit()
    for room in rooms:
        await session.refresh(room)

    print(f"  Created {count} rooms")
    return rooms


async def create_games(
    session: AsyncSession, users: list[User], count: int = 30
) -> list[Game]:
    """Create games with various types and configurations.

    Args:
        session: The database session.
        users: List of users who can participate in games.
        count: Number of games to create.

    Returns:
        List of created Game objects.
    """
    games = []
    for _ in range(count):
        user = random.choice(users)
        start_time = fake.date_time_between(start_date="-30d", end_date="now")
        has_ended = random.choice([True, False])
        end_time = start_time + timedelta(minutes=random.randint(5, 45)) if has_ended else None
        game_type = random.choice(list(GameType))
        num_players = random.randint(3, 12) if game_type == GameType.UNDERCOVER else random.randint(4, 10)

        game = Game(
            id=uuid4(),
            user_id=user.id,
            start_time=start_time,
            end_time=end_time,
            number_of_players=num_players,
            type=game_type,
            game_configurations={
                "game_type": game_type.value,
                "created_by": str(user.id),
            },
        )
        session.add(game)
        games.append(game)

    await session.commit()
    for game in games:
        await session.refresh(game)

    print(f"  Created {count} games")
    return games


async def seed_undercover_words(session: AsyncSession) -> dict[str, Word]:
    """Seed all Undercover words and return a mapping of word text to Word object.

    Args:
        session: The database session.

    Returns:
        Dictionary mapping word text to Word objects.
    """
    word_map: dict[str, Word] = {}
    new_count = 0

    for word_data in UNDERCOVER_WORDS:
        existing = (
            await session.exec(select(Word).where(Word.word == word_data["word"]))
        ).first()
        if existing:
            word_map[word_data["word"]] = existing
            continue
        word = Word(
            id=uuid4(),
            word=word_data["word"],
            category=word_data["category"],
            short_description=word_data["short_description"],
            long_description=word_data["long_description"],
            hint=word_data.get("hint", {"en": word_data["long_description"]}),
        )
        session.add(word)
        word_map[word_data["word"]] = word
        new_count += 1

    await session.commit()
    for word in word_map.values():
        await session.refresh(word)

    print(f"  Seeded {new_count} new Undercover words ({len(word_map)} total)")
    return word_map


async def seed_undercover_pairs(session: AsyncSession, word_map: dict[str, Word]) -> None:
    """Seed Undercover word pairs.

    Args:
        session: The database session.
        word_map: Dictionary mapping word text to Word objects.
    """
    count = 0
    for word1_text, word2_text in UNDERCOVER_WORD_PAIRS:
        w1 = word_map.get(word1_text)
        w2 = word_map.get(word2_text)
        if w1 is None or w2 is None:
            print(f"    Warning: Skipping pair ({word1_text}, {word2_text}) - word not found")
            continue

        existing = (
            await session.exec(
                select(TermPair).where(TermPair.word1_id == w1.id, TermPair.word2_id == w2.id)
            )
        ).first()
        if existing:
            continue

        pair = TermPair(
            id=uuid4(),
            word1_id=w1.id,
            word2_id=w2.id,
        )
        session.add(pair)
        count += 1

    await session.commit()
    print(f"  Seeded {count} new Undercover word pairs")


async def seed_codenames_words(session: AsyncSession) -> None:
    """Seed Codenames word packs and words.

    Args:
        session: The database session.
    """
    total_words = 0
    new_packs = 0

    for pack_name, words in CODENAMES_WORD_PACKS.items():
        existing_pack = (
            await session.exec(select(CodenamesWordPack).where(CodenamesWordPack.name == pack_name))
        ).first()
        if existing_pack:
            pack = existing_pack
        else:
            pack = CodenamesWordPack(
                id=uuid4(),
                name=pack_name,
                description=f"Islamic terms related to {pack_name.lower()}",
                is_active=True,
            )
            session.add(pack)
            await session.flush()
            new_packs += 1

        for word_data in words:
            existing_word = (
                await session.exec(
                    select(CodenamesWord).where(
                        CodenamesWord.word == word_data["word"],
                        CodenamesWord.word_pack_id == pack.id,
                    )
                )
            ).first()
            if existing_word:
                continue
            word = CodenamesWord(
                id=uuid4(),
                word=word_data["word"],
                hint=word_data.get("hint"),
                word_pack_id=pack.id,
            )
            session.add(word)
            total_words += 1

    await session.commit()
    print(f"  Seeded {new_packs} new Codenames packs, {total_words} new words")


QUIZ_WORDS: list[dict] = [
    # === Prophets (~25) ===
    {
        "word_en": "Ibrahim / Abraham",
        "word_ar": "إبراهيم",
        "word_fr": "Ibrahim / Abraham",
        "accepted_answers": {"en": ["Ibrahim", "Abraham"], "ar": ["إبراهيم", "ابراهيم"], "fr": ["Ibrahim", "Abraham"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "A great patriarch", "ar": "أب عظيم", "fr": "Un grand patriarche"},
            "2": {"en": "Known as the friend of Allah", "ar": "خليل الله", "fr": "Connu comme l'ami d'Allah"},
            "3": {"en": "He built the Kaaba", "ar": "بنى الكعبة", "fr": "Il a construit la Kaaba"},
            "4": {"en": "Father of Ismail and Ishaq", "ar": "والد إسماعيل وإسحاق", "fr": "Père d'Ismail et Ishaq"},
            "5": {"en": "He was thrown into fire", "ar": "ألقي في النار", "fr": "Il a été jeté dans le feu"},
            "6": {"en": "Khalil Allah", "ar": "خليل الله", "fr": "Khalil Allah"},
        },
        "explanation": {
            "en": "Ibrahim (Abraham) is one of the greatest prophets in Islam, known as the 'Friend of Allah' (Khalilullah). He built the Kaaba in Makkah with his son Ismail and is considered the father of monotheism.",
            "ar": "إبراهيم عليه السلام من أعظم الأنبياء في الإسلام، يُلقب بخليل الله. بنى الكعبة في مكة مع ابنه إسماعيل ويُعتبر أبا التوحيد.",
            "fr": "Ibrahim (Abraham) est l'un des plus grands prophètes de l'Islam, connu comme 'l'Ami d'Allah' (Khalilullah). Il a construit la Kaaba à La Mecque avec son fils Ismaïl et est considéré comme le père du monothéisme.",
        },
    },
    {
        "word_en": "Musa / Moses",
        "word_ar": "موسى",
        "word_fr": "Moussa / Moïse",
        "accepted_answers": {"en": ["Musa", "Moses"], "ar": ["موسى"], "fr": ["Moïse", "Moussa"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "One of the greatest messengers", "ar": "من أولي العزم", "fr": "Un des plus grands messagers"},
            "2": {"en": "Spoke directly to Allah", "ar": "كلّم الله مباشرة", "fr": "A parlé directement à Allah"},
            "3": {"en": "Led his people out of Egypt", "ar": "قاد قومه من مصر", "fr": "A mené son peuple hors d'Égypte"},
            "4": {"en": "Received the Torah", "ar": "تلقى التوراة", "fr": "A reçu la Torah"},
            "5": {"en": "His staff turned into a snake", "ar": "عصاه تحولت إلى حية", "fr": "Son bâton s'est transformé en serpent"},
            "6": {"en": "Kalim Allah", "ar": "كليم الله", "fr": "Kalim Allah"},
        },
        "explanation": {
            "en": "Musa (Moses) is one of the five greatest prophets (Ulul Azm) in Islam. He confronted Pharaoh, parted the sea by Allah's command, and received the Torah on Mount Sinai. He is called Kalim Allah — the one who spoke directly to God.",
            "ar": "موسى عليه السلام من أولي العزم من الرسل. واجه فرعون وشق البحر بأمر الله وتلقى التوراة على جبل سيناء. يُلقب بكليم الله لأنه كلّم الله مباشرة.",
            "fr": "Moussa (Moïse) est l'un des cinq plus grands prophètes (Ouloul Azm) de l'Islam. Il a affronté Pharaon, fendu la mer par l'ordre d'Allah et reçu la Torah sur le mont Sinaï. Il est appelé Kalim Allah — celui qui a parlé directement à Dieu.",
        },
    },
    {
        "word_en": "Isa / Jesus",
        "word_ar": "عيسى",
        "word_fr": "Issa / Jésus",
        "accepted_answers": {"en": ["Isa", "Jesus"], "ar": ["عيسى"], "fr": ["Jésus", "Issa"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Born miraculously", "ar": "ولد معجزة", "fr": "Né miraculeusement"},
            "2": {"en": "His mother is mentioned by name in the Quran", "ar": "أمه مذكورة بالاسم في القرآن", "fr": "Sa mère est mentionnée par nom dans le Coran"},
            "3": {"en": "Could heal the sick by Allah's permission", "ar": "كان يشفي المرضى بإذن الله", "fr": "Pouvait guérir les malades par la permission d'Allah"},
            "4": {"en": "Spoke as a baby in the cradle", "ar": "تكلم في المهد", "fr": "A parlé bébé dans le berceau"},
            "5": {"en": "He was raised to the heavens", "ar": "رُفع إلى السماء", "fr": "Il a été élevé aux cieux"},
            "6": {"en": "Son of Maryam", "ar": "ابن مريم", "fr": "Fils de Maryam"},
        },
        "explanation": {
            "en": "Isa (Jesus) is a revered prophet in Islam, born miraculously to Maryam (Mary) without a father. He performed miracles by Allah's permission including healing the sick, and spoke as a newborn in the cradle to defend his mother's honor.",
            "ar": "عيسى عليه السلام نبي مُبجّل في الإسلام، وُلد بمعجزة لمريم عليها السلام بدون أب. أجرى معجزات بإذن الله منها شفاء المرضى، وتكلم في المهد صبياً دفاعاً عن شرف أمه.",
            "fr": "Issa (Jésus) est un prophète révéré en Islam, né miraculeusement de Maryam (Marie) sans père. Il a accompli des miracles par la permission d'Allah, dont la guérison des malades, et a parlé au berceau pour défendre l'honneur de sa mère.",
        },
    },
    {
        "word_en": "Nuh / Noah",
        "word_ar": "نوح",
        "word_fr": "Nouh / Noé",
        "accepted_answers": {"en": ["Nuh", "Noah"], "ar": ["نوح"], "fr": ["Noé", "Nouh"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Lived for a very long time", "ar": "عاش طويلاً جداً", "fr": "A vécu très longtemps"},
            "2": {"en": "Built something massive by command of Allah", "ar": "بنى شيئاً عظيماً بأمر الله", "fr": "A construit quelque chose de massif par ordre d'Allah"},
            "3": {"en": "A great flood came", "ar": "جاء طوفان عظيم", "fr": "Un grand déluge est venu"},
            "4": {"en": "Preached for 950 years", "ar": "دعا 950 سنة", "fr": "A prêché pendant 950 ans"},
            "5": {"en": "His son refused to board", "ar": "رفض ابنه أن يركب", "fr": "Son fils a refusé de monter"},
            "6": {"en": "The Ark builder", "ar": "باني السفينة", "fr": "Le constructeur de l'Arche"},
        },
        "explanation": {
            "en": "Nuh (Noah) is one of the five greatest prophets in Islam. He preached monotheism for 950 years and built the Ark by Allah's command to save the believers and pairs of animals from the Great Flood.",
            "ar": "نوح عليه السلام من أولي العزم من الرسل. دعا قومه للتوحيد 950 سنة وبنى السفينة بأمر الله لإنقاذ المؤمنين وأزواج الحيوانات من الطوفان العظيم.",
            "fr": "Noé (Nuh) est l'un des cinq plus grands prophètes de l'Islam. Il a prêché le monothéisme pendant 950 ans et construit l'Arche sur ordre d'Allah pour sauver les croyants et les couples d'animaux du Déluge.",
        },
    },
    {
        "word_en": "Yusuf / Joseph",
        "word_ar": "يوسف",
        "word_fr": "Youssef / Joseph",
        "accepted_answers": {"en": ["Yusuf", "Joseph"], "ar": ["يوسف"], "fr": ["Joseph", "Youssef"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Known for his extraordinary beauty", "ar": "اشتهر بجماله الفائق", "fr": "Connu pour sa beauté extraordinaire"},
            "2": {"en": "Had a dream about celestial bodies", "ar": "رأى حلماً عن أجرام سماوية", "fr": "A eu un rêve sur des corps célestes"},
            "3": {"en": "Was thrown into a well by his brothers", "ar": "ألقاه إخوته في البئر", "fr": "A été jeté dans un puits par ses frères"},
            "4": {"en": "Became a minister in Egypt", "ar": "أصبح وزيراً في مصر", "fr": "Est devenu ministre en Égypte"},
            "5": {"en": "Could interpret dreams", "ar": "كان يفسر الأحلام", "fr": "Pouvait interpréter les rêves"},
            "6": {"en": "His story is called the best of stories", "ar": "قصته أحسن القصص", "fr": "Son histoire est la meilleure des histoires"},
        },
        "explanation": {
            "en": "Yusuf (Joseph) is known for his extraordinary beauty and his story of patience through betrayal, slavery, and imprisonment. His story in Surah Yusuf is called 'the best of stories' (Ahsan al-Qasas) in the Quran.",
            "ar": "يوسف عليه السلام يُعرف بجماله الاستثنائي وقصة صبره عبر الخيانة والعبودية والسجن. قصته في سورة يوسف توصف بأحسن القصص في القرآن.",
            "fr": "Youssouf (Joseph) est connu pour sa beauté extraordinaire et son histoire de patience à travers la trahison, l'esclavage et l'emprisonnement. Son histoire dans la sourate Youssouf est appelée 'le meilleur des récits' (Ahsan al-Qasas) dans le Coran.",
        },
    },
    {
        "word_en": "Dawud / David",
        "word_ar": "داود",
        "word_fr": "Daoud / David",
        "accepted_answers": {"en": ["Dawud", "David"], "ar": ["داود", "داوود"], "fr": ["David", "Daoud"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "A prophet who was also a king", "ar": "نبي وملك", "fr": "Un prophète qui était aussi roi"},
            "2": {"en": "Given a beautiful voice", "ar": "أُعطي صوتاً جميلاً", "fr": "Doté d'une belle voix"},
            "3": {"en": "Mountains and birds glorified Allah with him", "ar": "سبّحت معه الجبال والطيور", "fr": "Les montagnes et les oiseaux glorifiaient Allah avec lui"},
            "4": {"en": "Received the Zabur", "ar": "تلقى الزبور", "fr": "A reçu le Zabour"},
            "5": {"en": "Defeated a giant warrior", "ar": "هزم محارباً عملاقاً", "fr": "A vaincu un guerrier géant"},
            "6": {"en": "Father of Sulayman", "ar": "والد سليمان", "fr": "Père de Sulayman"},
        },
        "explanation": {
            "en": "Dawud (David) was both a prophet and a king of Israel. Allah gave him the Zabur (Psalms) and blessed him with a beautiful voice that made mountains and birds glorify Allah alongside him.",
            "ar": "داود عليه السلام كان نبياً وملكاً لبني إسرائيل. آتاه الله الزبور وباركه بصوت جميل جعل الجبال والطيور تسبح الله معه.",
            "fr": "Dawoud (David) était à la fois prophète et roi d'Israël. Allah lui a donné le Zabour (Psaumes) et l'a béni d'une belle voix qui faisait que les montagnes et les oiseaux glorifiaient Allah avec lui.",
        },
    },
    {
        "word_en": "Sulayman / Solomon",
        "word_ar": "سليمان",
        "word_fr": "Soulayman / Salomon",
        "accepted_answers": {"en": ["Sulayman", "Solomon"], "ar": ["سليمان"], "fr": ["Salomon", "Soulayman"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Given a kingdom unlike any other", "ar": "أُعطي ملكاً لا مثيل له", "fr": "Reçu un royaume sans pareil"},
            "2": {"en": "Could understand the language of animals", "ar": "كان يفهم لغة الحيوانات", "fr": "Pouvait comprendre le langage des animaux"},
            "3": {"en": "Commanded the jinn", "ar": "كان يأمر الجن", "fr": "Commandait les djinns"},
            "4": {"en": "The wind was at his service", "ar": "الريح كانت مسخرة له", "fr": "Le vent était à son service"},
            "5": {"en": "An ant warned its colony about his army", "ar": "حذرت نملة قومها من جيشه", "fr": "Une fourmi a averti sa colonie de son armée"},
            "6": {"en": "Son of Dawud", "ar": "ابن داود", "fr": "Fils de Dawud"},
        },
        "explanation": {
            "en": "Sulayman (Solomon) was a prophet-king who was given dominion over humans, jinn, animals, and the wind. He could understand the language of birds and ants, and he built a magnificent temple with the help of jinn.",
            "ar": "سليمان عليه السلام كان نبياً وملكاً سُخّر له الإنس والجن والحيوانات والرياح. كان يفهم لغة الطيور والنمل وبنى معبداً عظيماً بمساعدة الجن.",
            "fr": "Soulaymane (Salomon) était un prophète-roi à qui Allah a donné pouvoir sur les humains, les djinns, les animaux et le vent. Il comprenait le langage des oiseaux et des fourmis et a bâti un temple magnifique avec l'aide des djinns.",
        },
    },
    {
        "word_en": "Ayyub / Job",
        "word_ar": "أيوب",
        "word_fr": "Ayyoub / Job",
        "accepted_answers": {"en": ["Ayyub", "Job"], "ar": ["أيوب", "ايوب"], "fr": ["Job", "Ayyoub"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Known for extraordinary patience", "ar": "اشتهر بصبره العظيم", "fr": "Connu pour sa patience extraordinaire"},
            "2": {"en": "Lost his wealth and health", "ar": "فقد ماله وصحته", "fr": "A perdu sa richesse et sa santé"},
            "3": {"en": "Tested severely by Allah", "ar": "ابتلاه الله ابتلاءً شديداً", "fr": "Éprouvé sévèrement par Allah"},
            "4": {"en": "Never complained despite suffering", "ar": "لم يشكُ رغم المعاناة", "fr": "N'a jamais se plaint malgré la souffrance"},
            "5": {"en": "Allah restored everything to him", "ar": "أعاد الله إليه كل شيء", "fr": "Allah lui a tout restitué"},
            "6": {"en": "Symbol of patience (sabr)", "ar": "رمز الصبر", "fr": "Symbole de patience (sabr)"},
        },
        "explanation": {
            "en": "Ayyub (Job) is the ultimate symbol of patience in Islam. He endured years of severe illness, loss of wealth, and loss of family, yet never complained to anyone but Allah. His patience was rewarded with full restoration.",
            "ar": "أيوب عليه السلام رمز الصبر في الإسلام. تحمّل سنوات من المرض الشديد وفقدان المال والأهل ولم يشكُ إلا لله. كوفئ صبره باسترداد كل شيء.",
            "fr": "Ayyoub (Job) est le symbole ultime de la patience en Islam. Il a enduré des années de maladie grave, la perte de ses biens et de sa famille, sans jamais se plaindre qu'à Allah. Sa patience fut récompensée par une restauration complète.",
        },
    },
    {
        "word_en": "Yunus / Jonah",
        "word_ar": "يونس",
        "word_fr": "Younous / Jonas",
        "accepted_answers": {"en": ["Yunus", "Jonah"], "ar": ["يونس"], "fr": ["Jonas", "Younous"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Left his people in frustration", "ar": "ترك قومه غاضباً", "fr": "A quitté son peuple frustré"},
            "2": {"en": "Boarded a ship", "ar": "ركب سفينة", "fr": "A embarqué sur un navire"},
            "3": {"en": "Was swallowed by a large creature", "ar": "ابتلعه مخلوق كبير", "fr": "A été avalé par une grande créature"},
            "4": {"en": "Made dua in layers of darkness", "ar": "دعا في ظلمات", "fr": "A fait dua dans des couches de ténèbres"},
            "5": {"en": "La ilaha illa anta subhanaka inni kuntu min az-zalimin", "ar": "لا إله إلا أنت سبحانك إني كنت من الظالمين", "fr": "La ilaha illa anta subhanaka inni kuntu min az-zalimin"},
            "6": {"en": "The companion of the whale", "ar": "صاحب الحوت", "fr": "Le compagnon de la baleine"},
        },
        "explanation": {
            "en": "Yunus (Jonah) is known for being swallowed by a great whale after leaving his people without Allah's permission. Inside the whale's belly, he made the famous supplication that led to his miraculous rescue.",
            "ar": "يونس عليه السلام يُعرف بأنه ابتلعه حوت عظيم بعد أن ترك قومه دون إذن الله. في بطن الحوت دعا بالدعاء المشهور الذي أدى إلى إنقاذه بمعجزة.",
            "fr": "Younous (Jonas) est connu pour avoir été avalé par une grande baleine après avoir quitté son peuple sans la permission d'Allah. Dans le ventre de la baleine, il fit la célèbre invocation qui mena à son sauvetage miraculeux.",
        },
    },
    {
        "word_en": "Muhammad",
        "word_ar": "محمد",
        "word_fr": "Mohammed",
        "accepted_answers": {"en": ["Muhammad", "Mohammed", "Mohamed"], "ar": ["محمد"], "fr": ["Mohammed", "Muhammad", "Mohamed"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "The final messenger", "ar": "الرسول الأخير", "fr": "Le dernier messager"},
            "2": {"en": "Born in Makkah", "ar": "وُلد في مكة", "fr": "Né à La Mecque"},
            "3": {"en": "Received the Quran", "ar": "تلقى القرآن", "fr": "A reçu le Coran"},
            "4": {"en": "Made the Hijra to Madinah", "ar": "هاجر إلى المدينة", "fr": "A fait la Hijra vers Médine"},
            "5": {"en": "Sallallahu alayhi wa sallam", "ar": "صلى الله عليه وسلم", "fr": "Sallallahu alayhi wa sallam"},
            "6": {"en": "Seal of the Prophets", "ar": "خاتم الأنبياء", "fr": "Sceau des Prophètes"},
        },
        "explanation": {
            "en": "Muhammad (peace be upon him) is the final prophet and messenger of Allah, sent as a mercy to all of humanity. He received the Quran over 23 years and established the foundations of Islamic civilization in Madinah.",
            "ar": "محمد صلى الله عليه وسلم خاتم الأنبياء والمرسلين، أُرسل رحمة للعالمين. تلقى القرآن على مدى 23 سنة وأسس حضارة الإسلام في المدينة المنورة.",
            "fr": "Muhammad (paix et bénédictions sur lui) est le dernier prophète et messager d'Allah, envoyé comme miséricorde pour toute l'humanité. Il a reçu le Coran sur 23 ans et a établi les fondements de la civilisation islamique à Médine.",
        },
    },
    # === Companions (~15) ===
    {
        "word_en": "Abu Bakr",
        "word_ar": "أبو بكر",
        "word_fr": "Abou Bakr",
        "accepted_answers": {"en": ["Abu Bakr", "Abu Bakr As-Siddiq"], "ar": ["أبو بكر", "ابو بكر"], "fr": ["Abou Bakr"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "A very close friend of the Prophet", "ar": "صديق قريب جداً من النبي", "fr": "Un ami très proche du Prophète"},
            "2": {"en": "First among men to accept Islam", "ar": "أول الرجال إسلاماً", "fr": "Premier homme à accepter l'Islam"},
            "3": {"en": "Accompanied the Prophet during the Hijra", "ar": "رافق النبي في الهجرة", "fr": "A accompagné le Prophète pendant la Hijra"},
            "4": {"en": "Gave all his wealth for Islam", "ar": "أنفق كل ماله للإسلام", "fr": "A donné toute sa richesse pour l'Islam"},
            "5": {"en": "The first Caliph of Islam", "ar": "أول خليفة في الإسلام", "fr": "Le premier Calife de l'Islam"},
            "6": {"en": "As-Siddiq (The Truthful)", "ar": "الصديق", "fr": "As-Siddiq (Le Véridique)"},
        },
        "explanation": {
            "en": "Abu Bakr al-Siddiq was the Prophet's closest companion and the first adult male to embrace Islam. He became the first Caliph after the Prophet's death and is known for his unwavering faith and generosity.",
            "ar": "أبو بكر الصديق كان أقرب صحابي للنبي وأول رجل بالغ يعتنق الإسلام. أصبح أول خليفة بعد وفاة النبي ويُعرف بإيمانه الراسخ وكرمه.",
            "fr": "Abou Bakr al-Siddiq était le compagnon le plus proche du Prophète et le premier homme adulte à embrasser l'Islam. Il devint le premier calife après la mort du Prophète et est connu pour sa foi inébranlable et sa générosité.",
        },
    },
    {
        "word_en": "Umar",
        "word_ar": "عمر",
        "word_fr": "Omar",
        "accepted_answers": {"en": ["Umar", "Omar", "Umar ibn Al-Khattab"], "ar": ["عمر", "عمر بن الخطاب"], "fr": ["Omar"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Known for his strong sense of justice", "ar": "اشتهر بعدله", "fr": "Connu pour son sens de la justice"},
            "2": {"en": "His conversion strengthened the Muslims", "ar": "إسلامه قوّى المسلمين", "fr": "Sa conversion a renforcé les musulmans"},
            "3": {"en": "Established the Islamic calendar", "ar": "أسس التقويم الهجري", "fr": "A établi le calendrier islamique"},
            "4": {"en": "The second Caliph", "ar": "الخليفة الثاني", "fr": "Le deuxième Calife"},
            "5": {"en": "Conquered Jerusalem peacefully", "ar": "فتح القدس سلمياً", "fr": "A conquis Jérusalem pacifiquement"},
            "6": {"en": "Al-Faruq (The Distinguisher)", "ar": "الفاروق", "fr": "Al-Faruq (Le Distingueur)"},
        },
        "explanation": {
            "en": "Umar ibn al-Khattab was the second Caliph of Islam, known for his justice, strength, and administrative genius. His conversion to Islam was a turning point — the Prophet had prayed for either Umar or Abu Jahl to embrace the faith.",
            "ar": "عمر بن الخطاب الخليفة الثاني في الإسلام، يُعرف بعدله وقوته وعبقريته الإدارية. كان إسلامه نقطة تحول — دعا النبي أن يعز الله الإسلام بأحد العمرين.",
            "fr": "Omar ibn al-Khattab fut le deuxième calife de l'Islam, connu pour sa justice, sa force et son génie administratif. Sa conversion à l'Islam fut un tournant — le Prophète avait prié pour que l'un des deux Omar embrasse la foi.",
        },
    },
    {
        "word_en": "Khadijah",
        "word_ar": "خديجة",
        "word_fr": "Khadija",
        "accepted_answers": {"en": ["Khadijah", "Khadija"], "ar": ["خديجة"], "fr": ["Khadija", "Khadidja"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "A successful businesswoman", "ar": "سيدة أعمال ناجحة", "fr": "Une femme d'affaires prospère"},
            "2": {"en": "First person to accept Islam", "ar": "أول من أسلم", "fr": "Première personne à accepter l'Islam"},
            "3": {"en": "Was older than her husband", "ar": "كانت أكبر من زوجها سناً", "fr": "Était plus âgée que son mari"},
            "4": {"en": "Supported the Prophet during difficult times", "ar": "ساندت النبي في الأوقات الصعبة", "fr": "A soutenu le Prophète dans les moments difficiles"},
            "5": {"en": "Mother of Fatimah", "ar": "أم فاطمة", "fr": "Mère de Fatima"},
            "6": {"en": "First wife of the Prophet", "ar": "أول زوجات النبي", "fr": "Première épouse du Prophète"},
        },
        "explanation": {
            "en": "Khadijah bint Khuwaylid was the Prophet's first wife and the first person to accept Islam. She was a successful businesswoman who supported the Prophet emotionally and financially during the difficult early years of revelation.",
            "ar": "خديجة بنت خويلد كانت أول زوجات النبي وأول من آمن بالإسلام. كانت سيدة أعمال ناجحة دعمت النبي عاطفياً ومادياً خلال سنوات الوحي الأولى الصعبة.",
            "fr": "Khadija bint Khuwaylid était la première épouse du Prophète et la première personne à accepter l'Islam. C'était une femme d'affaires prospère qui a soutenu le Prophète émotionnellement et financièrement pendant les difficiles premières années de la révélation.",
        },
    },
    {
        "word_en": "Bilal",
        "word_ar": "بلال",
        "word_fr": "Bilal",
        "accepted_answers": {"en": ["Bilal", "Bilal ibn Rabah"], "ar": ["بلال", "بلال بن رباح"], "fr": ["Bilal"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Of Ethiopian origin", "ar": "من أصل حبشي", "fr": "D'origine éthiopienne"},
            "2": {"en": "Was severely tortured for his faith", "ar": "عُذّب بشدة بسبب إيمانه", "fr": "A été sévèrement torturé pour sa foi"},
            "3": {"en": "Said 'Ahad, Ahad' under persecution", "ar": "قال أحد أحد تحت التعذيب", "fr": "Disait 'Ahad, Ahad' sous la persécution"},
            "4": {"en": "Freed by Abu Bakr", "ar": "أعتقه أبو بكر", "fr": "Libéré par Abou Bakr"},
            "5": {"en": "Had a beautiful voice", "ar": "كان له صوت جميل", "fr": "Avait une belle voix"},
            "6": {"en": "The first muezzin of Islam", "ar": "أول مؤذن في الإسلام", "fr": "Le premier muezzin de l'Islam"},
        },
        "explanation": {
            "en": "Bilal ibn Rabah was an Abyssinian companion who became the first muezzin (caller to prayer) in Islam. He was tortured for his faith but remained steadfast, famously repeating 'Ahad, Ahad' (One, One) under persecution.",
            "ar": "بلال بن رباح صحابي حبشي أصبح أول مؤذن في الإسلام. عُذّب بسبب إيمانه لكنه ظل صامداً وكان يردد 'أحد أحد' تحت التعذيب.",
            "fr": "Bilal ibn Rabah était un compagnon abyssinien qui devint le premier muezzin (appelant à la prière) en Islam. Il fut torturé pour sa foi mais resta ferme, répétant célèbrement 'Ahad, Ahad' (Un, Un) sous la persécution.",
        },
    },
    {
        "word_en": "Ali",
        "word_ar": "علي",
        "word_fr": "Ali",
        "accepted_answers": {"en": ["Ali", "Ali ibn Abi Talib"], "ar": ["علي", "علي بن أبي طالب"], "fr": ["Ali"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Raised in the Prophet's household", "ar": "نشأ في بيت النبي", "fr": "Élevé dans la maison du Prophète"},
            "2": {"en": "Known for his bravery and knowledge", "ar": "اشتهر بشجاعته وعلمه", "fr": "Connu pour sa bravoure et son savoir"},
            "3": {"en": "Married the Prophet's daughter", "ar": "تزوج ابنة النبي", "fr": "A épousé la fille du Prophète"},
            "4": {"en": "Slept in the Prophet's bed during the Hijra", "ar": "نام في فراش النبي ليلة الهجرة", "fr": "A dormi dans le lit du Prophète pendant la Hijra"},
            "5": {"en": "The fourth Caliph", "ar": "الخليفة الرابع", "fr": "Le quatrième Calife"},
            "6": {"en": "The Gate of Knowledge", "ar": "باب العلم", "fr": "La Porte du Savoir"},
        },
        "explanation": {
            "en": "Ali ibn Abi Talib was the Prophet's cousin, son-in-law, and the fourth Caliph. Known as 'the Gate to the City of Knowledge,' he was the first young boy to accept Islam and was renowned for his bravery and wisdom.",
            "ar": "علي بن أبي طالب ابن عم النبي وصهره والخليفة الرابع. يُلقب بباب مدينة العلم، وكان أول صبي يعتنق الإسلام واشتهر بشجاعته وحكمته.",
            "fr": "Ali ibn Abi Talib était le cousin du Prophète, son gendre et le quatrième calife. Connu comme 'la Porte de la Cité du Savoir,' il fut le premier jeune garçon à accepter l'Islam et était renommé pour sa bravoure et sa sagesse.",
        },
    },
    # === Islamic Concepts (~20) ===
    {
        "word_en": "Tawhid",
        "word_ar": "توحيد",
        "word_fr": "Tawhid",
        "accepted_answers": {"en": ["Tawhid", "Tawheed", "Monotheism"], "ar": ["توحيد", "التوحيد"], "fr": ["Tawhid", "Monothéisme"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "The most fundamental concept in Islam", "ar": "أهم مفهوم في الإسلام", "fr": "Le concept le plus fondamental en Islam"},
            "2": {"en": "Related to the first pillar of Islam", "ar": "يتعلق بالركن الأول من الإسلام", "fr": "Lié au premier pilier de l'Islam"},
            "3": {"en": "La ilaha illa Allah expresses this", "ar": "لا إله إلا الله تعبر عنه", "fr": "La ilaha illa Allah l'exprime"},
            "4": {"en": "The belief in the absolute oneness of God", "ar": "الإيمان بوحدانية الله المطلقة", "fr": "La croyance en l'unicité absolue de Dieu"},
            "5": {"en": "Opposite of shirk", "ar": "عكس الشرك", "fr": "Le contraire du shirk"},
            "6": {"en": "Oneness of Allah", "ar": "وحدانية الله", "fr": "Unicité d'Allah"},
        },
        "explanation": {
            "en": "Tawhid is the absolute oneness of Allah — the most fundamental concept in Islam. It means affirming that Allah alone is the Creator, Sustainer, and only one worthy of worship, with no partners or equals.",
            "ar": "التوحيد هو إفراد الله بالوحدانية — أهم مفهوم في الإسلام. يعني تأكيد أن الله وحده الخالق والرازق والمستحق للعبادة بلا شريك.",
            "fr": "Le Tawhid est l'unicité absolue d'Allah — le concept le plus fondamental de l'Islam. Il signifie affirmer qu'Allah seul est le Créateur, le Pourvoyeur, et le seul digne d'adoration, sans associé ni égal.",
        },
    },
    {
        "word_en": "Taqwa",
        "word_ar": "تقوى",
        "word_fr": "Taqwa",
        "accepted_answers": {"en": ["Taqwa", "God-consciousness"], "ar": ["تقوى", "التقوى"], "fr": ["Taqwa", "Piété"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A quality highly praised in the Quran", "ar": "صفة ممدوحة في القرآن", "fr": "Une qualité très louée dans le Coran"},
            "2": {"en": "Being mindful of the Creator", "ar": "استحضار الخالق", "fr": "Être conscient du Créateur"},
            "3": {"en": "Protects from sin", "ar": "تحمي من الذنب", "fr": "Protège du péché"},
            "4": {"en": "The best provision for the Hereafter", "ar": "خير الزاد", "fr": "La meilleure provision pour l'Au-delà"},
            "5": {"en": "Awareness and fear of Allah", "ar": "الوعي بالله وخشيته", "fr": "Conscience et crainte d'Allah"},
            "6": {"en": "God-consciousness and piety", "ar": "الوعي بالله والتقوى", "fr": "Conscience de Dieu et piété"},
        },
        "explanation": {
            "en": "Taqwa means God-consciousness — being constantly aware of Allah's presence and striving to avoid sin. The Prophet said the seat of Taqwa is the heart, and it is the most valuable provision for the Hereafter.",
            "ar": "التقوى تعني مراقبة الله — الوعي الدائم بحضور الله والسعي لتجنب المعاصي. قال النبي إن التقوى ها هنا وأشار إلى صدره، وهي خير الزاد للآخرة.",
            "fr": "La Taqwa signifie la conscience de Dieu — être constamment conscient de la présence d'Allah et s'efforcer d'éviter le péché. Le Prophète a dit que le siège de la Taqwa est le cœur, et c'est la meilleure provision pour l'Au-delà.",
        },
    },
    {
        "word_en": "Zakat",
        "word_ar": "زكاة",
        "word_fr": "Zakat",
        "accepted_answers": {"en": ["Zakat", "Zakah"], "ar": ["زكاة", "الزكاة"], "fr": ["Zakat", "Aumône légale"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "One of the five pillars of Islam", "ar": "ركن من أركان الإسلام", "fr": "Un des cinq piliers de l'Islam"},
            "2": {"en": "Related to wealth", "ar": "يتعلق بالمال", "fr": "Lié à la richesse"},
            "3": {"en": "Usually 2.5% of savings", "ar": "عادة 2.5% من المدخرات", "fr": "Habituellement 2,5% des économies"},
            "4": {"en": "Purifies your wealth", "ar": "تطهر المال", "fr": "Purifie votre richesse"},
            "5": {"en": "Given to the poor and needy", "ar": "تُعطى للفقراء والمحتاجين", "fr": "Donnée aux pauvres et nécessiteux"},
            "6": {"en": "Obligatory charity", "ar": "الصدقة الواجبة", "fr": "Charité obligatoire"},
        },
        "explanation": {
            "en": "Zakat is the third pillar of Islam — an obligatory annual charity of 2.5% of one's savings given to those in need. It purifies wealth, reduces inequality, and strengthens community bonds.",
            "ar": "الزكاة الركن الثالث من أركان الإسلام — صدقة سنوية واجبة بنسبة 2.5% من المدخرات تُعطى للمحتاجين. تطهر المال وتقلل التفاوت وتقوي الروابط المجتمعية.",
            "fr": "La Zakat est le troisième pilier de l'Islam — une charité annuelle obligatoire de 2,5% de ses économies donnée aux nécessiteux. Elle purifie la richesse, réduit les inégalités et renforce les liens communautaires.",
        },
    },
    {
        "word_en": "Hajj",
        "word_ar": "حج",
        "word_fr": "Hajj",
        "accepted_answers": {"en": ["Hajj", "Haj"], "ar": ["حج", "الحج"], "fr": ["Hajj", "Pèlerinage"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "One of the five pillars of Islam", "ar": "ركن من أركان الإسلام", "fr": "Un des cinq piliers de l'Islam"},
            "2": {"en": "Required once in a lifetime", "ar": "واجب مرة في العمر", "fr": "Requis une fois dans la vie"},
            "3": {"en": "Involves traveling to a holy city", "ar": "يتطلب السفر إلى مدينة مقدسة", "fr": "Implique un voyage vers une ville sainte"},
            "4": {"en": "Occurs in the month of Dhul Hijjah", "ar": "يكون في شهر ذي الحجة", "fr": "A lieu au mois de Dhoul Hijja"},
            "5": {"en": "Millions gather wearing white garments", "ar": "الملايين يجتمعون بثياب بيضاء", "fr": "Des millions se rassemblent en vêtements blancs"},
            "6": {"en": "Pilgrimage to Makkah", "ar": "الحج إلى مكة", "fr": "Pèlerinage à La Mecque"},
        },
        "explanation": {
            "en": "Hajj is the annual pilgrimage to Makkah and the fifth pillar of Islam, required once in a lifetime for those who are able. Millions of Muslims gather wearing simple white garments, symbolizing equality before Allah.",
            "ar": "الحج هو الحج السنوي إلى مكة والركن الخامس من أركان الإسلام، واجب مرة في العمر لمن استطاع. يجتمع الملايين بلباس أبيض بسيط رمزاً للمساواة أمام الله.",
            "fr": "Le Hajj est le pèlerinage annuel à La Mecque et le cinquième pilier de l'Islam, obligatoire une fois dans la vie pour ceux qui en ont les moyens. Des millions de musulmans se rassemblent en vêtements blancs simples, symbolisant l'égalité devant Allah.",
        },
    },
    {
        "word_en": "Ihsan",
        "word_ar": "إحسان",
        "word_fr": "Ihsan",
        "accepted_answers": {"en": ["Ihsan", "Excellence"], "ar": ["إحسان", "الإحسان", "احسان"], "fr": ["Ihsan", "Excellence"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "The highest level of faith", "ar": "أعلى مستويات الإيمان", "fr": "Le plus haut niveau de foi"},
            "2": {"en": "Part of the Hadith of Jibreel", "ar": "جزء من حديث جبريل", "fr": "Partie du Hadith de Jibreel"},
            "3": {"en": "To worship as if you see Him", "ar": "أن تعبد الله كأنك تراه", "fr": "Adorer comme si vous Le voyiez"},
            "4": {"en": "Beyond Islam and Iman", "ar": "ما بعد الإسلام والإيمان", "fr": "Au-delà de l'Islam et de l'Iman"},
            "5": {"en": "If you don't see Him, He sees you", "ar": "فإن لم تكن تراه فإنه يراك", "fr": "Si vous ne Le voyez pas, Il vous voit"},
            "6": {"en": "Excellence in worship", "ar": "الإتقان في العبادة", "fr": "Excellence dans l'adoration"},
        },
        "explanation": {
            "en": "Ihsan means excellence in worship — to worship Allah as though you see Him, and if you cannot see Him, know that He sees you. It is the highest level of faith, above Islam (practice) and Iman (belief).",
            "ar": "الإحسان يعني الإتقان في العبادة — أن تعبد الله كأنك تراه فإن لم تكن تراه فإنه يراك. هو أعلى مراتب الإيمان فوق الإسلام والإيمان.",
            "fr": "L'Ihsan signifie l'excellence dans l'adoration — adorer Allah comme si vous Le voyiez, et si vous ne Le voyez pas, savoir qu'Il vous voit. C'est le plus haut niveau de foi, au-dessus de l'Islam (pratique) et de l'Iman (croyance).",
        },
    },
    # === Quran (~10) ===
    {
        "word_en": "Al-Fatiha",
        "word_ar": "الفاتحة",
        "word_fr": "Al-Fatiha",
        "accepted_answers": {"en": ["Al-Fatiha", "Fatiha", "The Opening"], "ar": ["الفاتحة", "سورة الفاتحة"], "fr": ["Al-Fatiha", "L'Ouverture"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "Recited in every salah", "ar": "تُقرأ في كل صلاة", "fr": "Récitée dans chaque salah"},
            "2": {"en": "The most frequently recited surah", "ar": "أكثر سورة تقرأ", "fr": "La sourate la plus récitée"},
            "3": {"en": "Has seven verses", "ar": "لها سبع آيات", "fr": "Contient sept versets"},
            "4": {"en": "Called the Mother of the Book", "ar": "تسمى أم الكتاب", "fr": "Appelée la Mère du Livre"},
            "5": {"en": "Begins with Bismillah", "ar": "تبدأ ببسم الله", "fr": "Commence par Bismillah"},
            "6": {"en": "The Opening chapter of the Quran", "ar": "سورة افتتاح القرآن", "fr": "Le chapitre d'ouverture du Coran"},
        },
        "explanation": {
            "en": "Al-Fatiha (The Opening) is the first surah of the Quran and is recited in every unit of prayer. Known as 'the Mother of the Quran,' it summarizes the entire message of the Quran in seven beautiful verses.",
            "ar": "الفاتحة هي أول سورة في القرآن وتُقرأ في كل ركعة من الصلاة. تُعرف بأم القرآن وتلخص رسالة القرآن كاملة في سبع آيات بليغة.",
            "fr": "Al-Fatiha (L'Ouverture) est la première sourate du Coran et est récitée dans chaque unité de prière. Connue comme 'la Mère du Coran,' elle résume l'ensemble du message coranique en sept beaux versets.",
        },
    },
    {
        "word_en": "Ayat Al-Kursi",
        "word_ar": "آية الكرسي",
        "word_fr": "Ayat Al-Kursi",
        "accepted_answers": {"en": ["Ayat Al-Kursi", "Ayatul Kursi", "Throne Verse"], "ar": ["آية الكرسي", "اية الكرسي"], "fr": ["Ayat Al-Kursi", "Verset du Trône"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "The greatest verse in the Quran", "ar": "أعظم آية في القرآن", "fr": "Le plus grand verset du Coran"},
            "2": {"en": "Found in Surah Al-Baqarah", "ar": "في سورة البقرة", "fr": "Se trouve dans Sourate Al-Baqarah"},
            "3": {"en": "Recited for protection", "ar": "تُقرأ للحماية", "fr": "Récité pour la protection"},
            "4": {"en": "Describes Allah's sovereignty", "ar": "تصف سيادة الله", "fr": "Décrit la souveraineté d'Allah"},
            "5": {"en": "Verse 255 of Al-Baqarah", "ar": "الآية 255 من البقرة", "fr": "Verset 255 de Al-Baqarah"},
            "6": {"en": "The Verse of the Throne", "ar": "آية العرش", "fr": "Le Verset du Trône"},
        },
        "explanation": {
            "en": "Ayat Al-Kursi (The Verse of the Throne) is verse 255 of Surah Al-Baqarah, considered the greatest verse in the Quran. It describes Allah's sovereignty over the heavens and earth and is recited for protection.",
            "ar": "آية الكرسي هي الآية 255 من سورة البقرة وتُعتبر أعظم آية في القرآن. تصف سيادة الله على السماوات والأرض وتُقرأ للحماية.",
            "fr": "Ayat Al-Kursi (Le Verset du Trône) est le verset 255 de la sourate Al-Baqarah, considéré comme le plus grand verset du Coran. Il décrit la souveraineté d'Allah sur les cieux et la terre et est récité pour la protection.",
        },
    },
    # === Islamic History (~10) ===
    {
        "word_en": "Hijra",
        "word_ar": "هجرة",
        "word_fr": "Hégire",
        "accepted_answers": {"en": ["Hijra", "Hijrah", "Migration"], "ar": ["هجرة", "الهجرة"], "fr": ["Hégire", "Hijra"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A pivotal event that changed Islamic history", "ar": "حدث محوري غيّر تاريخ الإسلام", "fr": "Un événement pivot qui a changé l'histoire islamique"},
            "2": {"en": "Involved a long journey", "ar": "تضمنت رحلة طويلة", "fr": "Impliquait un long voyage"},
            "3": {"en": "From Makkah to Madinah", "ar": "من مكة إلى المدينة", "fr": "De La Mecque à Médine"},
            "4": {"en": "Marks the start of the Islamic calendar", "ar": "تمثل بداية التقويم الهجري", "fr": "Marque le début du calendrier islamique"},
            "5": {"en": "The Prophet hid in a cave during this event", "ar": "اختبأ النبي في غار خلال هذا الحدث", "fr": "Le Prophète s'est caché dans une grotte"},
            "6": {"en": "The Migration of the Prophet", "ar": "هجرة النبي", "fr": "La Migration du Prophète"},
        },
        "explanation": {
            "en": "The Hijra was the Prophet Muhammad's migration from Makkah to Madinah in 622 CE, marking the beginning of the Islamic calendar. It was a turning point that established the first Muslim community and state.",
            "ar": "الهجرة كانت انتقال النبي محمد من مكة إلى المدينة سنة 622م، وتمثل بداية التقويم الهجري. كانت نقطة تحول أسست أول مجتمع ودولة إسلامية.",
            "fr": "La Hijra fut la migration du Prophète Muhammad de La Mecque à Médine en 622 de notre ère, marquant le début du calendrier islamique. Ce fut un tournant qui établit la première communauté et le premier État musulman.",
        },
    },
    # === Daily Life (~10) ===
    {
        "word_en": "Wudu",
        "word_ar": "وضوء",
        "word_fr": "Ablutions",
        "accepted_answers": {"en": ["Wudu", "Wudhu", "Ablution"], "ar": ["وضوء", "الوضوء"], "fr": ["Ablutions", "Woudou"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Done before an important act of worship", "ar": "يُفعل قبل عبادة مهمة", "fr": "Fait avant un acte d'adoration important"},
            "2": {"en": "Uses water", "ar": "يستخدم الماء", "fr": "Utilise de l'eau"},
            "3": {"en": "Involves washing specific body parts", "ar": "يتضمن غسل أعضاء محددة", "fr": "Implique le lavage de parties spécifiques du corps"},
            "4": {"en": "Face, hands, arms, head, feet", "ar": "الوجه واليدين والذراعين والرأس والقدمين", "fr": "Visage, mains, bras, tête, pieds"},
            "5": {"en": "Required before salah", "ar": "مطلوب قبل الصلاة", "fr": "Requis avant la salah"},
            "6": {"en": "Ritual ablution", "ar": "الطهارة الشرعية", "fr": "Ablution rituelle"},
        },
        "explanation": {
            "en": "Wudu is the Islamic ritual ablution performed before prayer, involving washing the hands, face, arms, wiping the head, and washing the feet. It symbolizes both physical and spiritual purification.",
            "ar": "الوضوء هو الطهارة الشرعية قبل الصلاة ويشمل غسل اليدين والوجه والذراعين ومسح الرأس وغسل القدمين. يرمز للطهارة الجسدية والروحية.",
            "fr": "Le Woudou est l'ablution rituelle islamique effectuée avant la prière, impliquant le lavage des mains, du visage, des bras, l'essuyage de la tête et le lavage des pieds. Il symbolise la purification physique et spirituelle.",
        },
    },
    {
        "word_en": "Adhan",
        "word_ar": "أذان",
        "word_fr": "Adhan",
        "accepted_answers": {"en": ["Adhan", "Azan", "Azaan"], "ar": ["أذان", "الأذان", "اذان"], "fr": ["Adhan", "Appel à la prière"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Heard five times a day", "ar": "يُسمع خمس مرات يومياً", "fr": "Entendu cinq fois par jour"},
            "2": {"en": "Comes from a high place", "ar": "يأتي من مكان مرتفع", "fr": "Vient d'un endroit élevé"},
            "3": {"en": "Contains the shahada", "ar": "يحتوي الشهادة", "fr": "Contient la shahada"},
            "4": {"en": "Begins with Allahu Akbar", "ar": "يبدأ بالله أكبر", "fr": "Commence par Allahou Akbar"},
            "5": {"en": "The muezzin performs this", "ar": "يؤديه المؤذن", "fr": "Le muezzin l'exécute"},
            "6": {"en": "The call to prayer", "ar": "النداء للصلاة", "fr": "L'appel à la prière"},
        },
        "explanation": {
            "en": "The Adhan is the Islamic call to prayer, announced five times daily from mosques worldwide. It was established in Madinah when Bilal ibn Rabah became the first muezzin, calling the faithful to worship.",
            "ar": "الأذان هو النداء الإسلامي للصلاة، يُعلن خمس مرات يومياً من المساجد حول العالم. أُسس في المدينة حين أصبح بلال بن رباح أول مؤذن.",
            "fr": "L'Adhan est l'appel islamique à la prière, annoncé cinq fois par jour depuis les mosquées du monde entier. Il fut établi à Médine quand Bilal ibn Rabah devint le premier muezzin, appelant les fidèles à l'adoration.",
        },
    },
    {
        "word_en": "Suhoor",
        "word_ar": "سحور",
        "word_fr": "Souhour",
        "accepted_answers": {"en": ["Suhoor", "Suhur", "Sahur"], "ar": ["سحور", "السحور"], "fr": ["Souhour", "Suhoor"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Happens during a special month", "ar": "يحدث في شهر خاص", "fr": "Se produit pendant un mois spécial"},
            "2": {"en": "Eaten very early in the morning", "ar": "يُؤكل في وقت مبكر جداً", "fr": "Mangé très tôt le matin"},
            "3": {"en": "Before dawn", "ar": "قبل الفجر", "fr": "Avant l'aube"},
            "4": {"en": "The Prophet said it is blessed", "ar": "قال النبي إنه مبارك", "fr": "Le Prophète a dit qu'il est béni"},
            "5": {"en": "Gives energy for fasting", "ar": "يعطي طاقة للصيام", "fr": "Donne de l'énergie pour le jeûne"},
            "6": {"en": "Pre-dawn meal during Ramadan", "ar": "وجبة ما قبل الفجر في رمضان", "fr": "Repas avant l'aube pendant le Ramadan"},
        },
        "explanation": {
            "en": "Suhoor is the pre-dawn meal eaten before the Fajr prayer during Ramadan. The Prophet encouraged eating suhoor, saying there is blessing in it. It provides energy for the long fasting day ahead.",
            "ar": "السحور هو وجبة ما قبل الفجر تُؤكل قبل صلاة الفجر في رمضان. حث النبي على السحور وقال إن فيه بركة. يمد الصائم بالطاقة لليوم الطويل.",
            "fr": "Le Souhour est le repas pris avant l'aube, avant la prière du Fajr pendant le Ramadan. Le Prophète a encouragé le souhour, disant qu'il y a de la bénédiction dedans. Il fournit l'énergie pour la longue journée de jeûne.",
        },
    },
    {
        "word_en": "Iftar",
        "word_ar": "إفطار",
        "word_fr": "Iftar",
        "accepted_answers": {"en": ["Iftar", "Iftaar"], "ar": ["إفطار", "الإفطار", "افطار"], "fr": ["Iftar", "Rupture du jeûne"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A daily tradition during Ramadan", "ar": "تقليد يومي في رمضان", "fr": "Une tradition quotidienne pendant le Ramadan"},
            "2": {"en": "Happens at a specific time of day", "ar": "يحدث في وقت محدد من اليوم", "fr": "Se produit à un moment précis de la journée"},
            "3": {"en": "Often starts with dates and water", "ar": "يبدأ غالباً بالتمر والماء", "fr": "Commence souvent par des dattes et de l'eau"},
            "4": {"en": "At sunset", "ar": "عند غروب الشمس", "fr": "Au coucher du soleil"},
            "5": {"en": "Families gather for this", "ar": "تجتمع العائلات لهذا", "fr": "Les familles se rassemblent pour cela"},
            "6": {"en": "Breaking the fast", "ar": "فطور الصيام", "fr": "Rupture du jeûne"},
        },
        "explanation": {
            "en": "Iftar is the meal eaten at sunset to break the daily Ramadan fast. The Prophet would break his fast with dates and water. It is a moment of joy, gratitude, and community gathering.",
            "ar": "الإفطار هو الوجبة عند غروب الشمس لكسر صيام رمضان اليومي. كان النبي يفطر على التمر والماء. إنها لحظة فرح وامتنان واجتماع.",
            "fr": "L'Iftar est le repas pris au coucher du soleil pour rompre le jeûne quotidien du Ramadan. Le Prophète rompait son jeûne avec des dattes et de l'eau. C'est un moment de joie, de gratitude et de rassemblement communautaire.",
        },
    },
    {
        "word_en": "Taraweeh",
        "word_ar": "تراويح",
        "word_fr": "Tarawih",
        "accepted_answers": {"en": ["Taraweeh", "Tarawih", "Taraweeh prayers"], "ar": ["تراويح", "التراويح"], "fr": ["Tarawih", "Taraouih"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A special nightly worship", "ar": "عبادة ليلية خاصة", "fr": "Un culte nocturne spécial"},
            "2": {"en": "Only during one month of the year", "ar": "فقط خلال شهر واحد في السنة", "fr": "Seulement pendant un mois de l'année"},
            "3": {"en": "Prayed in congregation at the mosque", "ar": "تُصلى جماعة في المسجد", "fr": "Priées en congrégation à la mosquée"},
            "4": {"en": "After Isha prayer during Ramadan", "ar": "بعد صلاة العشاء في رمضان", "fr": "Après la prière d'Isha pendant le Ramadan"},
            "5": {"en": "The entire Quran is often completed", "ar": "غالباً يُختم القرآن كاملاً", "fr": "Le Coran entier est souvent complété"},
            "6": {"en": "Ramadan night prayers", "ar": "صلاة الليل في رمضان", "fr": "Prières nocturnes du Ramadan"},
        },
        "explanation": {
            "en": "Taraweeh are special nightly prayers performed during Ramadan after the Isha prayer. They involve reciting long portions of the Quran, and many mosques complete the entire Quran over the 30 nights of Ramadan.",
            "ar": "التراويح صلوات ليلية خاصة تُؤدى في رمضان بعد صلاة العشاء. تتضمن تلاوة أجزاء طويلة من القرآن وتختم كثير من المساجد القرآن كاملاً خلال 30 ليلة.",
            "fr": "Les Tarawih sont des prières nocturnes spéciales effectuées pendant le Ramadan après la prière d'Isha. Elles impliquent la récitation de longues portions du Coran, et de nombreuses mosquées complètent le Coran entier sur les 30 nuits du Ramadan.",
        },
    },
    # === More Prophets ===
    {
        "word_en": "Adam",
        "word_ar": "آدم",
        "word_fr": "Adam",
        "accepted_answers": {"en": ["Adam"], "ar": ["آدم", "ادم"], "fr": ["Adam"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "The very first human being", "ar": "أول إنسان على الإطلاق", "fr": "Le tout premier être humain"},
            "2": {"en": "Created from clay", "ar": "خُلق من طين", "fr": "Créé à partir d'argile"},
            "3": {"en": "Angels were ordered to prostrate to him", "ar": "أُمرت الملائكة بالسجود له", "fr": "Les anges ont reçu l'ordre de se prosterner devant lui"},
            "4": {"en": "Lived in Paradise before descending to Earth", "ar": "عاش في الجنة قبل النزول إلى الأرض", "fr": "A vécu au Paradis avant de descendre sur Terre"},
            "5": {"en": "His wife was Hawwa", "ar": "زوجته حواء", "fr": "Son épouse était Hawwa"},
            "6": {"en": "Father of all mankind", "ar": "أبو البشرية", "fr": "Père de toute l'humanité"},
        },
        "explanation": {
            "en": "Adam is the first human being and the first prophet in Islam, created by Allah from clay. Allah taught him the names of all things and commanded the angels to prostrate before him, establishing humanity's honored status.",
            "ar": "آدم عليه السلام أول إنسان وأول نبي في الإسلام، خلقه الله من طين. علّمه الله الأسماء كلها وأمر الملائكة بالسجود له تكريماً للإنسان.",
            "fr": "Adam est le premier être humain et le premier prophète en Islam, créé par Allah à partir d'argile. Allah lui a enseigné les noms de toutes les choses et a ordonné aux anges de se prosterner devant lui, établissant le statut honoré de l'humanité.",
        },
    },
    {
        "word_en": "Ismail / Ishmael",
        "word_ar": "إسماعيل",
        "word_fr": "Ismaïl / Ismaël",
        "accepted_answers": {"en": ["Ismail", "Ishmael", "Ismaril"], "ar": ["إسماعيل", "اسماعيل"], "fr": ["Ismaël", "Ismail", "Ismaril"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Born after his parents' long prayer for a child", "ar": "وُلد بعد دعاء طويل من والديه", "fr": "Né après une longue prière de ses parents"},
            "2": {"en": "His mother ran between two hills", "ar": "سعت أمه بين تلتين", "fr": "Sa mère a couru entre deux collines"},
            "3": {"en": "Nearly sacrificed by his father", "ar": "كاد أبوه أن يذبحه", "fr": "Presque sacrifié par son père"},
            "4": {"en": "Helped build the Kaaba", "ar": "ساعد في بناء الكعبة", "fr": "A aidé à construire la Kaaba"},
            "5": {"en": "Ancestor of the Prophet Muhammad", "ar": "جد النبي محمد", "fr": "Ancêtre du Prophète Muhammad"},
            "6": {"en": "Son of Ibrahim and Hajar", "ar": "ابن إبراهيم وهاجر", "fr": "Fils d'Ibrahim et Hajar"},
        },
        "explanation": {
            "en": "Ismail (Ishmael) is the son of Ibrahim and Hajar. As a young boy, he submitted to Allah's command when his father was ordered to sacrifice him — a test commemorated during Eid al-Adha. He helped build the Kaaba.",
            "ar": "إسماعيل عليه السلام ابن إبراهيم وهاجر. استسلم صغيراً لأمر الله حين أُمر أبوه بذبحه — اختبار يُحتفى به في عيد الأضحى. ساعد في بناء الكعبة.",
            "fr": "Ismaïl est le fils d'Ibrahim et de Hajar. Jeune garçon, il s'est soumis au commandement d'Allah quand son père reçut l'ordre de le sacrifier — une épreuve commémorée lors de l'Aïd al-Adha. Il a aidé à construire la Kaaba.",
        },
    },
    {
        "word_en": "Yaqub / Jacob",
        "word_ar": "يعقوب",
        "word_fr": "Yacoub / Jacob",
        "accepted_answers": {"en": ["Yaqub", "Yarqub", "Jacob"], "ar": ["يعقوب"], "fr": ["Jacob", "Yacoub", "Yarcoub"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Also known by another name meaning 'Israel'", "ar": "يُعرف أيضاً باسم إسرائيل", "fr": "Aussi connu sous un autre nom signifiant 'Israël'"},
            "2": {"en": "Lost his sight from weeping", "ar": "فقد بصره من كثرة البكاء", "fr": "A perdu la vue à force de pleurer"},
            "3": {"en": "Had twelve sons", "ar": "كان له اثنا عشر ابناً", "fr": "Avait douze fils"},
            "4": {"en": "Grieved deeply for a lost son", "ar": "حزن حزناً شديداً على ابنه المفقود", "fr": "A profondément pleuré un fils perdu"},
            "5": {"en": "His sight was restored by a shirt", "ar": "عاد بصره بقميص", "fr": "Sa vue a été restaurée par une chemise"},
            "6": {"en": "Father of Yusuf", "ar": "والد يوسف", "fr": "Père de Yusuf"},
        },
        "explanation": {
            "en": "Yaqub (Jacob) was the son of Ishaq and grandson of Ibrahim. He endured the long separation from his beloved son Yusuf with patience, weeping until he lost his sight, which was miraculously restored.",
            "ar": "يعقوب عليه السلام ابن إسحاق وحفيد إبراهيم. تحمّل فراق ابنه الحبيب يوسف بصبر وبكى حتى فقد بصره الذي أُعيد له بمعجزة.",
            "fr": "Yacoub (Jacob) était le fils d'Ishaq et le petit-fils d'Ibrahim. Il a enduré la longue séparation de son fils bien-aimé Youssouf avec patience, pleurant jusqu'à perdre la vue, qui fut miraculeusement restaurée.",
        },
    },
    {
        "word_en": "Shuayb / Jethro",
        "word_ar": "شعيب",
        "word_fr": "Chouaïb / Jethro",
        "accepted_answers": {"en": ["Shuayb", "Shoaib", "Shurayb", "Jethro"], "ar": ["شعيب"], "fr": ["Chouaïb", "Chouraib", "Shuayb"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Called the orator of the prophets", "ar": "يُلقب بخطيب الأنبياء", "fr": "Appelé l'orateur des prophètes"},
            "2": {"en": "Warned his people against cheating in trade", "ar": "حذّر قومه من الغش في التجارة", "fr": "A averti son peuple contre la triche dans le commerce"},
            "3": {"en": "Sent to the people of Madyan", "ar": "أُرسل إلى أهل مدين", "fr": "Envoyé au peuple de Madyan"},
            "4": {"en": "His people cheated in weights and measures", "ar": "كان قومه يغشون في الموازين", "fr": "Son peuple trichait dans les poids et mesures"},
            "5": {"en": "Musa married his daughter", "ar": "تزوج موسى ابنته", "fr": "Moïse a épousé sa fille"},
            "6": {"en": "Prophet of Madyan", "ar": "نبي مدين", "fr": "Prophète de Madyan"},
        },
        "explanation": {
            "en": "Shuayb was sent to the people of Madyan who cheated in their business dealings. Known as the 'orator of the prophets' for his eloquence, he called his people to fair trade and honest weights and measures.",
            "ar": "شعيب عليه السلام أُرسل لأهل مدين الذين كانوا يغشون في تجارتهم. يُلقب بخطيب الأنبياء لفصاحته ودعا قومه للتجارة العادلة والكيل والميزان.",
            "fr": "Chouaïb fut envoyé au peuple de Madyan qui trichait dans ses transactions commerciales. Connu comme 'l'orateur des prophètes' pour son éloquence, il a appelé son peuple au commerce équitable et aux poids et mesures honnêtes.",
        },
    },
    {
        "word_en": "Salih",
        "word_ar": "صالح",
        "word_fr": "Salih",
        "accepted_answers": {"en": ["Salih", "Saleh"], "ar": ["صالح"], "fr": ["Salih", "Saleh"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Sent to an ancient Arabian people", "ar": "أُرسل إلى قوم عرب قدماء", "fr": "Envoyé à un ancien peuple arabe"},
            "2": {"en": "His people carved homes in mountains", "ar": "كان قومه ينحتون بيوتاً في الجبال", "fr": "Son peuple sculptait des maisons dans les montagnes"},
            "3": {"en": "A miraculous animal emerged from a rock", "ar": "خرج حيوان معجزة من صخرة", "fr": "Un animal miraculeux est sorti d'un rocher"},
            "4": {"en": "His people killed the miracle", "ar": "قتل قومه المعجزة", "fr": "Son peuple a tué le miracle"},
            "5": {"en": "The she-camel of Allah", "ar": "ناقة الله", "fr": "La chamelle d'Allah"},
            "6": {"en": "Prophet sent to Thamud", "ar": "نبي أُرسل إلى ثمود", "fr": "Prophète envoyé à Thamoud"},
        },
        "explanation": {
            "en": "Salih was sent to the people of Thamud who carved magnificent homes into mountains. Allah gave them the miracle of a she-camel emerging from rock, but they defied the warning and killed it, bringing divine punishment.",
            "ar": "صالح عليه السلام أُرسل لقوم ثمود الذين نحتوا بيوتاً عظيمة في الجبال. أعطاهم الله معجزة ناقة خرجت من الصخر لكنهم عصوا وقتلوها فحل بهم العذاب.",
            "fr": "Salih fut envoyé au peuple de Thamoud qui sculptait de magnifiques demeures dans les montagnes. Allah leur donna le miracle d'une chamelle sortie du rocher, mais ils défièrent l'avertissement et la tuèrent, attirant le châtiment divin.",
        },
    },
    {
        "word_en": "Hud",
        "word_ar": "هود",
        "word_fr": "Houd",
        "accepted_answers": {"en": ["Hud", "Hood"], "ar": ["هود"], "fr": ["Houd", "Hud"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Sent to a powerful ancient people", "ar": "أُرسل إلى قوم أقوياء قدماء", "fr": "Envoyé à un puissant peuple ancien"},
            "2": {"en": "His people were known for building tall structures", "ar": "اشتهر قومه ببناء المباني العالية", "fr": "Son peuple était connu pour construire de hautes structures"},
            "3": {"en": "They said: who is mightier than us?", "ar": "قالوا من أشد منا قوة", "fr": "Ils ont dit : qui est plus puissant que nous ?"},
            "4": {"en": "Destroyed by a violent wind", "ar": "أُهلكوا بريح عاتية", "fr": "Détruits par un vent violent"},
            "5": {"en": "A surah in the Quran bears his name", "ar": "سورة في القرآن تحمل اسمه", "fr": "Une sourate du Coran porte son nom"},
            "6": {"en": "Prophet sent to the people of Ad", "ar": "نبي أُرسل إلى قوم عاد", "fr": "Prophète envoyé au peuple de Ad"},
        },
        "explanation": {
            "en": "Hud was sent to the people of 'Ad, an ancient and powerful civilization known for their tall stature and impressive buildings. They rejected his message, so Allah destroyed them with a furious wind lasting seven nights.",
            "ar": "هود عليه السلام أُرسل لقوم عاد، حضارة قديمة قوية اشتهرت بضخامة أجسامهم ومبانيهم. رفضوا رسالته فأهلكهم الله بريح صرصر سبع ليالٍ.",
            "fr": "Houd fut envoyé au peuple de 'Ad, une civilisation ancienne et puissante connue pour leur grande taille et leurs bâtiments impressionnants. Ils rejetèrent son message, alors Allah les détruisit par un vent furieux durant sept nuits.",
        },
    },
    {
        "word_en": "Zakaria / Zechariah",
        "word_ar": "زكريا",
        "word_fr": "Zakaria / Zacharie",
        "accepted_answers": {"en": ["Zakaria", "Zakariyya", "Zechariah"], "ar": ["زكريا", "زكرياء"], "fr": ["Zacharie", "Zakaria"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Made dua for a child in old age", "ar": "دعا الله بولد في شيخوخته", "fr": "A invoqué Allah pour un enfant dans sa vieillesse"},
            "2": {"en": "Was the guardian of a righteous girl", "ar": "كان كفيل فتاة صالحة", "fr": "Était le gardien d'une fille pieuse"},
            "3": {"en": "Found provision with her that he did not provide", "ar": "وجد عندها رزقاً لم يأتِ به", "fr": "A trouvé auprès d'elle une provision qu'il n'avait pas fournie"},
            "4": {"en": "Told not to speak for three days as a sign", "ar": "أُمر بألا يكلم الناس ثلاثة أيام", "fr": "On lui a dit de ne pas parler pendant trois jours comme signe"},
            "5": {"en": "Father of Yahya", "ar": "والد يحيى", "fr": "Père de Yahya"},
            "6": {"en": "Guardian of Maryam", "ar": "كفيل مريم", "fr": "Gardien de Maryam"},
        },
        "explanation": {
            "en": "Zakaria (Zechariah) was an elderly prophet who prayed to Allah for an heir despite his old age and his wife's barrenness. Allah answered his prayer and blessed him with Yahya (John), a righteous prophet.",
            "ar": "زكريا عليه السلام كان نبياً مسناً دعا الله أن يرزقه ولداً رغم كبر سنه وعقم زوجته. استجاب الله دعاءه وبارك له بيحيى النبي الصالح.",
            "fr": "Zacharie était un prophète âgé qui a prié Allah pour un héritier malgré son grand âge et la stérilité de sa femme. Allah a exaucé sa prière et l'a béni avec Yahya (Jean), un prophète vertueux.",
        },
    },
    {
        "word_en": "Idris / Enoch",
        "word_ar": "إدريس",
        "word_fr": "Idris / Hénoch",
        "accepted_answers": {"en": ["Idris", "Enoch"], "ar": ["إدريس", "ادريس"], "fr": ["Idris", "Énoch"]},
        "category": "Prophets",
        "hints": {
            "1": {"en": "Mentioned only briefly in the Quran", "ar": "ذُكر بإيجاز في القرآن", "fr": "Mentionné brièvement dans le Coran"},
            "2": {"en": "Described as truthful and patient", "ar": "وُصف بالصدق والصبر", "fr": "Décrit comme véridique et patient"},
            "3": {"en": "Raised to a high station", "ar": "رُفع مكاناً علياً", "fr": "Élevé à un haut rang"},
            "4": {"en": "Said to be the first to write with a pen", "ar": "يُقال أنه أول من كتب بالقلم", "fr": "On dit qu'il fut le premier à écrire avec un stylo"},
            "5": {"en": "Among the earliest prophets after Adam", "ar": "من أوائل الأنبياء بعد آدم", "fr": "Parmi les premiers prophètes après Adam"},
            "6": {"en": "Raised to a high place by Allah", "ar": "رفعه الله مكاناً علياً", "fr": "Élevé à un haut lieu par Allah"},
        },
        "explanation": {
            "en": "Idris (Enoch) was among the earliest prophets, known for his vast knowledge and wisdom. The Quran mentions that Allah raised him to a high station. He is traditionally credited with being the first to write with a pen.",
            "ar": "إدريس عليه السلام من أوائل الأنبياء واشتهر بعلمه الواسع وحكمته. ذكر القرآن أن الله رفعه مكاناً علياً. يُنسب إليه تقليدياً أنه أول من كتب بالقلم.",
            "fr": "Idris (Hénoch) fut parmi les premiers prophètes, connu pour son vaste savoir et sa sagesse. Le Coran mentionne qu'Allah l'a élevé à un haut rang. On lui attribue traditionnellement d'avoir été le premier à écrire avec un calame.",
        },
    },
    # === More Companions ===
    {
        "word_en": "Uthman",
        "word_ar": "عثمان",
        "word_fr": "Othman",
        "accepted_answers": {"en": ["Uthman", "Othman", "Uthman ibn Affan"], "ar": ["عثمان", "عثمان بن عفان"], "fr": ["Othman", "Uthman"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Known for his generosity and modesty", "ar": "اشتهر بكرمه وحيائه", "fr": "Connu pour sa générosité et sa modestie"},
            "2": {"en": "Married two daughters of the Prophet", "ar": "تزوج ابنتين من بنات النبي", "fr": "A épousé deux filles du Prophète"},
            "3": {"en": "Compiled the Quran into a single book", "ar": "جمع القرآن في مصحف واحد", "fr": "A compilé le Coran en un seul livre"},
            "4": {"en": "Financed the army of Tabuk", "ar": "جهّز جيش تبوك", "fr": "A financé l'armée de Tabuk"},
            "5": {"en": "The third Caliph", "ar": "الخليفة الثالث", "fr": "Le troisième Calife"},
            "6": {"en": "Dhun-Nurain (Possessor of Two Lights)", "ar": "ذو النورين", "fr": "Dhun-Nurain (Possesseur de Deux Lumières)"},
        },
        "explanation": {
            "en": "Uthman ibn Affan was the third Caliph, known for his generosity and modesty. He compiled the standardized written Quran (mushaf) and is called 'Dhun-Nurayn' (possessor of two lights) for marrying two of the Prophet's daughters.",
            "ar": "عثمان بن عفان الخليفة الثالث واشتهر بكرمه وحيائه. جمع المصحف الشريف ويُلقب بذي النورين لزواجه من ابنتي النبي.",
            "fr": "Othman ibn Affan fut le troisième calife, connu pour sa générosité et sa modestie. Il a compilé le Coran standardisé (mushaf) et est appelé 'Dhun-Nurayn' (possesseur de deux lumières) pour avoir épousé deux filles du Prophète.",
        },
    },
    {
        "word_en": "Aisha",
        "word_ar": "عائشة",
        "word_fr": "Aïcha",
        "accepted_answers": {"en": ["Aisha", "Aishah"], "ar": ["عائشة", "عايشة"], "fr": ["Aïcha", "Aicha"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Known for her vast knowledge", "ar": "اشتهرت بعلمها الواسع", "fr": "Connue pour son vaste savoir"},
            "2": {"en": "Narrated over 2000 hadiths", "ar": "روت أكثر من 2000 حديث", "fr": "A rapporté plus de 2000 hadiths"},
            "3": {"en": "Daughter of the first Caliph", "ar": "ابنة الخليفة الأول", "fr": "Fille du premier Calife"},
            "4": {"en": "Scholars would come to her for rulings", "ar": "كان العلماء يأتون إليها للفتوى", "fr": "Les savants venaient la consulter pour des jugements"},
            "5": {"en": "The Prophet passed away in her room", "ar": "توفي النبي في حجرتها", "fr": "Le Prophète est décédé dans sa chambre"},
            "6": {"en": "Mother of the Believers, daughter of Abu Bakr", "ar": "أم المؤمنين بنت أبي بكر", "fr": "Mère des Croyants, fille d'Abou Bakr"},
        },
        "explanation": {
            "en": "Aisha bint Abi Bakr was the wife of Prophet Muhammad and one of the greatest scholars of Islam. She narrated over 2,000 hadiths and was a leading authority on Islamic jurisprudence, medicine, and poetry.",
            "ar": "عائشة بنت أبي بكر زوجة النبي محمد ومن أعظم علماء الإسلام. روت أكثر من 2000 حديث وكانت مرجعاً في الفقه والطب والشعر.",
            "fr": "Aïcha bint Abi Bakr était l'épouse du Prophète Muhammad et l'une des plus grandes savantes de l'Islam. Elle a rapporté plus de 2 000 hadiths et était une autorité de premier plan en jurisprudence islamique, médecine et poésie.",
        },
    },
    {
        "word_en": "Khalid ibn al-Walid",
        "word_ar": "خالد بن الوليد",
        "word_fr": "Khalid ibn al-Walid",
        "accepted_answers": {"en": ["Khalid", "Khalid ibn al-Walid"], "ar": ["خالد", "خالد بن الوليد"], "fr": ["Khalid", "Khalid ibn al-Walid"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "A brilliant military strategist", "ar": "استراتيجي عسكري عبقري", "fr": "Un brillant stratège militaire"},
            "2": {"en": "Initially fought against Muslims", "ar": "حارب المسلمين في البداية", "fr": "A d'abord combattu contre les musulmans"},
            "3": {"en": "Never lost a battle", "ar": "لم يخسر معركة قط", "fr": "N'a jamais perdu une bataille"},
            "4": {"en": "Led the Muslim army in many conquests", "ar": "قاد الجيش الإسلامي في فتوحات كثيرة", "fr": "A mené l'armée musulmane dans de nombreuses conquêtes"},
            "5": {"en": "The Prophet gave him a famous title", "ar": "أعطاه النبي لقباً مشهوراً", "fr": "Le Prophète lui a donné un titre célèbre"},
            "6": {"en": "The Sword of Allah", "ar": "سيف الله المسلول", "fr": "L'Épée d'Allah"},
        },
        "explanation": {
            "en": "Khalid ibn al-Walid was a military genius known as 'the Sword of Allah.' He never lost a battle, whether fighting against or for Islam. After converting, he became one of the most successful commanders in history.",
            "ar": "خالد بن الوليد عبقري عسكري يُلقب بسيف الله المسلول. لم يُهزم في أي معركة سواء ضد الإسلام أو معه. بعد إسلامه أصبح من أنجح القادة في التاريخ.",
            "fr": "Khalid ibn al-Walid était un génie militaire connu comme 'l'Épée d'Allah.' Il n'a jamais perdu une bataille, que ce soit en combattant contre ou pour l'Islam. Après sa conversion, il devint l'un des commandants les plus victorieux de l'histoire.",
        },
    },
    {
        "word_en": "Fatimah",
        "word_ar": "فاطمة",
        "word_fr": "Fatima",
        "accepted_answers": {"en": ["Fatimah", "Fatima"], "ar": ["فاطمة"], "fr": ["Fatima", "Fatimah"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Known as the leader of the women of Paradise", "ar": "سيدة نساء أهل الجنة", "fr": "Connue comme la chef des femmes du Paradis"},
            "2": {"en": "Resembled the Prophet the most in character", "ar": "أكثر من يشبه النبي خُلقاً", "fr": "Ressemblait le plus au Prophète en caractère"},
            "3": {"en": "Mother of Al-Hasan and Al-Husayn", "ar": "أم الحسن والحسين", "fr": "Mère d'Al-Hasan et Al-Husayn"},
            "4": {"en": "Her husband was the fourth Caliph", "ar": "زوجها الخليفة الرابع", "fr": "Son mari était le quatrième Calife"},
            "5": {"en": "Called Az-Zahra (The Radiant)", "ar": "لُقبت بالزهراء", "fr": "Appelée Az-Zahra (La Resplendissante)"},
            "6": {"en": "Daughter of the Prophet Muhammad", "ar": "بنت النبي محمد", "fr": "Fille du Prophète Muhammad"},
        },
        "explanation": {
            "en": "Fatimah al-Zahra was the youngest daughter of Prophet Muhammad and Khadijah, and the wife of Ali ibn Abi Talib. She is considered the leader of the women of Paradise and the mother of the Prophet's grandsons Hasan and Husayn.",
            "ar": "فاطمة الزهراء أصغر بنات النبي محمد وخديجة وزوجة علي بن أبي طالب. تُعتبر سيدة نساء الجنة وأم حفيدي النبي الحسن والحسين.",
            "fr": "Fatima al-Zahra était la plus jeune fille du Prophète Muhammad et de Khadija, et l'épouse d'Ali ibn Abi Talib. Elle est considérée comme la dame des femmes du Paradis et la mère des petits-fils du Prophète, Hassan et Hussein.",
        },
    },
    {
        "word_en": "Salman al-Farisi",
        "word_ar": "سلمان الفارسي",
        "word_fr": "Salman al-Farisi",
        "accepted_answers": {"en": ["Salman", "Salman al-Farisi"], "ar": ["سلمان", "سلمان الفارسي"], "fr": ["Salman", "Salman al-Farisi"]},
        "category": "Companions",
        "hints": {
            "1": {"en": "Traveled across many lands seeking truth", "ar": "سافر عبر بلاد كثيرة باحثاً عن الحق", "fr": "A voyagé à travers de nombreuses terres en quête de vérité"},
            "2": {"en": "Originally from Persia", "ar": "أصله من فارس", "fr": "Originaire de Perse"},
            "3": {"en": "Suggested a famous defensive strategy", "ar": "اقترح خطة دفاعية مشهورة", "fr": "A suggéré une stratégie défensive célèbre"},
            "4": {"en": "The Prophet said he is from Ahl al-Bayt", "ar": "قال النبي إنه من أهل البيت", "fr": "Le Prophète a dit qu'il fait partie des Ahl al-Bayt"},
            "5": {"en": "His idea was to dig a trench", "ar": "فكرته كانت حفر خندق", "fr": "Son idée était de creuser un fossé"},
            "6": {"en": "The Persian companion who proposed the trench", "ar": "الصحابي الفارسي الذي اقترح الخندق", "fr": "Le compagnon persan qui a proposé le fossé"},
        },
        "explanation": {
            "en": "Salman al-Farisi was a Persian companion who traveled across lands seeking the truth before embracing Islam. He suggested digging a trench around Madinah during the Battle of the Khandaq, a strategy that saved the city.",
            "ar": "سلمان الفارسي صحابي فارسي سافر عبر البلاد باحثاً عن الحق قبل اعتناق الإسلام. اقترح حفر خندق حول المدينة في غزوة الخندق مما أنقذ المدينة.",
            "fr": "Salman al-Farisi était un compagnon persan qui a voyagé à travers les terres à la recherche de la vérité avant d'embrasser l'Islam. Il a suggéré de creuser une tranchée autour de Médine lors de la bataille du Khandaq, une stratégie qui a sauvé la ville.",
        },
    },
    # === More Islamic Concepts ===
    {
        "word_en": "Shura",
        "word_ar": "شورى",
        "word_fr": "Choura",
        "accepted_answers": {"en": ["Shura", "Consultation"], "ar": ["شورى", "الشورى"], "fr": ["Choura", "Consultation"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A principle of governance in Islam", "ar": "مبدأ حكم في الإسلام", "fr": "Un principe de gouvernance en Islam"},
            "2": {"en": "A surah in the Quran bears this name", "ar": "سورة في القرآن تحمل هذا الاسم", "fr": "Une sourate du Coran porte ce nom"},
            "3": {"en": "The Prophet practiced this with his companions", "ar": "مارسها النبي مع صحابته", "fr": "Le Prophète la pratiquait avec ses compagnons"},
            "4": {"en": "Making decisions together", "ar": "اتخاذ القرارات معاً", "fr": "Prendre des décisions ensemble"},
            "5": {"en": "And their affairs are by this among them (Quran)", "ar": "وأمرهم شورى بينهم", "fr": "Et leurs affaires sont par ceci entre eux (Coran)"},
            "6": {"en": "Mutual consultation", "ar": "التشاور المتبادل", "fr": "Consultation mutuelle"},
        },
        "explanation": {
            "en": "Shura means consultation — the Islamic principle of making decisions through mutual discussion. The Quran praises those 'whose affairs are decided by consultation among themselves,' making it a core value of Islamic governance.",
            "ar": "الشورى مبدأ إسلامي لاتخاذ القرارات بالتشاور. أثنى القرآن على الذين 'أمرهم شورى بينهم' مما يجعلها قيمة أساسية في الحكم الإسلامي.",
            "fr": "La Choura signifie consultation — le principe islamique de prendre des décisions par discussion mutuelle. Le Coran loue ceux 'dont les affaires sont décidées par consultation entre eux,' en faisant une valeur fondamentale de la gouvernance islamique.",
        },
    },
    {
        "word_en": "Sadaqah",
        "word_ar": "صدقة",
        "word_fr": "Sadaqa",
        "accepted_answers": {"en": ["Sadaqah", "Sadaqa", "Charity"], "ar": ["صدقة", "الصدقة"], "fr": ["Sadaqa", "Aumône volontaire"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A virtuous act encouraged in Islam", "ar": "عمل فاضل مستحب في الإسلام", "fr": "Un acte vertueux encouragé en Islam"},
            "2": {"en": "Even a smile counts as one", "ar": "حتى الابتسامة تعتبر واحدة", "fr": "Même un sourire en est une"},
            "3": {"en": "It does not decrease wealth", "ar": "لا تنقص المال", "fr": "Elle ne diminue pas la richesse"},
            "4": {"en": "Different from the obligatory form of giving", "ar": "تختلف عن العطاء الواجب", "fr": "Différente de la forme obligatoire de don"},
            "5": {"en": "Can be given at any time", "ar": "يمكن إعطاؤها في أي وقت", "fr": "Peut être donnée à tout moment"},
            "6": {"en": "Voluntary charity", "ar": "الصدقة التطوعية", "fr": "Charité volontaire"},
        },
        "explanation": {
            "en": "Sadaqah is voluntary charity given out of compassion and generosity, beyond the obligatory Zakat. The Prophet said even a smile is Sadaqah, teaching that charity extends far beyond financial giving.",
            "ar": "الصدقة عطاء تطوعي بدافع الرحمة والكرم يتجاوز الزكاة الواجبة. قال النبي إن التبسم في وجه أخيك صدقة مبيناً أن العطاء أوسع من المال.",
            "fr": "La Sadaqah est une charité volontaire donnée par compassion et générosité, au-delà de la Zakat obligatoire. Le Prophète a dit que même un sourire est une Sadaqah, enseignant que la charité va bien au-delà du don financier.",
        },
    },
    {
        "word_en": "Istighfar",
        "word_ar": "استغفار",
        "word_fr": "Istighfar",
        "accepted_answers": {"en": ["Istighfar", "Seeking forgiveness"], "ar": ["استغفار", "الاستغفار"], "fr": ["Istighfar", "Demande de pardon"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A practice the Prophet did over 70 times daily", "ar": "عمل كان النبي يفعله أكثر من 70 مرة يومياً", "fr": "Une pratique que le Prophète faisait plus de 70 fois par jour"},
            "2": {"en": "Opens doors to provision and relief", "ar": "يفتح أبواب الرزق والفرج", "fr": "Ouvre les portes de la provision et du soulagement"},
            "3": {"en": "Nuh told his people to do this", "ar": "أمر نوح قومه بهذا", "fr": "Noé a dit à son peuple de faire cela"},
            "4": {"en": "Astaghfirullah is its common form", "ar": "أستغفر الله هي صيغته الشائعة", "fr": "Astaghfirullah est sa forme courante"},
            "5": {"en": "Erases sins and brings peace", "ar": "يمحو الذنوب ويجلب السكينة", "fr": "Efface les péchés et apporte la paix"},
            "6": {"en": "Seeking Allah's forgiveness", "ar": "طلب مغفرة الله", "fr": "Demander le pardon d'Allah"},
        },
        "explanation": {
            "en": "Istighfar is the act of seeking Allah's forgiveness, typically by saying 'Astaghfirullah.' The Prophet himself sought forgiveness over 70 times daily, teaching that repentance is a continuous spiritual practice, not just for major sins.",
            "ar": "الاستغفار هو طلب مغفرة الله عادة بقول 'أستغفر الله.' كان النبي نفسه يستغفر أكثر من 70 مرة يومياً مبيناً أن التوبة عبادة مستمرة لا تقتصر على الكبائر.",
            "fr": "L'Istighfar est l'acte de demander le pardon d'Allah, typiquement en disant 'Astaghfirullah.' Le Prophète lui-même demandait pardon plus de 70 fois par jour, enseignant que le repentir est une pratique spirituelle continue, pas seulement pour les grands péchés.",
        },
    },
    {
        "word_en": "Tawakkul",
        "word_ar": "توكل",
        "word_fr": "Tawakkul",
        "accepted_answers": {"en": ["Tawakkul", "Trust in Allah", "Reliance"], "ar": ["توكل", "التوكل"], "fr": ["Tawakkul", "Confiance en Allah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A quality of the believers", "ar": "صفة من صفات المؤمنين", "fr": "Une qualité des croyants"},
            "2": {"en": "Tie your camel, then do this", "ar": "اعقلها وتوكل", "fr": "Attache ton chameau, puis fais ceci"},
            "3": {"en": "Does not mean being passive", "ar": "لا يعني أن تكون سلبياً", "fr": "Ne signifie pas être passif"},
            "4": {"en": "Take action, but leave the result to Allah", "ar": "اعمل ثم فوّض النتيجة لله", "fr": "Agis, mais laisse le résultat à Allah"},
            "5": {"en": "Whoever does this, Allah is sufficient for them", "ar": "ومن يتوكل على الله فهو حسبه", "fr": "Quiconque fait cela, Allah lui suffit"},
            "6": {"en": "Reliance and trust in Allah", "ar": "الاعتماد والثقة بالله", "fr": "S'en remettre à Allah et Lui faire confiance"},
        },
        "explanation": {
            "en": "Tawakkul means complete trust and reliance on Allah after taking all necessary actions. The Prophet taught: 'Tie your camel, then place your trust in Allah' — combining effort with faith in divine wisdom.",
            "ar": "التوكل يعني الثقة الكاملة بالله بعد اتخاذ كل الأسباب. علّم النبي: 'اعقلها وتوكل' — الجمع بين العمل والإيمان بحكمة الله.",
            "fr": "Le Tawakkul signifie la confiance totale en Allah après avoir pris toutes les mesures nécessaires. Le Prophète a enseigné : 'Attache ton chameau, puis place ta confiance en Allah' — combinant l'effort avec la foi en la sagesse divine.",
        },
    },
    {
        "word_en": "Sabr",
        "word_ar": "صبر",
        "word_fr": "Patience",
        "accepted_answers": {"en": ["Sabr", "Patience"], "ar": ["صبر", "الصبر"], "fr": ["Patience", "Sabr"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "One of the most mentioned virtues in the Quran", "ar": "من أكثر الفضائل ذكراً في القرآن", "fr": "L'une des vertus les plus mentionnées dans le Coran"},
            "2": {"en": "Allah is with those who have this quality", "ar": "الله مع من يتحلى بهذه الصفة", "fr": "Allah est avec ceux qui ont cette qualité"},
            "3": {"en": "Three types: in obedience, from sin, and during hardship", "ar": "ثلاثة أنواع: على الطاعة وعن المعصية وعلى البلاء", "fr": "Trois types : dans l'obéissance, face au péché, et durant l'épreuve"},
            "4": {"en": "Yaqub said: beautiful is this", "ar": "قال يعقوب: فصبر جميل", "fr": "Yaqub a dit : belle est cette qualité"},
            "5": {"en": "Its reward is without measure", "ar": "أجرها بغير حساب", "fr": "Sa récompense est sans mesure"},
            "6": {"en": "Patient perseverance", "ar": "الصبر والمثابرة", "fr": "Persévérance patiente"},
        },
        "explanation": {
            "en": "Sabr (patience) is one of the highest virtues in Islam, mentioned over 90 times in the Quran. It encompasses patience in hardship, patience in obedience to Allah, and patience in refraining from sin.",
            "ar": "الصبر من أعلى الفضائل في الإسلام ذُكر أكثر من 90 مرة في القرآن. يشمل الصبر على البلاء والصبر على الطاعة والصبر عن المعصية.",
            "fr": "Le Sabr (patience) est l'une des plus hautes vertus en Islam, mentionné plus de 90 fois dans le Coran. Il englobe la patience dans l'adversité, la patience dans l'obéissance à Allah et la patience pour s'abstenir du péché.",
        },
    },
    # === More Quran ===
    {
        "word_en": "Al-Ikhlas",
        "word_ar": "الإخلاص",
        "word_fr": "Al-Ikhlas",
        "accepted_answers": {"en": ["Al-Ikhlas", "Ikhlas", "Sincerity"], "ar": ["الإخلاص", "سورة الإخلاص"], "fr": ["Al-Ikhlas", "La Sincérité"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "A very short surah", "ar": "سورة قصيرة جداً", "fr": "Une sourate très courte"},
            "2": {"en": "Equal to one-third of the Quran in reward", "ar": "تعدل ثلث القرآن أجراً", "fr": "Équivaut à un tiers du Coran en récompense"},
            "3": {"en": "Describes who Allah is", "ar": "تصف من هو الله", "fr": "Décrit qui est Allah"},
            "4": {"en": "Qul Huwa Allahu Ahad", "ar": "قل هو الله أحد", "fr": "Qul Huwa Allahu Ahad"},
            "5": {"en": "Has only four verses", "ar": "لها أربع آيات فقط", "fr": "N'a que quatre versets"},
            "6": {"en": "The Surah of Pure Sincerity", "ar": "سورة الإخلاص والتوحيد", "fr": "La Sourate de la Pure Sincérité"},
        },
        "explanation": {
            "en": "Surah Al-Ikhlas (The Sincerity) is the 112th chapter of the Quran, containing just four verses that define pure monotheism. The Prophet said it equals one-third of the Quran in meaning and significance.",
            "ar": "سورة الإخلاص السورة 112 من القرآن تحتوي أربع آيات تُعرّف التوحيد الخالص. قال النبي إنها تعدل ثلث القرآن في المعنى والأهمية.",
            "fr": "La sourate Al-Ikhlas (La Sincérité) est le 112e chapitre du Coran, contenant seulement quatre versets qui définissent le monothéisme pur. Le Prophète a dit qu'elle équivaut à un tiers du Coran en sens et en importance.",
        },
    },
    {
        "word_en": "Al-Kahf",
        "word_ar": "الكهف",
        "word_fr": "Al-Kahf",
        "accepted_answers": {"en": ["Al-Kahf", "The Cave"], "ar": ["الكهف", "سورة الكهف"], "fr": ["Al-Kahf", "La Caverne"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "Recommended to read every Friday", "ar": "يُسن قراءتها كل جمعة", "fr": "Recommandé de la lire chaque vendredi"},
            "2": {"en": "Contains four major stories", "ar": "تحتوي أربع قصص رئيسية", "fr": "Contient quatre histoires majeures"},
            "3": {"en": "Protection from Dajjal", "ar": "حماية من الدجال", "fr": "Protection contre le Dajjal"},
            "4": {"en": "Young men who slept for centuries", "ar": "فتية ناموا قروناً", "fr": "Des jeunes hommes qui ont dormi des siècles"},
            "5": {"en": "Musa's journey with Al-Khidr", "ar": "رحلة موسى مع الخضر", "fr": "Le voyage de Moïse avec Al-Khidr"},
            "6": {"en": "The Surah of the Cave", "ar": "سورة الكهف", "fr": "La Sourate de la Caverne"},
        },
        "explanation": {
            "en": "Surah Al-Kahf (The Cave) is the 18th chapter of the Quran, telling four powerful stories including the Sleepers of the Cave and Dhul-Qarnayn. The Prophet recommended reading it every Friday for spiritual light and protection.",
            "ar": "سورة الكهف السورة 18 من القرآن تروي أربع قصص قوية منها أصحاب الكهف وذو القرنين. أوصى النبي بقراءتها كل جمعة للنور والحماية الروحية.",
            "fr": "La sourate Al-Kahf (La Caverne) est le 18e chapitre du Coran, racontant quatre histoires puissantes dont les Dormants de la Caverne et Dhul-Qarnayn. Le Prophète a recommandé de la lire chaque vendredi pour la lumière spirituelle et la protection.",
        },
    },
    {
        "word_en": "Al-Mulk",
        "word_ar": "الملك",
        "word_fr": "Al-Mulk",
        "accepted_answers": {"en": ["Al-Mulk", "The Sovereignty", "Tabarak"], "ar": ["الملك", "سورة الملك", "تبارك"], "fr": ["Al-Mulk", "La Royauté"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "Recommended to read before sleeping", "ar": "يُسن قراءتها قبل النوم", "fr": "Recommandé de la lire avant de dormir"},
            "2": {"en": "Protects from the punishment of the grave", "ar": "تحمي من عذاب القبر", "fr": "Protège du châtiment de la tombe"},
            "3": {"en": "Has 30 verses", "ar": "لها 30 آية", "fr": "Contient 30 versets"},
            "4": {"en": "Begins with: Blessed is He in whose hand is dominion", "ar": "تبدأ بـ تبارك الذي بيده الملك", "fr": "Commence par : Béni soit Celui dans la main duquel est la royauté"},
            "5": {"en": "It will intercede for its reader", "ar": "ستشفع لقارئها", "fr": "Elle intercédera pour son lecteur"},
            "6": {"en": "The Surah of Sovereignty", "ar": "سورة الملك", "fr": "La Sourate de la Royauté"},
        },
        "explanation": {
            "en": "Surah Al-Mulk (The Sovereignty) is the 67th chapter of the Quran. The Prophet said it intercedes for its reader in the grave, and recommended reciting it every night before sleep for protection.",
            "ar": "سورة الملك السورة 67 من القرآن. قال النبي إنها تشفع لقارئها في القبر وأوصى بقراءتها كل ليلة قبل النوم للحماية.",
            "fr": "La sourate Al-Mulk (La Souveraineté) est le 67e chapitre du Coran. Le Prophète a dit qu'elle intercède pour son lecteur dans la tombe et a recommandé de la réciter chaque nuit avant de dormir pour la protection.",
        },
    },
    {
        "word_en": "Surah Yasin",
        "word_ar": "سورة يس",
        "word_fr": "Sourate Yasin",
        "accepted_answers": {"en": ["Yasin", "Ya Sin", "Surah Yasin"], "ar": ["يس", "سورة يس"], "fr": ["Yasin", "Ya Sin", "Sourate Yasin"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "Called the heart of the Quran", "ar": "تُسمى قلب القرآن", "fr": "Appelée le cœur du Coran"},
            "2": {"en": "Begins with two Arabic letters", "ar": "تبدأ بحرفين عربيين", "fr": "Commence par deux lettres arabes"},
            "3": {"en": "Contains the story of the people of the town", "ar": "تحتوي قصة أصحاب القرية", "fr": "Contient l'histoire des gens de la ville"},
            "4": {"en": "Discusses resurrection and signs of Allah", "ar": "تناقش البعث وآيات الله", "fr": "Traite de la résurrection et des signes d'Allah"},
            "5": {"en": "Often recited for the deceased", "ar": "تُقرأ غالباً على الميت", "fr": "Souvent récitée pour les défunts"},
            "6": {"en": "The heart of the Quran", "ar": "قلب القرآن", "fr": "Le cœur du Coran"},
        },
        "explanation": {
            "en": "Surah Yasin is the 36th chapter of the Quran, often called 'the Heart of the Quran.' It covers themes of resurrection, divine signs in nature, and the fate of those who reject the message.",
            "ar": "سورة يس السورة 36 من القرآن وتُسمى قلب القرآن. تتناول مواضيع البعث وآيات الله في الطبيعة ومصير المكذبين.",
            "fr": "La sourate Yasin est le 36e chapitre du Coran, souvent appelée 'le Cœur du Coran.' Elle couvre les thèmes de la résurrection, des signes divins dans la nature et du sort de ceux qui rejettent le message.",
        },
    },
    # === More Islamic History (single-word answers) ===
    {
        "word_en": "Badr",
        "word_ar": "بدر",
        "word_fr": "Badr",
        "accepted_answers": {"en": ["Badr"], "ar": ["بدر"], "fr": ["Badr"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A decisive early event in Islamic history", "ar": "حدث حاسم في بداية الإسلام", "fr": "Un événement décisif au début de l'Islam"},
            "2": {"en": "Muslims were greatly outnumbered", "ar": "كان المسلمون أقل عدداً بكثير", "fr": "Les musulmans étaient largement dépassés en nombre"},
            "3": {"en": "313 Muslims vs about 1000 enemies", "ar": "313 مسلماً ضد نحو 1000", "fr": "313 musulmans contre environ 1000 ennemis"},
            "4": {"en": "Angels descended to help", "ar": "نزلت الملائكة للمساعدة", "fr": "Les anges sont descendus pour aider"},
            "5": {"en": "Occurred in the 2nd year after Hijra", "ar": "وقعت في السنة الثانية بعد الهجرة", "fr": "S'est produite la 2e année après la Hijra"},
            "6": {"en": "The first major battle of Islam", "ar": "أول معركة كبرى في الإسلام", "fr": "La première grande bataille de l'Islam"},
        },
        "explanation": {
            "en": "Badr was the first major battle in Islamic history (624 CE), where 313 Muslims defeated an army of about 1,000 Quraysh warriors. Allah sent angels to aid the believers, making it a defining moment of early Islam.",
            "ar": "بدر أول معركة كبرى في تاريخ الإسلام (624م) حيث هزم 313 مسلماً جيشاً من نحو 1000 مقاتل قرشي. أرسل الله الملائكة لنصرة المؤمنين مما جعلها لحظة فارقة.",
            "fr": "Badr fut la première grande bataille de l'histoire islamique (624), où 313 musulmans ont vaincu une armée d'environ 1 000 guerriers Quraysh. Allah a envoyé des anges pour aider les croyants, en faisant un moment déterminant de l'Islam naissant.",
        },
    },
    {
        "word_en": "Uhud",
        "word_ar": "أحد",
        "word_fr": "Uhud",
        "accepted_answers": {"en": ["Uhud", "Ohud"], "ar": ["أحد"], "fr": ["Uhud", "Ohoud"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A mountain near Madinah", "ar": "جبل قرب المدينة", "fr": "Une montagne près de Médine"},
            "2": {"en": "The Prophet said: this mountain loves us and we love it", "ar": "قال النبي: هذا جبل يحبنا ونحبه", "fr": "Le Prophète a dit : cette montagne nous aime et nous l'aimons"},
            "3": {"en": "Archers left their positions", "ar": "ترك الرماة مواقعهم", "fr": "Les archers ont quitté leurs positions"},
            "4": {"en": "Hamza was martyred here", "ar": "استشهد حمزة هنا", "fr": "Hamza y a été martyrisé"},
            "5": {"en": "The second major battle in Islam", "ar": "المعركة الكبرى الثانية في الإسلام", "fr": "La deuxième grande bataille en Islam"},
            "6": {"en": "Battle at the mountain near Madinah", "ar": "معركة عند الجبل قرب المدينة", "fr": "Bataille à la montagne près de Médine"},
        },
        "explanation": {
            "en": "Uhud was the second major battle in Islam (625 CE), fought near the mountain of Uhud outside Madinah. The Muslims initially prevailed but suffered losses when archers left their positions, teaching a lasting lesson about discipline.",
            "ar": "أحد ثاني معركة كبرى في الإسلام (625م) قرب جبل أحد خارج المدينة. انتصر المسلمون أولاً لكنهم تكبدوا خسائر حين ترك الرماة مواقعهم درساً في الانضباط.",
            "fr": "Uhud fut la deuxième grande bataille de l'Islam (625), livrée près du mont Uhud à l'extérieur de Médine. Les musulmans l'emportèrent d'abord mais subirent des pertes quand les archers quittèrent leurs positions, enseignant une leçon durable sur la discipline.",
        },
    },
    {
        "word_en": "Khandaq",
        "word_ar": "خندق",
        "word_fr": "Khandaq",
        "accepted_answers": {"en": ["Khandaq", "Trench", "Ahzab"], "ar": ["خندق", "الخندق", "الأحزاب"], "fr": ["Khandaq", "Tranchée"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A defensive strategy was used for the first time in Arabia", "ar": "استُخدمت استراتيجية دفاعية لأول مرة في الجزيرة", "fr": "Une stratégie défensive a été utilisée pour la première fois en Arabie"},
            "2": {"en": "Salman al-Farisi suggested the plan", "ar": "اقترح سلمان الفارسي الخطة", "fr": "Salman al-Farisi a suggéré le plan"},
            "3": {"en": "A coalition of tribes besieged Madinah", "ar": "حاصر تحالف من القبائل المدينة", "fr": "Une coalition de tribus a assiégé Médine"},
            "4": {"en": "The wind dispersed the enemy", "ar": "الريح فرّقت العدو", "fr": "Le vent a dispersé l'ennemi"},
            "5": {"en": "Also known as the Battle of the Confederates", "ar": "تُعرف أيضاً بغزوة الأحزاب", "fr": "Aussi connue comme la Bataille des Coalisés"},
            "6": {"en": "The Battle of the Trench", "ar": "غزوة الخندق", "fr": "La Bataille du Fossé"},
        },
        "explanation": {
            "en": "The Battle of the Khandaq (Trench) in 627 CE saw the Muslims defend Madinah by digging a trench — a strategy suggested by Salman al-Farisi. The siege failed and the coalition of enemies dispersed.",
            "ar": "غزوة الخندق سنة 627م حيث دافع المسلمون عن المدينة بحفر خندق — استراتيجية اقترحها سلمان الفارسي. فشل الحصار وتفرق تحالف الأعداء.",
            "fr": "La bataille du Khandaq (Tranchée) en 627 vit les musulmans défendre Médine en creusant une tranchée — une stratégie suggérée par Salman al-Farisi. Le siège échoua et la coalition ennemie se dispersa.",
        },
    },
    # === More Daily Life ===
    {
        "word_en": "Dua",
        "word_ar": "دعاء",
        "word_fr": "Invocation",
        "accepted_answers": {"en": ["Dua", "Duraa", "Supplication"], "ar": ["دعاء", "الدعاء"], "fr": ["Invocation", "Dua", "Doua", "Douraa"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "The weapon of the believer", "ar": "سلاح المؤمن", "fr": "L'arme du croyant"},
            "2": {"en": "Can be made at any time, anywhere", "ar": "يمكن فعله في أي وقت وأي مكان", "fr": "Peut être fait à tout moment, n'importe où"},
            "3": {"en": "The Prophet called it the essence of worship", "ar": "سماه النبي مخ العبادة", "fr": "Le Prophète l'a appelé l'essence de l'adoration"},
            "4": {"en": "Raising your hands while calling upon Allah", "ar": "رفع اليدين أثناء مناجاة الله", "fr": "Lever les mains en invoquant Allah"},
            "5": {"en": "Best times include last third of the night", "ar": "من أفضل أوقاته الثلث الأخير من الليل", "fr": "Les meilleurs moments incluent le dernier tiers de la nuit"},
            "6": {"en": "Personal supplication to Allah", "ar": "مناجاة شخصية لله", "fr": "Supplication personnelle à Allah"},
        },
        "explanation": {
            "en": "Dua is personal supplication to Allah — a direct conversation with the Creator without any intermediary. The Prophet called it 'the essence of worship' and taught that Allah is always near and responds to every call.",
            "ar": "الدعاء مناجاة شخصية لله — حوار مباشر مع الخالق بلا واسطة. سماه النبي 'مخ العبادة' وعلّم أن الله قريب يجيب دعوة الداعي.",
            "fr": "Le Dou'a est une supplication personnelle à Allah — une conversation directe avec le Créateur sans intermédiaire. Le Prophète l'a appelé 'l'essence de l'adoration' et a enseigné qu'Allah est toujours proche et répond à chaque appel.",
        },
    },
    {
        "word_en": "Dhikr",
        "word_ar": "ذكر",
        "word_fr": "Dhikr",
        "accepted_answers": {"en": ["Dhikr", "Thikr", "Remembrance"], "ar": ["ذكر", "الذكر"], "fr": ["Dhikr", "Rappel"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Brings peace to the heart", "ar": "يطمئن القلب", "fr": "Apporte la paix au cœur"},
            "2": {"en": "Can be done silently or aloud", "ar": "يمكن فعله سراً أو جهراً", "fr": "Peut être fait silencieusement ou à voix haute"},
            "3": {"en": "SubhanAllah, Alhamdulillah, Allahu Akbar are forms of this", "ar": "سبحان الله والحمد لله والله أكبر من صوره", "fr": "SubhanAllah, Alhamdulillah, Allahou Akbar en sont des formes"},
            "4": {"en": "The Quran says: by this do hearts find rest", "ar": "قال القرآن: ألا بذكر الله تطمئن القلوب", "fr": "Le Coran dit : par cela les cœurs trouvent le repos"},
            "5": {"en": "Morning and evening ones are recommended daily", "ar": "أذكار الصباح والمساء مستحبة يومياً", "fr": "Ceux du matin et du soir sont recommandés quotidiennement"},
            "6": {"en": "Remembrance of Allah", "ar": "ذكر الله", "fr": "Rappel d'Allah"},
        },
        "explanation": {
            "en": "Dhikr is the remembrance of Allah through phrases like SubhanAllah, Alhamdulillah, and Allahu Akbar. The Quran states that 'in the remembrance of Allah do hearts find tranquility,' making it a cornerstone of spiritual life.",
            "ar": "الذكر هو ذكر الله بعبارات مثل سبحان الله والحمد لله والله أكبر. يقول القرآن 'ألا بذكر الله تطمئن القلوب' مما يجعله ركيزة الحياة الروحية.",
            "fr": "Le Dhikr est le rappel d'Allah à travers des phrases comme SubhanAllah, Alhamdulillah et Allahu Akbar. Le Coran affirme que 'c'est dans le rappel d'Allah que les cœurs trouvent la tranquillité,' en faisant une pierre angulaire de la vie spirituelle.",
        },
    },
    {
        "word_en": "Jumuah",
        "word_ar": "جمعة",
        "word_fr": "Joumou'a",
        "accepted_answers": {"en": ["Jumuah", "Jumu'ah", "Jummah", "Jumurah", "Friday prayer"], "ar": ["جمعة", "الجمعة"], "fr": ["Joumou'a", "Joumouaa", "Joumoura", "Prière du vendredi"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "The best day of the week in Islam", "ar": "أفضل يوم في الأسبوع في الإسلام", "fr": "Le meilleur jour de la semaine en Islam"},
            "2": {"en": "Adam was created on this day", "ar": "خُلق آدم في هذا اليوم", "fr": "Adam a été créé ce jour-là"},
            "3": {"en": "Includes a special sermon (khutbah)", "ar": "يتضمن خطبة خاصة", "fr": "Comprend un sermon spécial (khoutba)"},
            "4": {"en": "There is a special hour when dua is accepted", "ar": "فيه ساعة يُستجاب فيها الدعاء", "fr": "Il y a une heure spéciale où les invocations sont acceptées"},
            "5": {"en": "Ghusl is recommended before attending", "ar": "يُستحب الاغتسال قبل الحضور", "fr": "Le ghusl est recommandé avant d'y assister"},
            "6": {"en": "The Friday congregational prayer (Salat al-Jumuah)", "ar": "صلاة الجمعة", "fr": "La prière du vendredi en congrégation"},
        },
        "explanation": {
            "en": "Jumuah (Friday prayer) is the weekly congregational prayer held every Friday, replacing the Dhuhr prayer. The Quran commands believers to hasten to the remembrance of Allah when called. It includes a khutbah (sermon).",
            "ar": "الجمعة صلاة جماعية أسبوعية كل يوم جمعة تحل محل صلاة الظهر. أمر القرآن المؤمنين بالسعي لذكر الله إذا نودي للصلاة وتشمل خطبة.",
            "fr": "Le Joumou'a (prière du vendredi) est la prière congregationnelle hebdomadaire tenue chaque vendredi, remplaçant la prière du Dhuhr. Le Coran ordonne aux croyants de se hâter vers le rappel d'Allah quand on les appelle. Elle inclut une khutbah (sermon).",
        },
    },
    {
        "word_en": "Miswak",
        "word_ar": "مسواك",
        "word_fr": "Miswak",
        "accepted_answers": {"en": ["Miswak", "Siwak"], "ar": ["مسواك", "سواك"], "fr": ["Miswak", "Siwak"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A Sunnah of the Prophet before an act of worship", "ar": "سنة نبوية قبل العبادة", "fr": "Une Sunnah du Prophète avant un acte d'adoration"},
            "2": {"en": "Comes from a tree", "ar": "يأتي من شجرة", "fr": "Provient d'un arbre"},
            "3": {"en": "Used for oral hygiene", "ar": "يُستخدم لنظافة الفم", "fr": "Utilisé pour l'hygiène buccale"},
            "4": {"en": "The Prophet said if it were not hard, he would command it", "ar": "لولا أن أشق على أمتي لأمرتهم به", "fr": "Le Prophète a dit que s'il n'était pas difficile, il l'ordonnerait"},
            "5": {"en": "Recommended before every prayer", "ar": "مستحب قبل كل صلاة", "fr": "Recommandé avant chaque prière"},
            "6": {"en": "Natural tooth-cleaning twig", "ar": "عود تنظيف الأسنان الطبيعي", "fr": "Bâtonnet naturel de nettoyage des dents"},
        },
        "explanation": {
            "en": "The Miswak is a teeth-cleaning twig from the Salvadora persica tree, used by the Prophet Muhammad. He said 'If it were not too difficult for my Ummah, I would have commanded them to use the Miswak before every prayer.'",
            "ar": "المسواك عود تنظيف أسنان من شجرة الأراك استخدمه النبي محمد. قال: 'لولا أن أشق على أمتي لأمرتهم بالسواك عند كل صلاة.'",
            "fr": "Le Miswak est une brindille de nettoyage des dents de l'arbre Salvadora persica, utilisée par le Prophète Muhammad. Il a dit : 'Si ce n'était pas trop difficile pour ma Oumma, je leur aurais ordonné d'utiliser le Miswak avant chaque prière.'",
        },
    },
    # === Places (New Category) ===
    {
        "word_en": "Makkah",
        "word_ar": "مكة",
        "word_fr": "La Mecque",
        "accepted_answers": {"en": ["Makkah", "Mecca"], "ar": ["مكة", "مكة المكرمة"], "fr": ["La Mecque", "Makkah"]},
        "category": "Places",
        "hints": {
            "1": {"en": "The holiest city in Islam", "ar": "أقدس مدينة في الإسلام", "fr": "La ville la plus sainte de l'Islam"},
            "2": {"en": "Located in a barren valley", "ar": "تقع في واد غير ذي زرع", "fr": "Située dans une vallée aride"},
            "3": {"en": "Birthplace of the Prophet", "ar": "مسقط رأس النبي", "fr": "Lieu de naissance du Prophète"},
            "4": {"en": "Millions visit it every year", "ar": "يزورها ملايين كل سنة", "fr": "Des millions la visitent chaque année"},
            "5": {"en": "Home of the Kaaba", "ar": "موطن الكعبة", "fr": "Foyer de la Kaaba"},
            "6": {"en": "City of the Sacred Mosque", "ar": "مدينة المسجد الحرام", "fr": "Ville de la Mosquée Sacrée"},
        },
        "explanation": {
            "en": "Makkah (Mecca) is the holiest city in Islam, birthplace of the Prophet Muhammad and home of the Kaaba. Muslims worldwide face Makkah in prayer, and millions perform Hajj there annually.",
            "ar": "مكة المكرمة أقدس مدينة في الإسلام ومسقط رأس النبي محمد وموطن الكعبة. يتوجه المسلمون حول العالم نحوها في الصلاة ويحج إليها الملايين سنوياً.",
            "fr": "La Mecque est la ville la plus sainte de l'Islam, lieu de naissance du Prophète Muhammad et foyer de la Kaaba. Les musulmans du monde entier se tournent vers La Mecque dans la prière, et des millions y accomplissent le Hajj chaque année.",
        },
    },
    {
        "word_en": "Madinah",
        "word_ar": "المدينة",
        "word_fr": "Médine",
        "accepted_answers": {"en": ["Madinah", "Medina"], "ar": ["المدينة", "المدينة المنورة"], "fr": ["Médine", "Madinah"]},
        "category": "Places",
        "hints": {
            "1": {"en": "The city that welcomed the Prophet", "ar": "المدينة التي استقبلت النبي", "fr": "La ville qui a accueilli le Prophète"},
            "2": {"en": "Home to the first Islamic state", "ar": "مقر أول دولة إسلامية", "fr": "Siège du premier État islamique"},
            "3": {"en": "A prayer there equals 1000 prayers elsewhere", "ar": "الصلاة فيها بألف صلاة", "fr": "Une prière là-bas équivaut à 1000 prières ailleurs"},
            "4": {"en": "The Prophet is buried here", "ar": "النبي مدفون فيها", "fr": "Le Prophète y est enterré"},
            "5": {"en": "Known as the Radiant City", "ar": "تُعرف بالمنورة", "fr": "Connue comme la Ville Radieuse"},
            "6": {"en": "The Illuminated City of the Prophet", "ar": "المدينة المنورة مدينة الرسول", "fr": "La Ville Illuminée du Prophète"},
        },
        "explanation": {
            "en": "Madinah (Medina) is the second holiest city in Islam, where the Prophet Muhammad migrated to and established the first Islamic state. It houses the Prophet's Mosque (Al-Masjid an-Nabawi) where he is buried.",
            "ar": "المدينة المنورة ثاني أقدس مدينة في الإسلام حيث هاجر إليها النبي وأسس أول دولة إسلامية. فيها المسجد النبوي حيث دُفن النبي.",
            "fr": "Médine est la deuxième ville la plus sainte de l'Islam, où le Prophète Muhammad a migré et établi le premier État islamique. Elle abrite la Mosquée du Prophète (Al-Masjid an-Nabawi) où il est enterré.",
        },
    },
    {
        "word_en": "Al-Aqsa",
        "word_ar": "الأقصى",
        "word_fr": "Al-Aqsa",
        "accepted_answers": {"en": ["Al-Aqsa", "Aqsa", "Masjid Al-Aqsa"], "ar": ["الأقصى", "المسجد الأقصى"], "fr": ["Al-Aqsa", "Mosquée Al-Aqsa"]},
        "category": "Places",
        "hints": {
            "1": {"en": "The third holiest site in Islam", "ar": "ثالث أقدس مكان في الإسلام", "fr": "Le troisième lieu le plus saint de l'Islam"},
            "2": {"en": "First qiblah of Muslims", "ar": "أولى القبلتين", "fr": "Première qibla des musulmans"},
            "3": {"en": "Located in a blessed land", "ar": "يقع في أرض مباركة", "fr": "Situé dans une terre bénie"},
            "4": {"en": "The Night Journey went to this place", "ar": "الإسراء كان إلى هذا المكان", "fr": "Le Voyage Nocturne allait vers ce lieu"},
            "5": {"en": "In the city of Jerusalem", "ar": "في مدينة القدس", "fr": "Dans la ville de Jérusalem"},
            "6": {"en": "The Farthest Mosque", "ar": "المسجد الأقصى", "fr": "La Mosquée la Plus Éloignée"},
        },
        "explanation": {
            "en": "Al-Aqsa Mosque in Jerusalem is the third holiest site in Islam. It was the first qiblah (prayer direction) and the destination of the Prophet's Night Journey (Isra). Prayer there is worth 500 times more than elsewhere.",
            "ar": "المسجد الأقصى في القدس ثالث أقدس موقع في الإسلام. كان أول قبلة للمسلمين ووجهة رحلة الإسراء. الصلاة فيه تعادل 500 صلاة.",
            "fr": "La Mosquée Al-Aqsa à Jérusalem est le troisième lieu le plus saint de l'Islam. C'était la première qibla (direction de prière) et la destination du Voyage Nocturne du Prophète (Isra). La prière y vaut 500 fois plus qu'ailleurs.",
        },
    },
    {
        "word_en": "Hira",
        "word_ar": "حراء",
        "word_fr": "Hira",
        "accepted_answers": {"en": ["Hira", "Cave of Hira", "Ghar Hira"], "ar": ["حراء", "غار حراء"], "fr": ["Hira", "Grotte de Hira"]},
        "category": "Places",
        "hints": {
            "1": {"en": "A place of solitude and reflection", "ar": "مكان للعزلة والتأمل", "fr": "Un lieu de solitude et de réflexion"},
            "2": {"en": "Located on a mountain near a holy city", "ar": "يقع على جبل قرب مدينة مقدسة", "fr": "Situé sur une montagne près d'une ville sainte"},
            "3": {"en": "The Prophet used to go there to meditate", "ar": "كان النبي يذهب إليه للتأمل", "fr": "Le Prophète y allait pour méditer"},
            "4": {"en": "The angel Jibreel appeared here", "ar": "ظهر الملك جبريل هنا", "fr": "L'ange Jibreel est apparu ici"},
            "5": {"en": "Iqra — Read — was the first word revealed here", "ar": "اقرأ — كانت أول كلمة أُنزلت هنا", "fr": "Iqra — Lis — fut le premier mot révélé ici"},
            "6": {"en": "Where the first Quran revelation came", "ar": "حيث نزل أول وحي قرآني", "fr": "Où la première révélation coranique est venue"},
        },
        "explanation": {
            "en": "Hira is a cave on Jabal al-Nour (Mountain of Light) near Makkah where the Prophet Muhammad used to retreat for meditation. It was here that the angel Jibreel first appeared and revealed the opening verses of Surah Al-Alaq: 'Read!'",
            "ar": "حراء غار على جبل النور قرب مكة كان النبي محمد يعتكف فيه للتأمل. هنا ظهر جبريل لأول مرة وأنزل أول آيات سورة العلق: 'اقرأ!'",
            "fr": "Hira est une grotte sur le Jabal al-Nour (Montagne de Lumière) près de La Mecque où le Prophète Muhammad se retirait pour méditer. C'est là que l'ange Jibreel apparut pour la première fois et révéla les premiers versets de la sourate Al-Alaq : 'Lis !'",
        },
    },
    # === New entries: Islamic Concepts ===
    {
        "word_en": "Shahada",
        "word_ar": "شهادة",
        "word_fr": "Chahada",
        "accepted_answers": {"en": ["Shahada", "Shahadah"], "ar": ["شهادة", "الشهادة"], "fr": ["Chahada", "Shahada"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "The most fundamental statement in Islam", "ar": "أهم عبارة في الإسلام", "fr": "La déclaration la plus fondamentale de l'Islam"},
            "2": {"en": "It is the first pillar of Islam", "ar": "الركن الأول من أركان الإسلام", "fr": "C'est le premier pilier de l'Islam"},
            "3": {"en": "Whispered into a newborn's ear", "ar": "تُهمس في أذن المولود", "fr": "Chuchotée à l'oreille d'un nouveau-né"},
            "4": {"en": "Contains two parts: about Allah and His Messenger", "ar": "تحتوي جزأين: عن الله ورسوله", "fr": "Contient deux parties : sur Allah et Son Messager"},
            "5": {"en": "La ilaha illa Allah...", "ar": "لا إله إلا الله...", "fr": "La ilaha illa Allah..."},
            "6": {"en": "The declaration of faith", "ar": "إعلان الإيمان", "fr": "La déclaration de foi"},
        },
        "explanation": {
            "en": "The Shahada is the Islamic declaration of faith: 'There is no god but Allah, and Muhammad is the Messenger of Allah.' It is the first pillar of Islam and the most important statement a Muslim makes, recited to enter the faith.",
            "ar": "الشهادة هي إعلان الإيمان الإسلامي: 'لا إله إلا الله محمد رسول الله.' هي الركن الأول من أركان الإسلام وأهم عبارة ينطقها المسلم وتُقال للدخول في الإسلام.",
            "fr": "La Chahada est la déclaration de foi islamique : 'Il n'y a de dieu qu'Allah et Muhammad est le Messager d'Allah.' C'est le premier pilier de l'Islam et la déclaration la plus importante qu'un musulman fait, récitée pour entrer dans la foi.",
        },
    },
    {
        "word_en": "Sunnah",
        "word_ar": "سنة",
        "word_fr": "Sunna",
        "accepted_answers": {"en": ["Sunnah", "Sunna"], "ar": ["سنة", "السنة", "سنّة"], "fr": ["Sunna", "Sunnah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A major source of Islamic guidance alongside the Quran", "ar": "مصدر رئيسي للتوجيه الإسلامي إلى جانب القرآن", "fr": "Une source majeure de guidance islamique aux côtés du Coran"},
            "2": {"en": "Preserved through hadiths", "ar": "محفوظة من خلال الأحاديث", "fr": "Préservée à travers les hadiths"},
            "3": {"en": "Includes sayings, actions, and approvals", "ar": "تشمل الأقوال والأفعال والتقريرات", "fr": "Comprend les paroles, les actes et les approbations"},
            "4": {"en": "Scholars like Bukhari and Muslim compiled it", "ar": "جمعها علماء مثل البخاري ومسلم", "fr": "Des savants comme Bukhari et Muslim l'ont compilée"},
            "5": {"en": "Following it is highly recommended", "ar": "اتباعها مستحب جداً", "fr": "La suivre est hautement recommandé"},
            "6": {"en": "The prophetic tradition and way of life", "ar": "الطريقة النبوية والمنهج", "fr": "La tradition prophétique et mode de vie"},
        },
        "explanation": {
            "en": "The Sunnah refers to the teachings, practices, and approvals of Prophet Muhammad, preserved in hadiths. It is the second source of Islamic law after the Quran, covering everything from worship to daily etiquette.",
            "ar": "السنة تشير إلى تعاليم النبي محمد وممارساته وتقريراته المحفوظة في الأحاديث. هي المصدر الثاني للتشريع الإسلامي بعد القرآن وتغطي كل شيء من العبادة إلى آداب الحياة اليومية.",
            "fr": "La Sunna désigne les enseignements, pratiques et approbations du Prophète Muhammad, préservés dans les hadiths. C'est la deuxième source de droit islamique après le Coran, couvrant tout, de l'adoration à l'étiquette quotidienne.",
        },
    },
    {
        "word_en": "Ummah",
        "word_ar": "أمة",
        "word_fr": "Oumma",
        "accepted_answers": {"en": ["Ummah", "Umma"], "ar": ["أمة", "الأمة"], "fr": ["Oumma", "Ummah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "A concept that transcends borders and ethnicities", "ar": "مفهوم يتجاوز الحدود والأعراق", "fr": "Un concept qui transcende les frontières et les ethnies"},
            "2": {"en": "Nearly 2 billion people belong to it", "ar": "ينتمي إليها نحو ملياري شخص", "fr": "Près de 2 milliards de personnes y appartiennent"},
            "3": {"en": "The Prophet compared it to one body", "ar": "شبّهها النبي بالجسد الواحد", "fr": "Le Prophète l'a comparée à un seul corps"},
            "4": {"en": "United by faith, not nationality", "ar": "متحدة بالإيمان لا بالجنسية", "fr": "Unie par la foi, pas par la nationalité"},
            "5": {"en": "The global brotherhood and sisterhood", "ar": "الأخوة والأختية العالمية", "fr": "La fraternité et la sororité mondiales"},
            "6": {"en": "The Muslim community worldwide", "ar": "المجتمع الإسلامي العالمي", "fr": "La communauté musulmane mondiale"},
        },
        "explanation": {
            "en": "The Ummah is the global Muslim community, bound together by shared faith regardless of nationality, ethnicity, or language. The Prophet described it as one body — when one part suffers, the whole body responds with sleeplessness and fever.",
            "ar": "الأمة هي المجتمع الإسلامي العالمي المترابط بالإيمان بغض النظر عن الجنسية أو العرق أو اللغة. وصفها النبي بالجسد الواحد — إذا اشتكى منه عضو تداعى له سائر الجسد.",
            "fr": "L'Oumma est la communauté musulmane mondiale, liée par une foi partagée indépendamment de la nationalité, de l'ethnicité ou de la langue. Le Prophète l'a décrite comme un seul corps — quand une partie souffre, tout le corps répond par l'insomnie et la fièvre.",
        },
    },
    {
        "word_en": "Qadr",
        "word_ar": "قدر",
        "word_fr": "Qadr",
        "accepted_answers": {"en": ["Qadr", "Qadar", "Qader"], "ar": ["قدر", "القدر"], "fr": ["Qadr", "Qadar"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "One of the six pillars of faith (Iman)", "ar": "من أركان الإيمان الستة", "fr": "Un des six piliers de la foi (Iman)"},
            "2": {"en": "Related to Allah's knowledge of all things", "ar": "متعلق بعلم الله لكل شيء", "fr": "Lié à la connaissance d'Allah de toutes choses"},
            "3": {"en": "Nothing happens outside of it", "ar": "لا شيء يحدث خارجه", "fr": "Rien ne se passe en dehors de cela"},
            "4": {"en": "Includes both good and difficult events", "ar": "يشمل الخير والشر", "fr": "Inclut les bons et les difficiles événements"},
            "5": {"en": "Laylat al-... is the Night of Power", "ar": "ليلة ال... هي ليلة القدر", "fr": "Laylat al-... est la Nuit du Destin"},
            "6": {"en": "Divine decree and predestination", "ar": "القضاء والقدر", "fr": "Le décret divin et la prédestination"},
        },
        "explanation": {
            "en": "Qadr (Divine Decree) is the belief that Allah has knowledge of and has ordained everything that will happen. It is one of the six pillars of Iman. Belief in Qadr brings peace in hardship, knowing everything occurs by Allah's wisdom.",
            "ar": "القدر هو الإيمان بأن الله يعلم كل ما سيحدث وقد قدّره. وهو من أركان الإيمان الستة. الإيمان بالقدر يمنح السكينة في الشدائد علماً بأن كل شيء يجري بحكمة الله.",
            "fr": "Le Qadr (Décret Divin) est la croyance qu'Allah a la connaissance de tout ce qui arrivera et l'a ordonné. C'est l'un des six piliers de l'Iman. La croyance au Qadr apporte la paix dans l'adversité, sachant que tout se produit par la sagesse d'Allah.",
        },
    },
    {
        "word_en": "Baraka",
        "word_ar": "بركة",
        "word_fr": "Baraka",
        "accepted_answers": {"en": ["Baraka", "Barakah"], "ar": ["بركة", "البركة"], "fr": ["Baraka", "Barakah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "Something intangible that increases goodness", "ar": "شيء غير ملموس يزيد الخير", "fr": "Quelque chose d'intangible qui augmente le bien"},
            "2": {"en": "Found in certain times, places, and people", "ar": "توجد في أوقات وأماكن وأشخاص معينين", "fr": "Se trouve dans certains moments, lieux et personnes"},
            "3": {"en": "The Prophet's food was said to have it", "ar": "قيل إن طعام النبي كان فيه منها", "fr": "On dit que la nourriture du Prophète en avait"},
            "4": {"en": "Zamzam water is full of it", "ar": "ماء زمزم ممتلئ بها", "fr": "L'eau de Zamzam en est pleine"},
            "5": {"en": "We say 'may Allah put ... in it'", "ar": "نقول 'بارك الله فيه'", "fr": "On dit 'qu'Allah y mette de la ...'"},
            "6": {"en": "Divine blessing and spiritual abundance", "ar": "بركة إلهية ووفرة روحية", "fr": "Bénédiction divine et abondance spirituelle"},
        },
        "explanation": {
            "en": "Baraka is a divine blessing that brings abundance, growth, and goodness beyond what is expected. Muslims seek it in prayer, in the Quran, in Ramadan, and in acts of kindness. It can make a little go a long way.",
            "ar": "البركة نعمة إلهية تجلب الوفرة والنماء والخير فوق المتوقع. يلتمسها المسلمون في الصلاة والقرآن ورمضان وأعمال الخير. تجعل القليل يكفي ويزيد.",
            "fr": "La Baraka est une bénédiction divine qui apporte abondance, croissance et bien au-delà de ce qui est attendu. Les musulmans la cherchent dans la prière, le Coran, le Ramadan et les actes de bonté. Elle peut faire qu'un peu suffise largement.",
        },
    },
    {
        "word_en": "Tawbah",
        "word_ar": "توبة",
        "word_fr": "Tawba",
        "accepted_answers": {"en": ["Tawbah", "Tawba", "Taubah"], "ar": ["توبة", "التوبة"], "fr": ["Tawba", "Tawbah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "Allah loves those who do this sincerely", "ar": "الله يحب من يفعل هذا بإخلاص", "fr": "Allah aime ceux qui font cela sincèrement"},
            "2": {"en": "A surah in the Quran bears this name", "ar": "سورة في القرآن تحمل هذا الاسم", "fr": "Une sourate du Coran porte ce nom"},
            "3": {"en": "It involves regret, stopping, and resolving not to return", "ar": "تتضمن الندم والتوقف والعزم على عدم العودة", "fr": "Elle implique le regret, l'arrêt et la résolution de ne pas revenir"},
            "4": {"en": "The door of this is always open", "ar": "بابها مفتوح دائماً", "fr": "La porte de cela est toujours ouverte"},
            "5": {"en": "Turning back to Allah after sin", "ar": "العودة إلى الله بعد الذنب", "fr": "Retourner vers Allah après le péché"},
            "6": {"en": "Repentance", "ar": "التوبة", "fr": "Le repentir"},
        },
        "explanation": {
            "en": "Tawbah is sincere repentance — turning back to Allah after committing a sin. It requires genuine regret, ceasing the sin, and resolving not to return to it. Allah says He loves those who repent, and His mercy is always available.",
            "ar": "التوبة هي العودة الصادقة إلى الله بعد ارتكاب الذنب. تتطلب ندماً حقيقياً والتوقف عن الذنب والعزم على عدم العودة إليه. يقول الله إنه يحب التوابين ورحمته متاحة دائماً.",
            "fr": "La Tawba est le repentir sincère — le retour vers Allah après avoir commis un péché. Elle nécessite un regret sincère, l'arrêt du péché et la résolution de ne pas y revenir. Allah dit qu'Il aime ceux qui se repentent, et Sa miséricorde est toujours disponible.",
        },
    },
    {
        "word_en": "Shukr",
        "word_ar": "شكر",
        "word_fr": "Choukr",
        "accepted_answers": {"en": ["Shukr", "Shukur"], "ar": ["شكر", "الشكر"], "fr": ["Choukr", "Shukr"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "The opposite of ingratitude", "ar": "عكس الجحود", "fr": "L'opposé de l'ingratitude"},
            "2": {"en": "Allah promises more for those who practice it", "ar": "وعد الله بالزيادة لمن يمارسه", "fr": "Allah promet plus à ceux qui le pratiquent"},
            "3": {"en": "'If you are ... I will increase you'", "ar": "'لئن شكرتم لأزيدنكم'", "fr": "'Si vous êtes ... Je vous augmenterai'"},
            "4": {"en": "Expressed by the heart, tongue, and limbs", "ar": "يُعبّر عنه بالقلب واللسان والجوارح", "fr": "Exprimé par le cœur, la langue et les membres"},
            "5": {"en": "Alhamdulillah is an expression of this", "ar": "الحمد لله تعبير عن هذا", "fr": "Alhamdulillah est une expression de cela"},
            "6": {"en": "Gratitude to Allah", "ar": "الامتنان لله", "fr": "La gratitude envers Allah"},
        },
        "explanation": {
            "en": "Shukr (gratitude) is a core Islamic virtue. The Quran states: 'If you are grateful, I will increase you.' True Shukr involves the heart (recognizing blessings), the tongue (praising Allah), and the limbs (using blessings in obedience).",
            "ar": "الشكر فضيلة إسلامية أساسية. يقول القرآن: 'لئن شكرتم لأزيدنكم.' الشكر الحقيقي يشمل القلب (إدراك النعم) واللسان (حمد الله) والجوارح (استعمال النعم في الطاعة).",
            "fr": "Le Choukr (gratitude) est une vertu islamique fondamentale. Le Coran déclare : 'Si vous êtes reconnaissants, Je vous augmenterai.' Le vrai Choukr implique le cœur (reconnaître les bienfaits), la langue (louer Allah) et les membres (utiliser les bienfaits dans l'obéissance).",
        },
    },
    {
        "word_en": "Niyyah",
        "word_ar": "نية",
        "word_fr": "Niyyah",
        "accepted_answers": {"en": ["Niyyah", "Niyya", "Niya"], "ar": ["نية", "النية"], "fr": ["Niyyah", "Niya"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "The Prophet said actions are judged by this", "ar": "قال النبي إنما الأعمال بها", "fr": "Le Prophète a dit que les actes sont jugés par cela"},
            "2": {"en": "It is in the heart, not spoken aloud", "ar": "محلها القلب لا اللسان", "fr": "Elle est dans le cœur, pas prononcée à voix haute"},
            "3": {"en": "It distinguishes worship from habit", "ar": "تميز العبادة عن العادة", "fr": "Elle distingue l'adoration de l'habitude"},
            "4": {"en": "Required before every act of worship", "ar": "مطلوبة قبل كل عبادة", "fr": "Requise avant chaque acte d'adoration"},
            "5": {"en": "Without it, a good deed may have no reward", "ar": "بدونها قد لا يكون للعمل الصالح أجر", "fr": "Sans elle, une bonne action peut ne pas avoir de récompense"},
            "6": {"en": "Intention", "ar": "النية", "fr": "L'intention"},
        },
        "explanation": {
            "en": "Niyyah (intention) is the cornerstone of all deeds in Islam. The famous hadith states: 'Actions are judged by intentions.' A sincere intention transforms everyday actions like eating and sleeping into acts of worship.",
            "ar": "النية حجر الزاوية لكل الأعمال في الإسلام. يقول الحديث الشهير: 'إنما الأعمال بالنيات.' النية الصادقة تحول الأعمال اليومية كالأكل والنوم إلى عبادات.",
            "fr": "La Niyyah (intention) est la pierre angulaire de tous les actes en Islam. Le célèbre hadith déclare : 'Les actes ne valent que par les intentions.' Une intention sincère transforme les actions quotidiennes comme manger et dormir en actes d'adoration.",
        },
    },
    {
        "word_en": "Fitrah",
        "word_ar": "فطرة",
        "word_fr": "Fitra",
        "accepted_answers": {"en": ["Fitrah", "Fitra"], "ar": ["فطرة", "الفطرة"], "fr": ["Fitra", "Fitrah"]},
        "category": "Islamic Concepts",
        "hints": {
            "1": {"en": "Every child is born upon this", "ar": "كل مولود يُولد عليها", "fr": "Chaque enfant naît avec cela"},
            "2": {"en": "An innate quality within every human", "ar": "صفة فطرية في كل إنسان", "fr": "Une qualité innée chez chaque être humain"},
            "3": {"en": "It recognizes the Creator instinctively", "ar": "تتعرف على الخالق بالفطرة", "fr": "Elle reconnaît le Créateur instinctivement"},
            "4": {"en": "The environment can alter it over time", "ar": "البيئة يمكن أن تغيرها مع الوقت", "fr": "L'environnement peut l'altérer avec le temps"},
            "5": {"en": "The pure, original state of being", "ar": "الحالة الأصلية النقية", "fr": "L'état pur et originel de l'être"},
            "6": {"en": "Natural disposition toward God", "ar": "الميل الطبيعي نحو الله", "fr": "La disposition naturelle vers Dieu"},
        },
        "explanation": {
            "en": "Fitrah is the natural, innate disposition that every human is born with — an instinctive recognition of Allah. The Prophet said every child is born upon the Fitrah. It represents humanity's original, pure state of believing in one God.",
            "ar": "الفطرة هي الطبيعة الفطرية التي يُولد عليها كل إنسان — إدراك غريزي لوجود الله. قال النبي إن كل مولود يُولد على الفطرة. تمثل الحالة الأصلية النقية للإيمان بالله الواحد.",
            "fr": "La Fitra est la disposition naturelle innée avec laquelle chaque être humain naît — une reconnaissance instinctive d'Allah. Le Prophète a dit que chaque enfant naît sur la Fitra. Elle représente l'état originel et pur de l'humanité croyant en un seul Dieu.",
        },
    },
    # === New entries: Daily Life ===
    {
        "word_en": "Quran",
        "word_ar": "قرآن",
        "word_fr": "Coran",
        "accepted_answers": {"en": ["Quran", "Qur'an", "Koran"], "ar": ["قرآن", "القرآن"], "fr": ["Coran", "Quran"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "The most read book in the world", "ar": "أكثر كتاب يُقرأ في العالم", "fr": "Le livre le plus lu au monde"},
            "2": {"en": "Revealed over a period of 23 years", "ar": "أُنزل على مدى 23 سنة", "fr": "Révélé sur une période de 23 ans"},
            "3": {"en": "Contains 114 surahs", "ar": "يحتوي على 114 سورة", "fr": "Contient 114 sourates"},
            "4": {"en": "Millions memorize it entirely by heart", "ar": "الملايين يحفظونه كاملاً عن ظهر قلب", "fr": "Des millions le mémorisent entièrement par cœur"},
            "5": {"en": "Revealed through the angel Jibreel", "ar": "أُنزل عبر الملك جبريل", "fr": "Révélé par l'ange Jibreel"},
            "6": {"en": "The holy book of Islam", "ar": "الكتاب المقدس في الإسلام", "fr": "Le livre saint de l'Islam"},
        },
        "explanation": {
            "en": "The Quran is the literal word of Allah revealed to Prophet Muhammad through the angel Jibreel over 23 years. It contains 114 surahs and is the primary source of Islamic guidance. It has been perfectly preserved in its original Arabic since revelation.",
            "ar": "القرآن كلام الله الحرفي أُنزل على النبي محمد عبر جبريل على مدى 23 سنة. يحتوي 114 سورة وهو المصدر الأساسي للتوجيه الإسلامي. حُفظ بكماله بالعربية منذ نزوله.",
            "fr": "Le Coran est la parole littérale d'Allah révélée au Prophète Muhammad par l'ange Jibreel sur 23 ans. Il contient 114 sourates et est la source principale de guidance islamique. Il a été parfaitement préservé dans son arabe original depuis la révélation.",
        },
    },
    {
        "word_en": "Ramadan",
        "word_ar": "رمضان",
        "word_fr": "Ramadan",
        "accepted_answers": {"en": ["Ramadan", "Ramadhan"], "ar": ["رمضان"], "fr": ["Ramadan"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A month that Muslims wait for all year", "ar": "شهر ينتظره المسلمون طوال العام", "fr": "Un mois que les musulmans attendent toute l'année"},
            "2": {"en": "The Quran was first revealed during it", "ar": "نزل القرآن لأول مرة خلاله", "fr": "Le Coran a été révélé pour la première fois pendant ce mois"},
            "3": {"en": "Fasting from dawn to sunset", "ar": "صيام من الفجر إلى الغروب", "fr": "Jeûne de l'aube au coucher du soleil"},
            "4": {"en": "The gates of paradise are opened", "ar": "تُفتح أبواب الجنة", "fr": "Les portes du paradis sont ouvertes"},
            "5": {"en": "Contains Laylat al-Qadr", "ar": "فيه ليلة القدر", "fr": "Contient Laylat al-Qadr"},
            "6": {"en": "The holy month of fasting", "ar": "شهر الصيام المبارك", "fr": "Le mois sacré du jeûne"},
        },
        "explanation": {
            "en": "Ramadan is the ninth month of the Islamic calendar during which Muslims fast from dawn to sunset. It commemorates the first revelation of the Quran and contains Laylat al-Qadr (Night of Power), which is better than a thousand months.",
            "ar": "رمضان الشهر التاسع من التقويم الهجري يصوم فيه المسلمون من الفجر إلى الغروب. يحتفي بنزول القرآن الأول وفيه ليلة القدر التي هي خير من ألف شهر.",
            "fr": "Le Ramadan est le neuvième mois du calendrier islamique pendant lequel les musulmans jeûnent de l'aube au coucher du soleil. Il commémore la première révélation du Coran et contient Laylat al-Qadr (Nuit du Destin), qui vaut mieux que mille mois.",
        },
    },
    {
        "word_en": "Eid",
        "word_ar": "عيد",
        "word_fr": "Aïd",
        "accepted_answers": {"en": ["Eid", "Eid al-Fitr", "Eid al-Adha"], "ar": ["عيد", "العيد"], "fr": ["Aïd", "Eid"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A joyous occasion celebrated by all Muslims", "ar": "مناسبة سعيدة يحتفل بها جميع المسلمين", "fr": "Une occasion joyeuse célébrée par tous les musulmans"},
            "2": {"en": "There are two of them each year", "ar": "هناك اثنان منه كل عام", "fr": "Il y en a deux chaque année"},
            "3": {"en": "One follows Ramadan, the other during Hajj", "ar": "واحد بعد رمضان والآخر في الحج", "fr": "L'un suit le Ramadan, l'autre pendant le Hajj"},
            "4": {"en": "Special prayer is performed in the morning", "ar": "تُصلى صلاة خاصة في الصباح", "fr": "Une prière spéciale est effectuée le matin"},
            "5": {"en": "New clothes, gifts, and family gatherings", "ar": "ملابس جديدة وهدايا واجتماعات عائلية", "fr": "Nouveaux vêtements, cadeaux et réunions familiales"},
            "6": {"en": "Islamic celebration and holiday", "ar": "احتفال إسلامي وعطلة", "fr": "Célébration et fête islamique"},
        },
        "explanation": {
            "en": "Eid refers to the two major Islamic holidays: Eid al-Fitr (after Ramadan) and Eid al-Adha (during Hajj). Both involve special prayers, charity, family gatherings, and celebrations. The Prophet said these are the two days Allah has given Muslims for celebration.",
            "ar": "العيد يشير إلى عيدين إسلاميين: عيد الفطر (بعد رمضان) وعيد الأضحى (في الحج). كلاهما يتضمن صلاة خاصة وصدقة واجتماعات عائلية واحتفالات. قال النبي إنهما اليومان اللذان جعلهما الله للمسلمين.",
            "fr": "L'Aïd désigne les deux grandes fêtes islamiques : l'Aïd al-Fitr (après le Ramadan) et l'Aïd al-Adha (pendant le Hajj). Les deux comprennent des prières spéciales, la charité, des réunions familiales et des célébrations. Le Prophète a dit que ce sont les deux jours qu'Allah a donnés aux musulmans pour célébrer.",
        },
    },
    {
        "word_en": "Ihram",
        "word_ar": "إحرام",
        "word_fr": "Ihram",
        "accepted_answers": {"en": ["Ihram"], "ar": ["إحرام", "الإحرام"], "fr": ["Ihram"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A sacred state entered for a special journey", "ar": "حالة مقدسة يُدخل فيها لرحلة خاصة", "fr": "Un état sacré dans lequel on entre pour un voyage spécial"},
            "2": {"en": "Involves wearing specific unstitched garments", "ar": "يتضمن ارتداء ملابس غير مخيطة", "fr": "Implique le port de vêtements non cousus spécifiques"},
            "3": {"en": "White cloth symbolizing equality", "ar": "قماش أبيض يرمز للمساواة", "fr": "Tissu blanc symbolisant l'égalité"},
            "4": {"en": "Certain actions become forbidden in this state", "ar": "تحرم بعض الأفعال في هذه الحالة", "fr": "Certaines actions deviennent interdites dans cet état"},
            "5": {"en": "Required for Hajj and Umrah", "ar": "مطلوب للحج والعمرة", "fr": "Requis pour le Hajj et la Omra"},
            "6": {"en": "The pilgrimage garment and sacred state", "ar": "لباس الحج والحالة المقدسة", "fr": "Le vêtement de pèlerinage et l'état sacré"},
        },
        "explanation": {
            "en": "Ihram is both the sacred state a Muslim enters for Hajj or Umrah and the simple white garments worn. Men wear two unstitched white cloths, symbolizing equality — king and servant stand side by side, indistinguishable before Allah.",
            "ar": "الإحرام هو الحالة المقدسة التي يدخلها المسلم للحج أو العمرة وكذلك اللباس الأبيض البسيط. يرتدي الرجال قطعتين بيضاوين غير مخيطتين رمزاً للمساواة — الملك والخادم يقفان جنباً إلى جنب.",
            "fr": "L'Ihram est à la fois l'état sacré dans lequel un musulman entre pour le Hajj ou la Omra et les simples vêtements blancs portés. Les hommes portent deux pièces de tissu blanc non cousues, symbolisant l'égalité — roi et serviteur se tiennent côte à côte, indiscernables devant Allah.",
        },
    },
    {
        "word_en": "Tawaf",
        "word_ar": "طواف",
        "word_fr": "Tawaf",
        "accepted_answers": {"en": ["Tawaf"], "ar": ["طواف", "الطواف"], "fr": ["Tawaf"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A ritual involving circular movement", "ar": "شعيرة تتضمن حركة دائرية", "fr": "Un rituel impliquant un mouvement circulaire"},
            "2": {"en": "Performed around the most sacred structure in Islam", "ar": "يُؤدى حول أقدس بناء في الإسلام", "fr": "Effectué autour de la structure la plus sacrée de l'Islam"},
            "3": {"en": "Done seven times counterclockwise", "ar": "يُفعل سبع مرات عكس عقارب الساعة", "fr": "Fait sept fois dans le sens inverse des aiguilles d'une montre"},
            "4": {"en": "Pilgrims recite prayers while doing it", "ar": "يردد الحجاج الأدعية أثناء أدائه", "fr": "Les pèlerins récitent des prières en le faisant"},
            "5": {"en": "Part of both Hajj and Umrah", "ar": "جزء من الحج والعمرة", "fr": "Fait partie du Hajj et de la Omra"},
            "6": {"en": "Circling the Kaaba", "ar": "الطواف حول الكعبة", "fr": "Tourner autour de la Kaaba"},
        },
        "explanation": {
            "en": "Tawaf is the ritual of circling the Kaaba seven times counterclockwise during Hajj or Umrah. It symbolizes the unity of believers in worship and their devotion to Allah. The tradition dates back to Prophet Ibrahim who built the Kaaba.",
            "ar": "الطواف شعيرة الدوران حول الكعبة سبع مرات عكس عقارب الساعة في الحج أو العمرة. يرمز لوحدة المؤمنين في العبادة وتفانيهم لله. يعود التقليد للنبي إبراهيم الذي بنى الكعبة.",
            "fr": "Le Tawaf est le rituel de tourner autour de la Kaaba sept fois dans le sens inverse des aiguilles d'une montre pendant le Hajj ou la Omra. Il symbolise l'unité des croyants dans l'adoration et leur dévotion à Allah. La tradition remonte au Prophète Ibrahim qui a construit la Kaaba.",
        },
    },
    {
        "word_en": "Qiblah",
        "word_ar": "قبلة",
        "word_fr": "Qibla",
        "accepted_answers": {"en": ["Qiblah", "Qibla", "Kiblah"], "ar": ["قبلة", "القبلة"], "fr": ["Qibla", "Qiblah"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Every mosque in the world is oriented toward it", "ar": "كل مسجد في العالم موجه نحوها", "fr": "Chaque mosquée du monde est orientée vers elle"},
            "2": {"en": "It was changed during the Prophet's lifetime", "ar": "تغيرت في حياة النبي", "fr": "Elle a été changée du vivant du Prophète"},
            "3": {"en": "Originally toward Jerusalem, then changed", "ar": "كانت نحو القدس ثم تغيرت", "fr": "À l'origine vers Jérusalem, puis changée"},
            "4": {"en": "A compass or app can help you find it", "ar": "بوصلة أو تطبيق يمكن أن يساعدك في إيجادها", "fr": "Une boussole ou une application peut vous aider à la trouver"},
            "5": {"en": "Points toward the Kaaba in Makkah", "ar": "تشير نحو الكعبة في مكة", "fr": "Pointe vers la Kaaba à La Mecque"},
            "6": {"en": "The direction of prayer", "ar": "اتجاه الصلاة", "fr": "La direction de la prière"},
        },
        "explanation": {
            "en": "The Qiblah is the direction Muslims face during prayer, pointing toward the Kaaba in Makkah. Initially, Muslims prayed toward Jerusalem, but the Qiblah was changed to Makkah about 16 months after the Hijra, as mentioned in Surah Al-Baqarah.",
            "ar": "القبلة هي الاتجاه الذي يتوجه إليه المسلمون في الصلاة نحو الكعبة في مكة. في البداية صلى المسلمون نحو القدس ثم تحولت القبلة إلى مكة بعد نحو 16 شهراً من الهجرة كما في سورة البقرة.",
            "fr": "La Qibla est la direction vers laquelle les musulmans se tournent pendant la prière, pointant vers la Kaaba à La Mecque. Initialement, les musulmans priaient vers Jérusalem, mais la Qibla fut changée vers La Mecque environ 16 mois après la Hijra, comme mentionné dans la sourate Al-Baqarah.",
        },
    },
    {
        "word_en": "Minbar",
        "word_ar": "منبر",
        "word_fr": "Minbar",
        "accepted_answers": {"en": ["Minbar", "Mimbar"], "ar": ["منبر", "المنبر"], "fr": ["Minbar"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "Found in every mosque", "ar": "موجود في كل مسجد", "fr": "Trouvé dans chaque mosquée"},
            "2": {"en": "The imam stands on it for a weekly address", "ar": "يقف عليه الإمام لخطبة أسبوعية", "fr": "L'imam s'y tient pour un discours hebdomadaire"},
            "3": {"en": "Usually has stairs or steps", "ar": "عادة ما يحتوي على درجات", "fr": "A généralement des marches ou des escaliers"},
            "4": {"en": "The Prophet's original one was simple, with three steps", "ar": "كان منبر النبي بسيطاً من ثلاث درجات", "fr": "Celui du Prophète était simple, avec trois marches"},
            "5": {"en": "Used during the Friday sermon", "ar": "يُستخدم أثناء خطبة الجمعة", "fr": "Utilisé pendant le sermon du vendredi"},
            "6": {"en": "The mosque pulpit", "ar": "منبر المسجد", "fr": "La chaire de la mosquée"},
        },
        "explanation": {
            "en": "The Minbar is the pulpit in a mosque from which the imam delivers the Friday khutbah (sermon). The Prophet's original minbar had just three simple wooden steps. Today, minbars are often beautifully crafted and are a distinctive feature of mosque architecture.",
            "ar": "المنبر هو المكان الذي يخطب منه الإمام خطبة الجمعة في المسجد. كان منبر النبي من ثلاث درجات خشبية بسيطة. اليوم تُصنع المنابر بإتقان وهي سمة مميزة لعمارة المساجد.",
            "fr": "Le Minbar est la chaire dans une mosquée depuis laquelle l'imam délivre la khutbah (sermon) du vendredi. Le minbar original du Prophète n'avait que trois marches en bois simples. Aujourd'hui, les minbars sont souvent magnifiquement façonnés et sont un élément distinctif de l'architecture des mosquées.",
        },
    },
    {
        "word_en": "Ghusl",
        "word_ar": "غسل",
        "word_fr": "Ghousl",
        "accepted_answers": {"en": ["Ghusl", "Ghusul"], "ar": ["غسل", "الغسل"], "fr": ["Ghousl", "Ghusl"]},
        "category": "Daily Life",
        "hints": {
            "1": {"en": "A purification ritual more thorough than Wudu", "ar": "طهارة أشمل من الوضوء", "fr": "Un rituel de purification plus complet que le Woudou"},
            "2": {"en": "Required after certain physical states", "ar": "مطلوب بعد حالات جسدية معينة", "fr": "Requis après certains états physiques"},
            "3": {"en": "Involves washing the entire body", "ar": "يتضمن غسل الجسم كاملاً", "fr": "Implique le lavage du corps entier"},
            "4": {"en": "Recommended before Friday prayer and Eid", "ar": "مستحب قبل صلاة الجمعة والعيد", "fr": "Recommandé avant la prière du vendredi et l'Aïd"},
            "5": {"en": "Has a specific order: intention, washing hands, then body", "ar": "له ترتيب: النية ثم غسل اليدين ثم الجسم", "fr": "A un ordre spécifique : intention, lavage des mains, puis corps"},
            "6": {"en": "The full ritual bath in Islam", "ar": "الاغتسال الكامل في الإسلام", "fr": "Le bain rituel complet en Islam"},
        },
        "explanation": {
            "en": "Ghusl is the full-body ritual washing required in Islam after certain states of impurity. It involves washing the entire body with water following a specific sequence. It is also recommended before Friday prayer, Eid, and entering Ihram for Hajj.",
            "ar": "الغسل هو غسل الجسم الكامل المطلوب في الإسلام بعد حالات معينة من الحدث الأكبر. يتضمن غسل الجسم كله بالماء وفق ترتيب محدد. يُستحب أيضاً قبل صلاة الجمعة والعيد والإحرام للحج.",
            "fr": "Le Ghousl est le lavage rituel du corps entier requis en Islam après certains états d'impureté. Il implique le lavage de tout le corps avec de l'eau suivant une séquence spécifique. Il est aussi recommandé avant la prière du vendredi, l'Aïd et l'entrée en Ihram pour le Hajj.",
        },
    },
    # === New entries: Places ===
    {
        "word_en": "Zamzam",
        "word_ar": "زمزم",
        "word_fr": "Zamzam",
        "accepted_answers": {"en": ["Zamzam", "Zam Zam"], "ar": ["زمزم"], "fr": ["Zamzam"]},
        "category": "Places",
        "hints": {
            "1": {"en": "Has been flowing for thousands of years", "ar": "يتدفق منذ آلاف السنين", "fr": "Coule depuis des milliers d'années"},
            "2": {"en": "Miraculous in origin, connected to a mother and child", "ar": "معجزة في أصلها مرتبطة بأم وطفلها", "fr": "Miraculeuse dans son origine, liée à une mère et un enfant"},
            "3": {"en": "Hajar ran between two hills seeking it", "ar": "سعت هاجر بين تلتين بحثاً عنه", "fr": "Hajar a couru entre deux collines à sa recherche"},
            "4": {"en": "Pilgrims drink from it during Hajj", "ar": "يشرب منه الحجاج أثناء الحج", "fr": "Les pèlerins en boivent pendant le Hajj"},
            "5": {"en": "Located inside the Grand Mosque in Makkah", "ar": "يقع داخل المسجد الحرام في مكة", "fr": "Situé à l'intérieur de la Grande Mosquée de La Mecque"},
            "6": {"en": "The holy well near the Kaaba", "ar": "البئر المقدسة قرب الكعبة", "fr": "Le puits sacré près de la Kaaba"},
        },
        "explanation": {
            "en": "Zamzam is the holy well located within the Masjid al-Haram in Makkah, just meters from the Kaaba. It miraculously sprang forth for Hajar and baby Ismail when they were alone in the desert. Its water has never dried up in over 4,000 years.",
            "ar": "زمزم بئر مقدسة داخل المسجد الحرام في مكة على بعد أمتار من الكعبة. نبعت بمعجزة لهاجر والطفل إسماعيل حين كانا وحدهما في الصحراء. لم تجف مياهها منذ أكثر من 4000 سنة.",
            "fr": "Zamzam est le puits sacré situé dans le Masjid al-Haram à La Mecque, à quelques mètres de la Kaaba. Il jaillit miraculeusement pour Hajar et le bébé Ismaïl quand ils étaient seuls dans le désert. Son eau n'a jamais tari en plus de 4 000 ans.",
        },
    },
    {
        "word_en": "Arafat",
        "word_ar": "عرفات",
        "word_fr": "Arafat",
        "accepted_answers": {"en": ["Arafat", "Arafah"], "ar": ["عرفات", "عرفة"], "fr": ["Arafat", "Arafah"]},
        "category": "Places",
        "hints": {
            "1": {"en": "Standing here is the most important pillar of Hajj", "ar": "الوقوف هنا أهم ركن في الحج", "fr": "Se tenir ici est le pilier le plus important du Hajj"},
            "2": {"en": "The Prophet delivered his Farewell Sermon here", "ar": "ألقى النبي خطبة الوداع هنا", "fr": "Le Prophète a prononcé son Sermon d'Adieu ici"},
            "3": {"en": "Pilgrims gather here on the 9th of Dhul Hijjah", "ar": "يجتمع الحجاج هنا في 9 ذي الحجة", "fr": "Les pèlerins s'y rassemblent le 9 Dhul Hijjah"},
            "4": {"en": "Where Adam and Hawa (Eve) reunited", "ar": "حيث التقى آدم وحواء", "fr": "Où Adam et Hawa (Ève) se sont retrouvés"},
            "5": {"en": "A vast plain outside Makkah", "ar": "سهل واسع خارج مكة", "fr": "Une vaste plaine à l'extérieur de La Mecque"},
            "6": {"en": "The Mountain of Mercy", "ar": "جبل الرحمة", "fr": "La Montagne de la Miséricorde"},
        },
        "explanation": {
            "en": "Arafat is a vast plain southeast of Makkah where pilgrims stand in prayer on the 9th of Dhul Hijjah — the most essential rite of Hajj. The Prophet said 'Hajj is Arafat.' It is where Adam and Hawa reunited and where the Farewell Sermon was delivered.",
            "ar": "عرفات سهل واسع جنوب شرق مكة يقف فيه الحجاج بالدعاء في 9 ذي الحجة — أهم ركن في الحج. قال النبي 'الحج عرفة.' هنا التقى آدم وحواء وهنا ألقيت خطبة الوداع.",
            "fr": "Arafat est une vaste plaine au sud-est de La Mecque où les pèlerins se tiennent en prière le 9 Dhul Hijjah — le rite le plus essentiel du Hajj. Le Prophète a dit 'Le Hajj, c'est Arafat.' C'est là qu'Adam et Hawa se sont retrouvés et où le Sermon d'Adieu fut prononcé.",
        },
    },
    {
        "word_en": "Mina",
        "word_ar": "منى",
        "word_fr": "Mina",
        "accepted_answers": {"en": ["Mina", "Muna"], "ar": ["منى"], "fr": ["Mina"]},
        "category": "Places",
        "hints": {
            "1": {"en": "A valley near Makkah that transforms during Hajj", "ar": "وادٍ قرب مكة يتحول أثناء الحج", "fr": "Une vallée près de La Mecque qui se transforme pendant le Hajj"},
            "2": {"en": "Hundreds of thousands of white tents fill it", "ar": "تملؤه مئات آلاف الخيام البيضاء", "fr": "Des centaines de milliers de tentes blanches la remplissent"},
            "3": {"en": "Pilgrims spend nights here during Hajj", "ar": "يبيت الحجاج هنا أثناء الحج", "fr": "Les pèlerins y passent des nuits pendant le Hajj"},
            "4": {"en": "The stoning ritual takes place here", "ar": "يُؤدى رمي الجمرات هنا", "fr": "Le rituel de lapidation a lieu ici"},
            "5": {"en": "Connected to Ibrahim's trial with his son", "ar": "مرتبطة بابتلاء إبراهيم مع ابنه", "fr": "Liée à l'épreuve d'Ibrahim avec son fils"},
            "6": {"en": "The tent city of Hajj", "ar": "مدينة خيام الحج", "fr": "La cité des tentes du Hajj"},
        },
        "explanation": {
            "en": "Mina is a valley near Makkah that becomes the world's largest tent city during Hajj. Pilgrims stay here and perform the symbolic stoning of the Jamarat pillars, commemorating Ibrahim's rejection of Shaytan's temptation to disobey Allah's command.",
            "ar": "منى وادٍ قرب مكة يصبح أكبر مدينة خيام في العالم أثناء الحج. يمكث الحجاج هنا ويرمون الجمرات رمزاً لرفض إبراهيم لوسوسة الشيطان بعصيان أمر الله.",
            "fr": "Mina est une vallée près de La Mecque qui devient la plus grande cité de tentes du monde pendant le Hajj. Les pèlerins y séjournent et effectuent la lapidation symbolique des piliers de Jamarat, commémorant le rejet par Ibrahim de la tentation de Shaytan de désobéir à l'ordre d'Allah.",
        },
    },
    {
        "word_en": "Safa",
        "word_ar": "صفا",
        "word_fr": "Safa",
        "accepted_answers": {"en": ["Safa", "Al-Safa"], "ar": ["صفا", "الصفا"], "fr": ["Safa", "Al-Safa"]},
        "category": "Places",
        "hints": {
            "1": {"en": "Part of a ritual walk during Hajj and Umrah", "ar": "جزء من مشي شعائري في الحج والعمرة", "fr": "Partie d'une marche rituelle pendant le Hajj et la Omra"},
            "2": {"en": "A mother desperately searched for water from here", "ar": "أم يائسة بحثت عن الماء من هنا", "fr": "Une mère a désespérément cherché de l'eau d'ici"},
            "3": {"en": "Pilgrims walk between this and another hill seven times", "ar": "يمشي الحجاج بين هذا وتل آخر سبع مرات", "fr": "Les pèlerins marchent entre celle-ci et une autre colline sept fois"},
            "4": {"en": "The companion hill is called Marwah", "ar": "التل المقابل يُسمى المروة", "fr": "La colline compagnon s'appelle Marwah"},
            "5": {"en": "Commemorates Hajar's search for water", "ar": "تُحيي ذكرى بحث هاجر عن الماء", "fr": "Commémore la recherche d'eau par Hajar"},
            "6": {"en": "A hill in the Grand Mosque of Makkah", "ar": "تل في المسجد الحرام بمكة", "fr": "Une colline dans la Grande Mosquée de La Mecque"},
        },
        "explanation": {
            "en": "Safa is one of two hills (with Marwah) inside the Grand Mosque of Makkah between which pilgrims walk seven times during Sa'i. This ritual commemorates Hajar's desperate search for water for her son Ismail, which led to the miraculous spring of Zamzam.",
            "ar": "الصفا أحد تلتين (مع المروة) داخل المسجد الحرام بمكة يمشي بينهما الحجاج سبع مرات في السعي. تُحيي هذه الشعيرة ذكرى بحث هاجر اليائس عن الماء لابنها إسماعيل مما أدى لنبع زمزم المعجزة.",
            "fr": "Safa est l'une des deux collines (avec Marwah) à l'intérieur de la Grande Mosquée de La Mecque entre lesquelles les pèlerins marchent sept fois pendant le Sa'i. Ce rituel commémore la recherche désespérée d'eau par Hajar pour son fils Ismaïl, qui mena à la source miraculeuse de Zamzam.",
        },
    },
    # === New entries: Islamic History ===
    {
        "word_en": "Hudaybiyyah",
        "word_ar": "حديبية",
        "word_fr": "Hudaybiyyah",
        "accepted_answers": {"en": ["Hudaybiyyah", "Hudaibiyyah", "Hudaybiyah"], "ar": ["حديبية", "الحديبية"], "fr": ["Hudaybiyyah", "Houdaybiyyah"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A place where a historic agreement was made", "ar": "مكان أُبرمت فيه اتفاقية تاريخية", "fr": "Un lieu où un accord historique a été conclu"},
            "2": {"en": "The Quran called it a 'clear victory'", "ar": "سماه القرآن 'فتحاً مبيناً'", "fr": "Le Coran l'a appelé une 'victoire éclatante'"},
            "3": {"en": "It happened in 6 AH", "ar": "حدث في السنة 6 هجرية", "fr": "Cela s'est produit en l'an 6 de l'Hégire"},
            "4": {"en": "A 10-year peace was agreed between two sides", "ar": "اتُفق على سلام عشر سنوات بين طرفين", "fr": "Une paix de 10 ans a été convenue entre deux parties"},
            "5": {"en": "Between the Muslims and the Quraysh", "ar": "بين المسلمين وقريش", "fr": "Entre les musulmans et les Quraysh"},
            "6": {"en": "The famous treaty near Makkah", "ar": "المعاهدة الشهيرة قرب مكة", "fr": "Le célèbre traité près de La Mecque"},
        },
        "explanation": {
            "en": "Hudaybiyyah is the location near Makkah where the Treaty of Hudaybiyyah was signed in 628 CE between the Muslims and Quraysh. Though it seemed like a setback, the Quran called it a 'clear victory' — the peace allowed Islam to spread rapidly across Arabia.",
            "ar": "الحديبية موقع قرب مكة حيث وُقّعت صلح الحديبية سنة 628م بين المسلمين وقريش. رغم أنه بدا انتكاسة سماه القرآن 'فتحاً مبيناً' — السلام سمح بانتشار الإسلام سريعاً في الجزيرة.",
            "fr": "Hudaybiyyah est le lieu près de La Mecque où le traité de Hudaybiyyah fut signé en 628 entre les musulmans et les Quraysh. Bien qu'il semblait être un recul, le Coran l'a appelé une 'victoire éclatante' — la paix a permis à l'Islam de se répandre rapidement en Arabie.",
        },
    },
    {
        "word_en": "Khaybar",
        "word_ar": "خيبر",
        "word_fr": "Khaybar",
        "accepted_answers": {"en": ["Khaybar", "Khaibar"], "ar": ["خيبر"], "fr": ["Khaybar", "Khaïbar"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A fortified oasis north of Madinah", "ar": "واحة محصنة شمال المدينة", "fr": "Une oasis fortifiée au nord de Médine"},
            "2": {"en": "A famous battle cry is associated with its name", "ar": "صيحة حربية شهيرة مرتبطة باسمها", "fr": "Un célèbre cri de guerre est associé à son nom"},
            "3": {"en": "Ali carried the fortress gate single-handedly", "ar": "حمل علي باب الحصن وحده", "fr": "Ali a porté la porte de la forteresse à lui seul"},
            "4": {"en": "Multiple fortresses had to be conquered", "ar": "حصون متعددة كان لا بد من فتحها", "fr": "Plusieurs forteresses devaient être conquises"},
            "5": {"en": "Occurred in 7 AH", "ar": "وقعت في السنة 7 هجرية", "fr": "S'est produite en l'an 7 de l'Hégire"},
            "6": {"en": "The famous fortress battle", "ar": "معركة الحصون الشهيرة", "fr": "La célèbre bataille des forteresses"},
        },
        "explanation": {
            "en": "Khaybar was a fortified oasis north of Madinah conquered by Muslims in 628 CE. It is famous for Ali ibn Abi Talib's legendary feat of tearing off a fortress gate and using it as a shield. The victory secured the northern frontier of the Muslim state.",
            "ar": "خيبر واحة محصنة شمال المدينة فتحها المسلمون سنة 628م. اشتهرت بمأثرة علي بن أبي طالب الأسطورية حين اقتلع باب حصن واستخدمه درعاً. أمّن الانتصار الحدود الشمالية للدولة الإسلامية.",
            "fr": "Khaybar était une oasis fortifiée au nord de Médine conquise par les musulmans en 628. Elle est célèbre pour l'exploit légendaire d'Ali ibn Abi Talib qui arracha une porte de forteresse et l'utilisa comme bouclier. La victoire sécurisa la frontière nord de l'État musulman.",
        },
    },
    # === New entries: Quran ===
    {
        "word_en": "Al-Baqarah",
        "word_ar": "البقرة",
        "word_fr": "Al-Baqarah",
        "accepted_answers": {"en": ["Al-Baqarah", "Al Baqarah", "Baqarah"], "ar": ["البقرة", "سورة البقرة"], "fr": ["Al-Baqarah", "La Vache"]},
        "category": "Quran",
        "hints": {
            "1": {"en": "The longest surah in the Quran", "ar": "أطول سورة في القرآن", "fr": "La plus longue sourate du Coran"},
            "2": {"en": "Contains 286 verses", "ar": "تحتوي 286 آية", "fr": "Contient 286 versets"},
            "3": {"en": "Ayat Al-Kursi is in this surah", "ar": "آية الكرسي في هذه السورة", "fr": "Ayat Al-Kursi est dans cette sourate"},
            "4": {"en": "Named after an animal from a story of Bani Israel", "ar": "سُميت بحيوان من قصة بني إسرائيل", "fr": "Nommée d'après un animal d'une histoire de Bani Israël"},
            "5": {"en": "The Prophet said Shaytan flees from a house where it is recited", "ar": "قال النبي إن الشيطان يفر من بيت تُقرأ فيه", "fr": "Le Prophète a dit que Shaytan fuit une maison où elle est récitée"},
            "6": {"en": "The Cow — second surah of the Quran", "ar": "البقرة — السورة الثانية من القرآن", "fr": "La Vache — deuxième sourate du Coran"},
        },
        "explanation": {
            "en": "Surah Al-Baqarah (The Cow) is the longest chapter in the Quran with 286 verses. It covers laws, stories of past nations, and contains Ayat Al-Kursi. The Prophet said that reciting it at home drives away Shaytan for three days.",
            "ar": "سورة البقرة أطول سورة في القرآن بـ286 آية. تتناول الأحكام وقصص الأمم السابقة وتحتوي آية الكرسي. قال النبي إن قراءتها في البيت تطرد الشيطان ثلاثة أيام.",
            "fr": "La sourate Al-Baqarah (La Vache) est le plus long chapitre du Coran avec 286 versets. Elle couvre des lois, des histoires de nations passées et contient Ayat Al-Kursi. Le Prophète a dit que la réciter à la maison chasse Shaytan pendant trois jours.",
        },
    },
]


async def seed_quiz_words(session: AsyncSession) -> None:
    """Seed Word Quiz words with trilingual hints.

    Args:
        session: The database session.
    """
    count = 0
    for word_data in QUIZ_WORDS:
        existing = (
            await session.exec(select(QuizWord).where(QuizWord.word_en == word_data["word_en"]))
        ).first()
        if existing:
            # Update explanation if it was added
            if word_data.get("explanation") and not existing.explanation:
                existing.explanation = word_data["explanation"]
                session.add(existing)
            continue
        quiz_word = QuizWord(
            id=uuid4(),
            word_en=word_data["word_en"],
            word_ar=word_data.get("word_ar"),
            word_fr=word_data.get("word_fr"),
            accepted_answers=word_data.get("accepted_answers"),
            category=word_data["category"],
            hints=word_data["hints"],
            explanation=word_data.get("explanation"),
        )
        session.add(quiz_word)
        count += 1

    await session.commit()
    print(f"  Seeded {count} Word Quiz words")


async def seed_achievements(session: AsyncSession) -> None:
    """Seed achievement definitions using the AchievementController.

    Args:
        session: The database session.
    """
    controller = AchievementController(session)
    await controller.seed_achievements()
    print("  Seeded achievement definitions")


async def create_user_stats(session: AsyncSession, users: list[User]) -> None:
    """Create sample UserStats entries for test users.

    Args:
        session: The database session.
        users: List of users to create stats for.
    """
    roles_undercover = ["civilian", "undercover", "mr_white"]
    roles_codenames = ["spymaster", "operative"]

    for user in users:
        total_played = random.randint(5, 100)
        total_won = random.randint(1, total_played)
        total_lost = total_played - total_won

        uc_played = random.randint(2, total_played // 2 + 1)
        uc_won = random.randint(0, uc_played)
        cn_played = total_played - uc_played
        cn_won = total_won - uc_won if total_won > uc_won else random.randint(0, cn_played)

        times_civilian = random.randint(1, max(1, uc_played // 2))
        times_undercover = random.randint(1, max(1, uc_played // 3))
        times_mr_white = max(0, uc_played - times_civilian - times_undercover)

        civilian_wins = random.randint(0, times_civilian)
        undercover_wins = random.randint(0, times_undercover)
        mr_white_wins = random.randint(0, times_mr_white)

        times_spymaster = random.randint(1, max(1, cn_played // 2))
        times_operative = max(0, cn_played - times_spymaster)

        spymaster_wins = random.randint(0, times_spymaster)
        operative_wins = random.randint(0, times_operative)

        current_win_streak = random.randint(0, 5)
        longest_win_streak = random.randint(current_win_streak, 10)

        current_play_streak = random.randint(0, 7)
        longest_play_streak = random.randint(current_play_streak, 30)

        stats = UserStats(
            id=uuid4(),
            user_id=user.id,
            total_games_played=total_played,
            total_games_won=total_won,
            total_games_lost=total_lost,
            undercover_games_played=uc_played,
            undercover_games_won=uc_won,
            codenames_games_played=cn_played,
            codenames_games_won=cn_won,
            times_civilian=times_civilian,
            times_undercover=times_undercover,
            times_mr_white=times_mr_white,
            civilian_wins=civilian_wins,
            undercover_wins=undercover_wins,
            mr_white_wins=mr_white_wins,
            times_spymaster=times_spymaster,
            times_operative=times_operative,
            spymaster_wins=spymaster_wins,
            operative_wins=operative_wins,
            total_votes_cast=random.randint(10, 200),
            correct_votes=random.randint(5, 100),
            times_eliminated=random.randint(0, 30),
            times_survived=random.randint(0, 50),
            current_win_streak=current_win_streak,
            longest_win_streak=longest_win_streak,
            current_play_streak_days=current_play_streak,
            longest_play_streak_days=longest_play_streak,
            last_played_at=fake.date_time_between(start_date="-7d", end_date="now"),
            mr_white_correct_guesses=random.randint(0, 5),
            codenames_words_guessed=random.randint(5, 80),
            codenames_perfect_rounds=random.randint(0, 5),
            rooms_created=random.randint(0, 20),
            games_hosted=random.randint(0, 15),
        )
        session.add(stats)

    await session.commit()
    print(f"  Created UserStats for {len(users)} users")


async def seed_challenges(session: AsyncSession) -> None:
    """Seed challenge definitions using the ChallengeController.

    Args:
        session: The database session.
    """
    controller = ChallengeController(session)
    await controller.seed_challenges()
    print("  Seeded challenge definitions")


async def create_friendships(session: AsyncSession, users: list[User]) -> None:
    """Create sample friendship records between test users.

    Args:
        session: The database session.
        users: List of users to create friendships between.
    """
    if len(users) < 4:
        return

    count = 0
    # Create accepted friendships between first few users
    pairs_accepted = [(0, 1), (0, 2), (1, 3), (2, 4), (3, 5)]
    for i, j in pairs_accepted:
        if i < len(users) and j < len(users):
            friendship = Friendship(
                id=uuid4(),
                requester_id=users[i].id,
                addressee_id=users[j].id,
                status=FriendshipStatus.ACCEPTED,
            )
            session.add(friendship)
            count += 1

    # Create some pending requests
    pairs_pending = [(4, 0), (5, 1), (6, 2)]
    for i, j in pairs_pending:
        if i < len(users) and j < len(users):
            friendship = Friendship(
                id=uuid4(),
                requester_id=users[i].id,
                addressee_id=users[j].id,
                status=FriendshipStatus.PENDING,
            )
            session.add(friendship)
            count += 1

    await session.commit()
    print(f"  Created {count} friendships")


async def create_chat_messages(session: AsyncSession, users: list[User], rooms: list[Room]) -> None:
    """Create sample chat messages in rooms.

    Args:
        session: The database session.
        users: List of users who can send messages.
        rooms: List of rooms to add messages to.
    """
    if not rooms or not users:
        return

    count = 0
    messages_pool = [
        "Assalamu Alaikum!",
        "Who's ready to play?",
        "Let's go!",
        "Good game everyone",
        "That was close!",
        "MashaAllah, well played!",
        "Ready for another round?",
        "SubhanAllah, what a game!",
        "Who's the undercover?",
        "I think I know the word...",
        "Great clue!",
        "Let's vote!",
        "Bismillah, here we go",
        "AlhamduliLlah, good win",
        "JazakAllah khair for playing",
    ]

    for room in rooms[:5]:  # Only first 5 rooms
        num_messages = random.randint(3, 10)
        for _ in range(num_messages):
            user = random.choice(users[:10])  # Use first 10 test users
            msg = ChatMessage(
                id=uuid4(),
                room_id=room.id,
                user_id=user.id,
                username=user.username,
                message=random.choice(messages_pool),
            )
            session.add(msg)
            count += 1

    await session.commit()
    print(f"  Created {count} chat messages")


async def create_user_achievements(session: AsyncSession, users: list[User]) -> None:
    """Create sample UserAchievement records for test users.

    Some achievements are unlocked (with unlocked_at), some are in-progress.

    Args:
        session: The database session.
        users: List of users to create achievements for.
    """
    # Fetch all achievement definitions
    definitions = list((await session.exec(select(AchievementDefinition))).all())
    if not definitions:
        print("  No achievement definitions found — skipping")
        return

    count = 0
    for user in users[:10]:  # First 10 test users
        # Give each user 3-6 random achievements
        num_achievements = random.randint(3, min(6, len(definitions)))
        selected = random.sample(definitions, num_achievements)

        for defn in selected:
            is_unlocked = random.random() < 0.6  # 60% chance unlocked
            progress = defn.threshold if is_unlocked else random.randint(0, defn.threshold - 1)
            unlocked_at = (
                fake.date_time_between(start_date="-30d", end_date="now")
                if is_unlocked
                else None
            )

            achievement = UserAchievement(
                id=uuid4(),
                user_id=user.id,
                achievement_id=defn.id,
                progress=progress,
                unlocked_at=unlocked_at,
            )
            session.add(achievement)
            count += 1

    await session.commit()
    print(f"  Created {count} user achievements")


async def create_user_challenges(session: AsyncSession, users: list[User]) -> None:
    """Assign active challenges to test users.

    Each user gets 3 daily + 2 weekly challenges (matching the app's assignment logic).

    Args:
        session: The database session.
        users: List of users to assign challenges to.
    """
    # Fetch challenge definitions by type
    all_defs = list((await session.exec(select(ChallengeDefinition))).all())
    if not all_defs:
        print("  No challenge definitions found — skipping")
        return

    daily_defs = [d for d in all_defs if d.challenge_type == ChallengeType.DAILY]
    weekly_defs = [d for d in all_defs if d.challenge_type == ChallengeType.WEEKLY]

    now = datetime.now(UTC)
    daily_expires = now.replace(hour=23, minute=59, second=59) + timedelta(days=1)
    weekly_expires = now + timedelta(days=7 - now.weekday())  # Next Monday

    count = 0
    for user in users[:10]:  # First 10 test users
        # 3 daily challenges
        chosen_daily = random.sample(daily_defs, min(3, len(daily_defs)))
        for defn in chosen_daily:
            progress = random.randint(0, defn.target_count)
            challenge = UserChallenge(
                id=uuid4(),
                user_id=user.id,
                challenge_id=defn.id,
                progress=progress,
                completed=progress >= defn.target_count,
                assigned_at=now,
                expires_at=daily_expires,
            )
            session.add(challenge)
            count += 1

        # 2 weekly challenges
        chosen_weekly = random.sample(weekly_defs, min(2, len(weekly_defs)))
        for defn in chosen_weekly:
            progress = random.randint(0, defn.target_count)
            challenge = UserChallenge(
                id=uuid4(),
                user_id=user.id,
                challenge_id=defn.id,
                progress=progress,
                completed=progress >= defn.target_count,
                assigned_at=now,
                expires_at=weekly_expires,
            )
            session.add(challenge)
            count += 1

    await session.commit()
    print(f"  Created {count} user challenges")


# ── Main operations ─────────────────────────────────────────────────────────


async def delete_all_data(engine: AsyncEngine) -> None:
    """Delete all data by dropping and recreating tables.

    Args:
        engine: The database engine.
    """
    print("Dropping and recreating all tables...")
    await create_db_and_tables(engine, drop_all=True)
    print("All tables dropped and recreated successfully!")


async def generate_all_data(
    engine: AsyncEngine,
    num_users: int = 15,
    num_games: int = 30,
) -> None:
    """Create tables and generate all fake data.

    Args:
        engine: The database engine.
        num_users: Number of additional random users to generate.
        num_games: Number of games to generate.
    """
    print("Creating database tables...")
    await create_db_and_tables(engine)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # 1. Create test users
        print("\n[1/12] Creating test users...")
        test_users = await create_test_users(session)

        # 2. Create random users
        print(f"\n[2/12] Creating {num_users} random users...")
        random_users = await create_random_users(session, num_users)
        all_users = test_users + random_users

        # 3. Create rooms
        print("\n[3/12] Creating rooms...")
        rooms = await create_rooms(session, all_users, count=max(5, len(all_users) // 3))

        # 4. Seed Undercover words and pairs
        print("\n[4/12] Seeding Undercover words and pairs...")
        word_map = await seed_undercover_words(session)
        await seed_undercover_pairs(session, word_map)

        # 5. Seed Codenames words
        print("\n[5/12] Seeding Codenames word packs...")
        await seed_codenames_words(session)

        # 5b. Seed Word Quiz words
        print("\n[5b/12] Seeding Word Quiz words...")
        await seed_quiz_words(session)

        # 5c. Seed MCQ Quiz questions
        print("\n[5c/12] Seeding MCQ Quiz questions...")
        await seed_mcq_questions(session)

        # 6. Seed achievements
        print("\n[6/12] Seeding achievement definitions...")
        await seed_achievements(session)

        # 7. Seed challenges
        print("\n[7/12] Seeding challenge definitions...")
        await seed_challenges(session)

        # 8. Create games and stats
        print(f"\n[8/12] Creating {num_games} games and user stats...")
        await create_games(session, all_users, count=num_games)
        await create_user_stats(session, test_users)

        # 9. Create friendships
        print("\n[9/12] Creating friendships...")
        await create_friendships(session, test_users)

        # 10. Create chat messages
        print("\n[10/12] Creating chat messages...")
        await create_chat_messages(session, test_users, rooms)

        # 11. Create user achievements (earned/in-progress)
        print("\n[11/12] Creating user achievements...")
        await create_user_achievements(session, test_users)

        # 12. Create user challenges (assigned daily/weekly)
        print("\n[12/12] Creating user challenges...")
        await create_user_challenges(session, test_users)

    print("\nFake data generation complete!")


async def seed_game_content(engine: AsyncEngine) -> None:
    """Seed only game content (words, term pairs, codenames, achievements, challenges).

    Safe for production — does not create fake users, rooms, or games.

    Args:
        engine: The database engine.
    """
    print("Creating database tables (if not exist)...")
    await create_db_and_tables(engine)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        print("\n[1/4] Seeding Undercover words and pairs...")
        word_map = await seed_undercover_words(session)
        await seed_undercover_pairs(session, word_map)

        print("\n[2/4] Seeding Codenames word packs...")
        await seed_codenames_words(session)

        print("\n[3/6] Seeding Word Quiz words...")
        await seed_quiz_words(session)

        print("\n[4/6] Seeding MCQ Quiz questions...")
        await seed_mcq_questions(session)

        print("\n[5/6] Seeding achievement definitions...")
        await seed_achievements(session)

        print("\n[6/6] Seeding challenge definitions...")
        await seed_challenges(session)

    print("\nGame content seeding complete!")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate fake data for IPG platform testing",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--create-db", "-c",
        action="store_true",
        help="Create database tables and generate fake data",
    )
    group.add_argument(
        "--delete", "-d",
        action="store_true",
        help="Delete all data by dropping and recreating tables",
    )
    group.add_argument(
        "--seed", "-s",
        action="store_true",
        help="Seed game content only (words, term pairs, codenames, achievements, challenges). Safe for production.",
    )

    parser.add_argument(
        "--users",
        type=int,
        default=15,
        help="Number of additional random users to generate (default: 15)",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=30,
        help="Number of games to generate (default: 30)",
    )

    return parser.parse_args()


async def main() -> None:
    """Main entry point for the fake data generation script."""
    global fake
    args = parse_args()

    # Import dev-only dependencies only when needed (not in production image)
    if args.create_db:
        from faker import Faker

        fake = Faker()

    settings = Settings()  # type: ignore[call-arg]
    engine = await create_app_engine(settings)

    try:
        if args.delete:
            await delete_all_data(engine)
        elif args.seed:
            await seed_game_content(engine)
        elif args.create_db:
            await generate_all_data(
                engine,
                num_users=args.users,
                num_games=args.games,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
