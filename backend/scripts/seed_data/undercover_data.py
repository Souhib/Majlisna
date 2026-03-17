"""Undercover game seed data — Islamic term word pairs."""

from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.undercover import TermPair, Word

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
    # --- Additional Prophets ---
    {
        "word": "Nuh",
        "category": "Prophets",
        "short_description": "Prophet Noah in Islam",
        "long_description": "Prophet Nuh (Noah) was sent to warn his people and built the Ark by God's command.",
        "hint": {
            "en": "Prophet Noah, who built the Ark and survived the great flood by God's command",
            "ar": "النبي نوح، الذي بنى السفينة ونجا من الطوفان العظيم بأمر الله",
            "fr": "Le prophète Noé, qui construisit l'Arche et survécut au grand déluge par ordre de Dieu",
        },
    },
    {
        "word": "Yusuf",
        "category": "Prophets",
        "short_description": "Prophet Joseph in Islam",
        "long_description": "Prophet Yusuf (Joseph) is known for his beauty, patience, and the detailed story in Surah Yusuf.",
        "hint": {
            "en": "Prophet Joseph, known for his beauty and patience — his story fills an entire surah",
            "ar": "النبي يوسف، المعروف بجماله وصبره — قصته تملأ سورة كاملة",
            "fr": "Le prophète Joseph, connu pour sa beauté et sa patience — son histoire remplit une sourate entière",
        },
    },
    {
        "word": "Dawud",
        "category": "Prophets",
        "short_description": "Prophet David in Islam",
        "long_description": "Prophet Dawud (David) was a king and prophet who received the Zabur (Psalms).",
        "hint": {
            "en": "Prophet David, a king and prophet who received the Zabur (Psalms)",
            "ar": "النبي داود، ملك ونبي أُنزل عليه الزبور",
            "fr": "Le prophète David, roi et prophète qui reçut le Zabur (Psaumes)",
        },
    },
    {
        "word": "Sulayman",
        "category": "Prophets",
        "short_description": "Prophet Solomon in Islam",
        "long_description": "Prophet Sulayman (Solomon) was granted dominion over jinn, animals, and the wind.",
        "hint": {
            "en": "Prophet Solomon, granted dominion over jinn, animals, and the wind",
            "ar": "النبي سليمان، سُخِّر له الجن والحيوانات والريح",
            "fr": "Le prophète Salomon, à qui fut donné le pouvoir sur les djinns, les animaux et le vent",
        },
    },
    {
        "word": "Yunus",
        "category": "Prophets",
        "short_description": "Prophet Jonah in Islam",
        "long_description": "Prophet Yunus (Jonah) is known for being swallowed by a whale and his repentance to God.",
        "hint": {
            "en": "Prophet Jonah, swallowed by a whale, who called upon God from the darkness",
            "ar": "النبي يونس، ابتلعه الحوت ودعا الله من الظلمات",
            "fr": "Le prophète Jonas, avalé par une baleine, qui invoqua Dieu depuis les ténèbres",
        },
    },
    {
        "word": "Ayyub",
        "category": "Prophets",
        "short_description": "Prophet Job in Islam",
        "long_description": "Prophet Ayyub (Job) is the symbol of patience through extreme trials and suffering.",
        "hint": {
            "en": "Prophet Job, the ultimate symbol of patience through extreme trials and suffering",
            "ar": "النبي أيوب، رمز الصبر في مواجهة الابتلاءات والمعاناة الشديدة",
            "fr": "Le prophète Job, symbole ultime de la patience face aux épreuves et souffrances extrêmes",
        },
    },
    {
        "word": "Yaqub",
        "category": "Prophets",
        "short_description": "Prophet Jacob in Islam",
        "long_description": "Prophet Yaqub (Jacob) was the father of Yusuf and the twelve tribes of Israel.",
        "hint": {
            "en": "Prophet Jacob, father of Yusuf and the twelve tribes of Israel",
            "ar": "النبي يعقوب، والد يوسف وأبو الأسباط الاثني عشر",
            "fr": "Le prophète Jacob, père de Yusuf et des douze tribus d'Israël",
        },
    },
    {
        "word": "Adam",
        "category": "Prophets",
        "short_description": "First prophet and first human",
        "long_description": "Prophet Adam is the first human being and the first prophet in Islam, created by God from clay.",
        "hint": {
            "en": "The first human being and first prophet, created by God from clay",
            "ar": "أول إنسان وأول نبي، خلقه الله من طين",
            "fr": "Le premier être humain et premier prophète, créé par Dieu à partir d'argile",
        },
    },
    {
        "word": "Harun",
        "category": "Prophets",
        "short_description": "Prophet Aaron in Islam",
        "long_description": "Prophet Harun (Aaron) was the brother of Musa and assisted him in his mission to Pharaoh.",
        "hint": {
            "en": "Prophet Aaron, brother of Musa who assisted him in his mission to Pharaoh",
            "ar": "النبي هارون، أخو موسى الذي ساعده في رسالته إلى فرعون",
            "fr": "Le prophète Aaron, frère de Moïse qui l'assista dans sa mission auprès de Pharaon",
        },
    },
    {
        "word": "Lut",
        "category": "Prophets",
        "short_description": "Prophet Lot in Islam",
        "long_description": "Prophet Lut (Lot) was sent to warn the people of Sodom against their transgressions.",
        "hint": {
            "en": "Prophet Lot, sent to warn the people of Sodom against their transgressions",
            "ar": "النبي لوط، أُرسل لتحذير قوم سدوم من فسادهم",
            "fr": "Le prophète Loth, envoyé pour avertir le peuple de Sodome contre leurs transgressions",
        },
    },
    {
        "word": "Hud",
        "category": "Prophets",
        "short_description": "Prophet sent to the people of Ad",
        "long_description": "Prophet Hud was sent to the ancient people of Ad who were destroyed for their arrogance.",
        "hint": {
            "en": "A prophet sent to the ancient people of Ad, who were destroyed for their arrogance",
            "ar": "نبي أُرسل إلى قوم عاد الذين أُهلكوا بسبب تكبرهم",
            "fr": "Un prophète envoyé au peuple ancien de Ad, détruit pour son arrogance",
        },
    },
    {
        "word": "Salih",
        "category": "Prophets",
        "short_description": "Prophet sent to the people of Thamud",
        "long_description": "Prophet Salih was sent to the people of Thamud with the miracle of the she-camel.",
        "hint": {
            "en": "A prophet sent to the people of Thamud, known for the miracle of the she-camel",
            "ar": "نبي أُرسل إلى قوم ثمود، معروف بمعجزة الناقة",
            "fr": "Un prophète envoyé au peuple de Thamud, connu pour le miracle de la chamelle",
        },
    },
    {
        "word": "Shuayb",
        "category": "Prophets",
        "short_description": "Prophet sent to the people of Madyan",
        "long_description": "Prophet Shuayb was sent to the people of Madyan to correct their dishonest trade practices.",
        "hint": {
            "en": "A prophet sent to the people of Madyan to correct their dishonest trade practices",
            "ar": "نبي أُرسل إلى أهل مدين لتصحيح ممارساتهم التجارية الغشاشة",
            "fr": "Un prophète envoyé au peuple de Madyan pour corriger leurs pratiques commerciales malhonnêtes",
        },
    },
    {
        "word": "Idris",
        "category": "Prophets",
        "short_description": "Early prophet raised to a high station",
        "long_description": "Prophet Idris is an early prophet mentioned in the Quran, raised to a high station by God.",
        "hint": {
            "en": "An early prophet mentioned in the Quran, raised by God to a high station",
            "ar": "نبي مبكر ذُكر في القرآن، رفعه الله مكاناً علياً",
            "fr": "Un prophète ancien mentionné dans le Coran, élevé par Dieu à un haut rang",
        },
    },
    # --- Companions ---
    {
        "word": "Abu Bakr",
        "category": "Companions",
        "short_description": "First Caliph of Islam",
        "long_description": "Abu Bakr al-Siddiq was the closest companion of Prophet Muhammad and the first Caliph.",
        "hint": {
            "en": "The closest companion of the Prophet and the first Caliph of Islam",
            "ar": "أقرب صحابة النبي وأول خليفة في الإسلام",
            "fr": "Le plus proche compagnon du Prophète et le premier calife de l'islam",
        },
    },
    {
        "word": "Umar",
        "category": "Companions",
        "short_description": "Second Caliph of Islam",
        "long_description": "Umar ibn al-Khattab was the second Caliph, known for justice and expanding the Islamic state.",
        "hint": {
            "en": "The second Caliph, known for his strict justice and expanding the Islamic state",
            "ar": "الخليفة الثاني، المعروف بعدله الصارم وتوسيع الدولة الإسلامية",
            "fr": "Le deuxième calife, connu pour sa justice stricte et l'expansion de l'État islamique",
        },
    },
    {
        "word": "Uthman",
        "category": "Companions",
        "short_description": "Third Caliph of Islam",
        "long_description": "Uthman ibn Affan was the third Caliph, known for compiling the Quran into a single book.",
        "hint": {
            "en": "The third Caliph, known for compiling the Quran into a single standardized book",
            "ar": "الخليفة الثالث، المعروف بجمع القرآن في مصحف واحد موحد",
            "fr": "Le troisième calife, connu pour avoir compilé le Coran en un seul livre standardisé",
        },
    },
    {
        "word": "Ali",
        "category": "Companions",
        "short_description": "Fourth Caliph of Islam",
        "long_description": "Ali ibn Abi Talib was the cousin and son-in-law of Prophet Muhammad and the fourth Caliph.",
        "hint": {
            "en": "Cousin and son-in-law of the Prophet, the fourth Caliph of Islam",
            "ar": "ابن عم النبي وصهره، الخليفة الرابع في الإسلام",
            "fr": "Cousin et gendre du Prophète, le quatrième calife de l'islam",
        },
    },
    {
        "word": "Bilal",
        "category": "Companions",
        "short_description": "First muezzin in Islam",
        "long_description": "Bilal ibn Rabah was a formerly enslaved companion who became the first muezzin in Islam.",
        "hint": {
            "en": "A formerly enslaved companion who became the first muezzin, caller to prayer",
            "ar": "صحابي كان مستعبداً وأصبح أول مؤذن في الإسلام",
            "fr": "Un compagnon autrefois réduit en esclavage qui devint le premier muezzin de l'islam",
        },
    },
    {
        "word": "Khalid ibn al-Walid",
        "category": "Companions",
        "short_description": "Sword of Allah",
        "long_description": "Khalid ibn al-Walid was a brilliant military commander known as the Sword of Allah.",
        "hint": {
            "en": "A brilliant military commander known as the Sword of Allah, undefeated in battle",
            "ar": "قائد عسكري عبقري عُرف بسيف الله المسلول، لم يُهزم في معركة",
            "fr": "Un brillant commandant militaire connu comme l'Épée d'Allah, invaincu au combat",
        },
    },
    # --- Islamic Places ---
    {
        "word": "Al-Aqsa",
        "category": "Islamic Places",
        "short_description": "Sacred mosque in Jerusalem",
        "long_description": "Al-Masjid al-Aqsa in Jerusalem is the third holiest site in Islam.",
        "hint": {
            "en": "The third holiest mosque in Islam, located in Jerusalem",
            "ar": "المسجد الأقصى — ثالث أقدس مسجد في الإسلام، يقع في القدس",
            "fr": "La troisième mosquée la plus sainte de l'islam, située à Jérusalem",
        },
    },
    {
        "word": "Arafat",
        "category": "Islamic Places",
        "short_description": "Plain where pilgrims stand during Hajj",
        "long_description": "The plain of Arafat is where pilgrims stand in prayer on the 9th of Dhul Hijjah during Hajj.",
        "hint": {
            "en": "The plain where pilgrims stand in prayer on the Day of Arafah during Hajj",
            "ar": "سهل عرفات حيث يقف الحجاج في الدعاء يوم عرفة",
            "fr": "La plaine où les pèlerins se tiennent en prière le jour d'Arafat pendant le Hajj",
        },
    },
    {
        "word": "Muzdalifah",
        "category": "Islamic Places",
        "short_description": "Site between Arafat and Mina",
        "long_description": "Muzdalifah is the area between Arafat and Mina where pilgrims spend the night during Hajj.",
        "hint": {
            "en": "The area between Arafat and Mina where pilgrims spend the night and collect pebbles",
            "ar": "المنطقة بين عرفات ومنى حيث يبيت الحجاج ويجمعون الحصى",
            "fr": "La zone entre Arafat et Mina où les pèlerins passent la nuit et ramassent des cailloux",
        },
    },
    {
        "word": "Mina",
        "category": "Islamic Places",
        "short_description": "Tent city during Hajj",
        "long_description": "Mina is a valley near Mecca where pilgrims stay in tents and perform the stoning ritual.",
        "hint": {
            "en": "A valley near Mecca where pilgrims stay in tents and perform the stoning of the Jamarat",
            "ar": "وادٍ قرب مكة حيث يقيم الحجاج في خيام ويرمون الجمرات",
            "fr": "Une vallée près de La Mecque où les pèlerins séjournent sous des tentes et lapident les Jamarat",
        },
    },
    {
        "word": "Zamzam",
        "category": "Islamic Places",
        "short_description": "Sacred well in Mecca",
        "long_description": "Zamzam is a sacred well in Masjid al-Haram, believed to have miraculously sprung for Hajar and Ismail.",
        "hint": {
            "en": "A sacred well in Masjid al-Haram, miraculously sprung for Hajar and baby Ismail",
            "ar": "بئر مقدسة في المسجد الحرام، نبعت بمعجزة لهاجر وإسماعيل الرضيع",
            "fr": "Un puits sacré dans Masjid al-Haram, jailli miraculeusement pour Hajar et le bébé Ismaël",
        },
    },
    {
        "word": "Safa",
        "category": "Islamic Places",
        "short_description": "Hill near the Kaaba",
        "long_description": "Safa is one of the two hills between which pilgrims walk during the Sa'i ritual of Hajj and Umrah.",
        "hint": {
            "en": "One of the two hills between which pilgrims walk during the Sa'i ritual",
            "ar": "أحد التلين اللذين يسعى بينهما الحجاج في شعيرة السعي",
            "fr": "L'une des deux collines entre lesquelles les pèlerins marchent pendant le rituel du Sa'i",
        },
    },
    {
        "word": "Marwa",
        "category": "Islamic Places",
        "short_description": "Hill near the Kaaba",
        "long_description": "Marwa is the second of the two hills in the Sa'i ritual, paired with Safa.",
        "hint": {
            "en": "The second of the two hills in the Sa'i ritual, paired with Safa",
            "ar": "التل الثاني في شعيرة السعي، مقترن بالصفا",
            "fr": "La deuxième des deux collines dans le rituel du Sa'i, associée à Safa",
        },
    },
    # --- Islamic Concepts ---
    {
        "word": "Barakah",
        "category": "Islamic Concepts",
        "short_description": "Divine blessing",
        "long_description": "Barakah is the concept of divine blessing and spiritual abundance from God.",
        "hint": {
            "en": "Divine blessing and spiritual abundance bestowed by God",
            "ar": "البركة — النعمة الإلهية والوفرة الروحية من الله",
            "fr": "La bénédiction divine et l'abondance spirituelle accordées par Dieu",
        },
    },
    {
        "word": "Fitrah",
        "category": "Islamic Concepts",
        "short_description": "Natural human disposition",
        "long_description": "Fitrah is the innate human nature and disposition toward recognizing God.",
        "hint": {
            "en": "The innate human nature and disposition toward recognizing God",
            "ar": "الفطرة — الطبيعة البشرية الفطرية والميل نحو معرفة الله",
            "fr": "La nature humaine innée et la disposition naturelle à reconnaître Dieu",
        },
    },
    {
        "word": "Nafs",
        "category": "Islamic Concepts",
        "short_description": "The self or soul",
        "long_description": "Nafs refers to the self or ego in Islamic psychology, which can incline toward good or evil.",
        "hint": {
            "en": "The self or ego that can incline toward good or evil — a concept in Islamic psychology",
            "ar": "النفس — الذات أو الأنا التي قد تميل إلى الخير أو الشر",
            "fr": "Le soi ou l'ego qui peut incliner vers le bien ou le mal — un concept de psychologie islamique",
        },
    },
    {
        "word": "Ruh",
        "category": "Islamic Concepts",
        "short_description": "The spirit",
        "long_description": "Ruh is the spirit or soul breathed into humans by God, distinct from the nafs.",
        "hint": {
            "en": "The spirit breathed into humans by God, distinct from the nafs (self)",
            "ar": "الروح — التي نفخها الله في الإنسان، تختلف عن النفس",
            "fr": "L'esprit insufflé dans les humains par Dieu, distinct du nafs (soi)",
        },
    },
    {
        "word": "Qadr",
        "category": "Islamic Beliefs",
        "short_description": "Divine predestination",
        "long_description": "Qadr is the belief in divine predestination, that God has knowledge and control over all events.",
        "hint": {
            "en": "Divine predestination — the belief that God has knowledge and control over all events",
            "ar": "القدر — الإيمان بأن الله له علم وسيطرة على جميع الأحداث",
            "fr": "La prédestination divine — la croyance que Dieu a connaissance et contrôle de tous les événements",
        },
    },
    {
        "word": "Rizq",
        "category": "Islamic Concepts",
        "short_description": "Provision from God",
        "long_description": "Rizq is the sustenance and provision that God grants to all living beings.",
        "hint": {
            "en": "The sustenance and provision that God grants to all living beings",
            "ar": "الرزق — القوت والعطاء الذي يمنحه الله لجميع الكائنات الحية",
            "fr": "La subsistance et la provision que Dieu accorde à tous les êtres vivants",
        },
    },
    {
        "word": "Tawbah",
        "category": "Islamic Concepts",
        "short_description": "Repentance to God",
        "long_description": "Tawbah is the act of sincere repentance and turning back to God after committing a sin.",
        "hint": {
            "en": "Sincere repentance and turning back to God after committing a sin",
            "ar": "التوبة — الرجوع الصادق إلى الله بعد ارتكاب ذنب",
            "fr": "Le repentir sincère et le retour vers Dieu après avoir commis un péché",
        },
    },
    {
        "word": "Hidayah",
        "category": "Islamic Concepts",
        "short_description": "Divine guidance",
        "long_description": "Hidayah is the guidance that God bestows upon those who sincerely seek the truth.",
        "hint": {
            "en": "Divine guidance bestowed by God upon those who sincerely seek the truth",
            "ar": "الهداية — الإرشاد الإلهي الذي يمنحه الله لمن يطلب الحق بصدق",
            "fr": "La guidance divine accordée par Dieu à ceux qui cherchent sincèrement la vérité",
        },
    },
    {
        "word": "Niyyah",
        "category": "Islamic Concepts",
        "short_description": "Intention",
        "long_description": "Niyyah is the intention behind an act of worship, a prerequisite for all Islamic rituals.",
        "hint": {
            "en": "The intention behind an act of worship — a prerequisite for all Islamic rituals",
            "ar": "النية — القصد وراء العبادة، شرط أساسي لجميع الشعائر الإسلامية",
            "fr": "L'intention derrière un acte d'adoration — un prérequis pour tous les rituels islamiques",
        },
    },
    # --- Islamic Practices ---
    {
        "word": "Itikaf",
        "category": "Islamic Practices",
        "short_description": "Spiritual retreat in a mosque",
        "long_description": "Itikaf is a spiritual retreat in a mosque, especially during the last ten days of Ramadan.",
        "hint": {
            "en": "A spiritual retreat in a mosque, especially during the last ten days of Ramadan",
            "ar": "الاعتكاف — خلوة روحية في المسجد، خاصة في العشر الأواخر من رمضان",
            "fr": "Une retraite spirituelle dans une mosquée, surtout pendant les dix derniers jours du Ramadan",
        },
    },
    {
        "word": "Qurbani",
        "category": "Islamic Practices",
        "short_description": "Ritual animal sacrifice",
        "long_description": "Qurbani is the ritual sacrifice of an animal during Eid al-Adha in remembrance of Ibrahim.",
        "hint": {
            "en": "The ritual sacrifice of an animal during Eid al-Adha in remembrance of Ibrahim",
            "ar": "الأضحية — ذبح طقسي للحيوان في عيد الأضحى إحياءً لذكرى إبراهيم",
            "fr": "Le sacrifice rituel d'un animal pendant l'Aïd al-Adha en souvenir d'Ibrahim",
        },
    },
    {
        "word": "Aqiqah",
        "category": "Islamic Practices",
        "short_description": "Sacrifice for a newborn",
        "long_description": "Aqiqah is the sacrifice of an animal on the occasion of a child's birth as an act of gratitude.",
        "hint": {
            "en": "The sacrifice of an animal on the occasion of a child's birth as gratitude to God",
            "ar": "العقيقة — ذبيحة بمناسبة ولادة طفل شكراً لله",
            "fr": "Le sacrifice d'un animal à l'occasion de la naissance d'un enfant en gratitude envers Dieu",
        },
    },
    {
        "word": "Khutbah",
        "category": "Islamic Practices",
        "short_description": "Sermon in a mosque",
        "long_description": "Khutbah is the sermon delivered by the imam before the Friday prayer or on Eid occasions.",
        "hint": {
            "en": "The sermon delivered by the imam before Friday prayer or on Eid occasions",
            "ar": "الخطبة — الموعظة التي يلقيها الإمام قبل صلاة الجمعة أو في العيدين",
            "fr": "Le sermon prononcé par l'imam avant la prière du vendredi ou lors des fêtes de l'Aïd",
        },
    },
    {
        "word": "Taraweeh",
        "category": "Islamic Practices",
        "short_description": "Night prayers during Ramadan",
        "long_description": "Taraweeh are special night prayers performed during Ramadan after the Isha prayer.",
        "hint": {
            "en": "Special night prayers performed during Ramadan after the Isha prayer",
            "ar": "التراويح — صلوات ليلية خاصة تُؤدى في رمضان بعد صلاة العشاء",
            "fr": "Des prières nocturnes spéciales accomplies pendant le Ramadan après la prière d'Isha",
        },
    },
    {
        "word": "Tahajjud",
        "category": "Islamic Practices",
        "short_description": "Voluntary late-night prayer",
        "long_description": "Tahajjud is a voluntary prayer performed in the last third of the night, highly recommended.",
        "hint": {
            "en": "A voluntary prayer performed in the last third of the night, highly recommended",
            "ar": "التهجد — صلاة تطوعية تُؤدى في الثلث الأخير من الليل",
            "fr": "Une prière volontaire accomplie dans le dernier tiers de la nuit, très recommandée",
        },
    },
    # --- Islamic Clothing ---
    {
        "word": "Hijab",
        "category": "Islamic Clothing",
        "short_description": "Headscarf worn by Muslim women",
        "long_description": "Hijab is the headscarf worn by Muslim women as a sign of modesty and faith.",
        "hint": {
            "en": "The headscarf worn by Muslim women as a sign of modesty and faith",
            "ar": "الحجاب — غطاء الرأس الذي ترتديه المسلمات علامة على الحشمة والإيمان",
            "fr": "Le foulard porté par les femmes musulmanes comme signe de pudeur et de foi",
        },
    },
    {
        "word": "Niqab",
        "category": "Islamic Clothing",
        "short_description": "Face veil worn by some Muslim women",
        "long_description": "Niqab is a face veil covering everything except the eyes, worn by some Muslim women.",
        "hint": {
            "en": "A face veil covering everything except the eyes, worn by some Muslim women",
            "ar": "النقاب — غطاء الوجه الذي يكشف العينين فقط، ترتديه بعض المسلمات",
            "fr": "Un voile facial couvrant tout sauf les yeux, porté par certaines femmes musulmanes",
        },
    },
    {
        "word": "Thobe",
        "category": "Islamic Clothing",
        "short_description": "Long garment worn by men",
        "long_description": "Thobe is a long, loose-fitting garment traditionally worn by men in many Muslim countries.",
        "hint": {
            "en": "A long, loose-fitting garment traditionally worn by men in many Muslim countries",
            "ar": "الثوب — لباس طويل فضفاض يرتديه الرجال تقليدياً في كثير من البلدان الإسلامية",
            "fr": "Un vêtement long et ample traditionnellement porté par les hommes dans de nombreux pays musulmans",
        },
    },
    {
        "word": "Kufi",
        "category": "Islamic Clothing",
        "short_description": "Round cap worn by Muslim men",
        "long_description": "Kufi is a short, rounded cap worn by Muslim men, often during prayer.",
        "hint": {
            "en": "A short, rounded cap worn by Muslim men, often during prayer",
            "ar": "الكوفية — قبعة مستديرة قصيرة يرتديها الرجال المسلمون، غالباً أثناء الصلاة",
            "fr": "Un bonnet court et arrondi porté par les hommes musulmans, souvent pendant la prière",
        },
    },
    # --- Islamic Events ---
    {
        "word": "Isra",
        "category": "Islamic Events",
        "short_description": "Night journey from Mecca to Jerusalem",
        "long_description": "Al-Isra is the miraculous night journey of Prophet Muhammad from Mecca to Jerusalem.",
        "hint": {
            "en": "The miraculous night journey of Prophet Muhammad from Mecca to Jerusalem",
            "ar": "الإسراء — رحلة النبي محمد الليلية المعجزة من مكة إلى القدس",
            "fr": "Le voyage nocturne miraculeux du Prophète Muhammad de La Mecque à Jérusalem",
        },
    },
    {
        "word": "Miraj",
        "category": "Islamic Events",
        "short_description": "Ascension to the heavens",
        "long_description": "Al-Miraj is the ascension of Prophet Muhammad through the heavens, where prayer was ordained.",
        "hint": {
            "en": "The ascension of Prophet Muhammad through the heavens, where the five daily prayers were ordained",
            "ar": "المعراج — صعود النبي محمد عبر السماوات، حيث فُرضت الصلوات الخمس",
            "fr": "L'ascension du Prophète Muhammad à travers les cieux, où les cinq prières furent ordonnées",
        },
    },
    {
        "word": "Mawlid",
        "category": "Islamic Events",
        "short_description": "Celebration of the Prophet's birth",
        "long_description": "Mawlid is the observance of the birth of Prophet Muhammad, celebrated in many Muslim cultures.",
        "hint": {
            "en": "The observance of the birth of Prophet Muhammad, celebrated in many Muslim cultures",
            "ar": "المولد النبوي — الاحتفال بذكرى ميلاد النبي محمد",
            "fr": "La commémoration de la naissance du Prophète Muhammad, célébrée dans de nombreuses cultures musulmanes",
        },
    },
]

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
    # --- New pairs ---
    # Prophets
    ("Nuh", "Ibrahim"),
    ("Yusuf", "Yaqub"),
    ("Dawud", "Sulayman"),
    ("Musa", "Harun"),
    ("Hud", "Salih"),
    ("Yunus", "Ayyub"),
    ("Lut", "Shuayb"),
    ("Adam", "Idris"),
    ("Ismail", "Yusuf"),
    ("Isa", "Nuh"),
    # Companions
    ("Abu Bakr", "Umar"),
    ("Uthman", "Ali"),
    ("Bilal", "Khalid ibn al-Walid"),
    ("Khadijah", "Abu Bakr"),
    # Places
    ("Al-Aqsa", "Kaaba"),
    ("Arafat", "Muzdalifah"),
    ("Mina", "Arafat"),
    ("Safa", "Marwa"),
    ("Zamzam", "Kaaba"),
    ("Medina", "Al-Aqsa"),
    # Concepts
    ("Barakah", "Rizq"),
    ("Nafs", "Ruh"),
    ("Fitrah", "Hidayah"),
    ("Qadr", "Tawakkul"),
    ("Tawbah", "Sabr"),
    ("Niyyah", "Ihsan"),
    # Practices
    ("Taraweeh", "Tahajjud"),
    ("Qurbani", "Aqiqah"),
    ("Itikaf", "Taraweeh"),
    ("Khutbah", "Jummah"),
    # Clothing
    ("Hijab", "Niqab"),
    ("Thobe", "Kufi"),
    # Events
    ("Isra", "Miraj"),
    ("Mawlid", "Hijrah"),
    ("Eid al-Adha", "Qurbani"),
]


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
        existing = (await session.exec(select(Word).where(Word.word == word_data["word"]))).first()
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
            await session.exec(select(TermPair).where(TermPair.word1_id == w1.id, TermPair.word2_id == w2.id))
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
