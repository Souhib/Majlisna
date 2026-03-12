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

    for word_data in UNDERCOVER_WORDS:
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

    await session.commit()
    for word in word_map.values():
        await session.refresh(word)

    print(f"  Seeded {len(word_map)} Undercover words")
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

        pair = TermPair(
            id=uuid4(),
            word1_id=w1.id,
            word2_id=w2.id,
        )
        session.add(pair)
        count += 1

    await session.commit()
    print(f"  Seeded {count} Undercover word pairs")


async def seed_codenames_words(session: AsyncSession) -> None:
    """Seed Codenames word packs and words.

    Args:
        session: The database session.
    """
    total_words = 0

    for pack_name, words in CODENAMES_WORD_PACKS.items():
        pack = CodenamesWordPack(
            id=uuid4(),
            name=pack_name,
            description=f"Islamic terms related to {pack_name.lower()}",
            is_active=True,
        )
        session.add(pack)
        await session.flush()

        for word_data in words:
            word = CodenamesWord(
                id=uuid4(),
                word=word_data["word"],
                hint=word_data.get("hint"),
                word_pack_id=pack.id,
            )
            session.add(word)
            total_words += 1

    await session.commit()
    print(f"  Seeded {len(CODENAMES_WORD_PACKS)} Codenames word packs with {total_words} words")


QUIZ_WORDS: list[dict] = [
    # === Prophets (~25) ===
    {
        "word_en": "Ibrahim",
        "word_ar": "إبراهيم",
        "word_fr": "Ibrahim",
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
    },
    {
        "word_en": "Musa",
        "word_ar": "موسى",
        "word_fr": "Moïse",
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
    },
    {
        "word_en": "Isa",
        "word_ar": "عيسى",
        "word_fr": "Jésus",
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
    },
    {
        "word_en": "Nuh",
        "word_ar": "نوح",
        "word_fr": "Noé",
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
    },
    {
        "word_en": "Yusuf",
        "word_ar": "يوسف",
        "word_fr": "Joseph",
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
    },
    {
        "word_en": "Dawud",
        "word_ar": "داود",
        "word_fr": "David",
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
    },
    {
        "word_en": "Sulayman",
        "word_ar": "سليمان",
        "word_fr": "Salomon",
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
    },
    {
        "word_en": "Ayyub",
        "word_ar": "أيوب",
        "word_fr": "Job",
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
    },
    {
        "word_en": "Yunus",
        "word_ar": "يونس",
        "word_fr": "Jonas",
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
    },
    # === Islamic History (~10) ===
    {
        "word_en": "Battle of Badr",
        "word_ar": "غزوة بدر",
        "word_fr": "Bataille de Badr",
        "accepted_answers": {"en": ["Battle of Badr", "Badr"], "ar": ["غزوة بدر", "بدر", "معركة بدر"], "fr": ["Bataille de Badr", "Badr"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A decisive early battle in Islamic history", "ar": "معركة حاسمة في بداية الإسلام", "fr": "Une bataille décisive au début de l'Islam"},
            "2": {"en": "Muslims were greatly outnumbered", "ar": "كان المسلمون أقل عدداً بكثير", "fr": "Les musulmans étaient largement dépassés en nombre"},
            "3": {"en": "Occurred in the 2nd year after Hijra", "ar": "وقعت في السنة الثانية بعد الهجرة", "fr": "S'est produite la 2e année après la Hijra"},
            "4": {"en": "313 Muslims vs about 1000 enemies", "ar": "313 مسلماً ضد نحو 1000", "fr": "313 musulmans contre environ 1000 ennemis"},
            "5": {"en": "Angels descended to help", "ar": "نزلت الملائكة للمساعدة", "fr": "Les anges sont descendus pour aider"},
            "6": {"en": "The first major battle of Islam", "ar": "أول معركة كبرى في الإسلام", "fr": "La première grande bataille de l'Islam"},
        },
    },
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
    },
    {
        "word_en": "Ismail",
        "word_ar": "إسماعيل",
        "word_fr": "Ismaël",
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
    },
    {
        "word_en": "Yaqub",
        "word_ar": "يعقوب",
        "word_fr": "Jacob",
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
    },
    {
        "word_en": "Shuayb",
        "word_ar": "شعيب",
        "word_fr": "Chouaïb",
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
    },
    {
        "word_en": "Zakaria",
        "word_ar": "زكريا",
        "word_fr": "Zacharie",
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
    },
    {
        "word_en": "Idris",
        "word_ar": "إدريس",
        "word_fr": "Idris",
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
    },
    # === More Islamic History ===
    {
        "word_en": "Treaty of Hudaybiyyah",
        "word_ar": "صلح الحديبية",
        "word_fr": "Traité de Hudaybiya",
        "accepted_answers": {"en": ["Hudaybiyyah", "Treaty of Hudaybiyyah", "Hudaybiyya"], "ar": ["صلح الحديبية", "الحديبية"], "fr": ["Hudaybiya", "Traité de Hudaybiya"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "Initially seemed like a loss to the Muslims", "ar": "بدا في البداية كخسارة للمسلمين", "fr": "Semblait initialement être une perte pour les musulmans"},
            "2": {"en": "A peace agreement between two parties", "ar": "اتفاق سلام بين طرفين", "fr": "Un accord de paix entre deux parties"},
            "3": {"en": "The Quran called it a clear victory", "ar": "سماه القرآن فتحاً مبيناً", "fr": "Le Coran l'a appelé une victoire claire"},
            "4": {"en": "Occurred in the 6th year of Hijra", "ar": "وقع في السنة السادسة للهجرة", "fr": "A eu lieu la 6e année de l'Hégire"},
            "5": {"en": "A 10-year truce was agreed", "ar": "تم الاتفاق على هدنة لعشر سنوات", "fr": "Une trêve de 10 ans a été convenue"},
            "6": {"en": "Peace treaty near Makkah", "ar": "معاهدة سلام قرب مكة", "fr": "Traité de paix près de La Mecque"},
        },
    },
    {
        "word_en": "Conquest of Makkah",
        "word_ar": "فتح مكة",
        "word_fr": "Conquête de La Mecque",
        "accepted_answers": {"en": ["Conquest of Makkah", "Fath Makkah", "Liberation of Mecca"], "ar": ["فتح مكة"], "fr": ["Conquête de La Mecque", "Fath Makkah"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A major turning point with almost no bloodshed", "ar": "نقطة تحول كبرى بلا سفك دماء تقريباً", "fr": "Un tournant majeur presque sans effusion de sang"},
            "2": {"en": "10,000 Muslims marched together", "ar": "سار 10,000 مسلم معاً", "fr": "10 000 musulmans ont marché ensemble"},
            "3": {"en": "The Prophet forgave his enemies", "ar": "عفا النبي عن أعدائه", "fr": "Le Prophète a pardonné à ses ennemis"},
            "4": {"en": "Idols were destroyed in the Kaaba", "ar": "حُطمت الأصنام في الكعبة", "fr": "Les idoles ont été détruites dans la Kaaba"},
            "5": {"en": "Occurred in 8 AH (630 CE)", "ar": "وقع سنة 8 هجرية", "fr": "A eu lieu en l'an 8 de l'Hégire (630 EC)"},
            "6": {"en": "The peaceful liberation of the holy city", "ar": "تحرير المدينة المقدسة سلمياً", "fr": "La libération pacifique de la ville sainte"},
        },
    },
    {
        "word_en": "Isra and Miraj",
        "word_ar": "الإسراء والمعراج",
        "word_fr": "Isra et Miraj",
        "accepted_answers": {"en": ["Isra and Miraj", "Night Journey", "Miraj", "Mirraj"], "ar": ["الإسراء والمعراج", "المعراج", "الاسراء"], "fr": ["Isra et Miraj", "Voyage nocturne", "Mirraj"]},
        "category": "Islamic History",
        "hints": {
            "1": {"en": "A miraculous journey that happened in one night", "ar": "رحلة معجزة حدثت في ليلة واحدة", "fr": "Un voyage miraculeux qui s'est produit en une nuit"},
            "2": {"en": "Traveled from one holy city to another", "ar": "سافر من مدينة مقدسة إلى أخرى", "fr": "A voyagé d'une ville sainte à une autre"},
            "3": {"en": "Ascended through the seven heavens", "ar": "صعد عبر السموات السبع", "fr": "A monté à travers les sept cieux"},
            "4": {"en": "Met previous prophets along the way", "ar": "التقى بالأنبياء السابقين", "fr": "A rencontré les prophètes précédents en chemin"},
            "5": {"en": "The five daily prayers were prescribed", "ar": "فُرضت الصلوات الخمس", "fr": "Les cinq prières quotidiennes ont été prescrites"},
            "6": {"en": "The Night Journey and Ascension", "ar": "الإسراء والمعراج", "fr": "Le Voyage Nocturne et l'Ascension"},
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
    },
    {
        "word_en": "Cave of Hira",
        "word_ar": "غار حراء",
        "word_fr": "Grotte de Hira",
        "accepted_answers": {"en": ["Cave of Hira", "Hira", "Ghar Hira"], "ar": ["غار حراء", "حراء"], "fr": ["Grotte de Hira", "Hira"]},
        "category": "Places",
        "hints": {
            "1": {"en": "A place of solitude and reflection", "ar": "مكان للعزلة والتأمل", "fr": "Un lieu de solitude et de réflexion"},
            "2": {"en": "Located on a mountain near a holy city", "ar": "يقع على جبل قرب مدينة مقدسة", "fr": "Situé sur une montagne près d'une ville sainte"},
            "3": {"en": "The Prophet used to go there to meditate", "ar": "كان النبي يذهب إليه للتأمل", "fr": "Le Prophète y allait pour méditer"},
            "4": {"en": "The angel Jibreel appeared here", "ar": "ظهر الملك جبريل هنا", "fr": "L'ange Jibreel est apparu ici"},
            "5": {"en": "Iqra — Read — was the first word revealed here", "ar": "اقرأ — كانت أول كلمة أُنزلت هنا", "fr": "Iqra — Lis — fut le premier mot révélé ici"},
            "6": {"en": "Where the first Quran revelation came", "ar": "حيث نزل أول وحي قرآني", "fr": "Où la première révélation coranique est venue"},
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
            continue
        quiz_word = QuizWord(
            id=uuid4(),
            word_en=word_data["word_en"],
            word_ar=word_data.get("word_ar"),
            word_fr=word_data.get("word_fr"),
            accepted_answers=word_data.get("accepted_answers"),
            category=word_data["category"],
            hints=word_data["hints"],
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

        print("\n[3/5] Seeding Word Quiz words...")
        await seed_quiz_words(session)

        print("\n[4/5] Seeding achievement definitions...")
        await seed_achievements(session)

        print("\n[5/5] Seeding challenge definitions...")
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
