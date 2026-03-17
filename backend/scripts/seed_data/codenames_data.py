"""Codenames game seed data — Islamic word packs."""

from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack

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
        {"word": "Dhul-Kifl", "hint": {"en": "Prophet mentioned in the Quran, known for his patience and righteousness", "ar": "ذو الكفل — نبي ذُكر في القرآن، عُرف بصبره وصلاحه", "fr": "Prophète mentionné dans le Coran, connu pour sa patience et sa droiture"}},
        {"word": "Ilyas", "hint": {"en": "Prophet Elijah, who called his people to worship Allah alone", "ar": "النبي إلياس، الذي دعا قومه لعبادة الله وحده", "fr": "Le prophète Élie, qui appela son peuple à adorer Allah seul"}},
        {"word": "Al-Yasa", "hint": {"en": "Prophet Elisha, successor of Ilyas and a righteous servant of God", "ar": "النبي اليسع، خليفة إلياس وعبد صالح لله", "fr": "Le prophète Élisée, successeur d'Ilyas et serviteur vertueux de Dieu"}},
        {"word": "Zakariya", "hint": {"en": "Prophet Zechariah, guardian of Maryam and father of Yahya", "ar": "النبي زكريا، كافل مريم وأبو يحيى", "fr": "Le prophète Zacharie, tuteur de Maryam et père de Yahya"}},
        {"word": "Yahya", "hint": {"en": "Prophet John the Baptist, son of Zakariya, known for his piety", "ar": "النبي يحيى، ابن زكريا، عُرف بتقواه", "fr": "Le prophète Jean-Baptiste, fils de Zacharie, connu pour sa piété"}},
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
        {"word": "Waqiah", "hint": {"en": "The Event — surah about the Day of Judgment and the three groups of people", "ar": "الواقعة — سورة عن يوم القيامة وأصناف الناس الثلاثة", "fr": "L'Événement — sourate sur le Jour du Jugement et les trois groupes de personnes"}},
        {"word": "Dukhan", "hint": {"en": "The Smoke — surah warning about a day when the sky will bring visible smoke", "ar": "الدخان — سورة تحذر من يوم تأتي السماء بدخان مبين", "fr": "La Fumée — sourate avertissant d'un jour où le ciel apportera une fumée visible"}},
        {"word": "Hadid", "hint": {"en": "The Iron — surah discussing the power of God and the nature of worldly life", "ar": "الحديد — سورة تتحدث عن قدرة الله وطبيعة الحياة الدنيا", "fr": "Le Fer — sourate sur la puissance de Dieu et la nature de la vie mondaine"}},
        {"word": "Furqan", "hint": {"en": "The Criterion — surah named after the Quran's role in distinguishing truth from falsehood", "ar": "الفرقان — سورة سُميت بدور القرآن في التمييز بين الحق والباطل", "fr": "Le Discernement — sourate nommée d'après le rôle du Coran à distinguer le vrai du faux"}},
        {"word": "Nur", "hint": {"en": "The Light — surah containing the famous Verse of Light and rulings on modesty", "ar": "النور — سورة تحتوي آية النور الشهيرة وأحكام الحشمة", "fr": "La Lumière — sourate contenant le célèbre Verset de la Lumière et les règles de pudeur"}},
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
        {"word": "Hattin", "hint": {"en": "Battle in 1187 CE where Saladin defeated the Crusaders and liberated Jerusalem", "ar": "حطين — معركة عام 1187م هزم فيها صلاح الدين الصليبيين وحرر القدس", "fr": "Bataille de 1187 où Saladin vainquit les croisés et libéra Jérusalem"}},
        {"word": "Ain Jalut", "hint": {"en": "Battle in 1260 CE where the Mamluks defeated the Mongols, halting their advance", "ar": "عين جالوت — معركة عام 1260م هزم فيها المماليك المغول وأوقفوا تقدمهم", "fr": "Bataille de 1260 où les Mamelouks vainquirent les Mongols, stoppant leur avancée"}},
        {"word": "Timbuktu", "hint": {"en": "West African center of Islamic learning, home to Sankore University", "ar": "تمبكتو — مركز العلم الإسلامي في غرب أفريقيا، موطن جامعة سنكوري", "fr": "Centre ouest-africain de savoir islamique, siège de l'Université de Sankoré"}},
        {"word": "Fatimid", "hint": {"en": "Shia Islamic dynasty that founded Cairo and Al-Azhar (909-1171 CE)", "ar": "الفاطميون — سلالة إسلامية شيعية أسست القاهرة والأزهر", "fr": "Dynastie islamique chiite qui fonda Le Caire et Al-Azhar (909-1171)"}},
        {"word": "Seljuk", "hint": {"en": "Turkic dynasty that championed Sunni Islam and founded the Nizamiyyah schools", "ar": "السلاجقة — سلالة تركية ناصرت الإسلام السني وأسست المدارس النظامية", "fr": "Dynastie turque qui défendit l'islam sunnite et fonda les écoles Nizamiyyah"}},
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
        {"word": "Umrah", "hint": {"en": "The lesser pilgrimage to Mecca, performed at any time of the year", "ar": "العمرة — الحج الأصغر إلى مكة، يُؤدى في أي وقت من السنة", "fr": "Le petit pèlerinage à La Mecque, effectué à tout moment de l'année"}},
        {"word": "Dua", "hint": {"en": "Supplication — personal prayer and direct communication with Allah", "ar": "الدعاء — صلاة شخصية وتواصل مباشر مع الله", "fr": "L'invocation — prière personnelle et communication directe avec Allah"}},
        {"word": "Sadaqah", "hint": {"en": "Voluntary charity given beyond the obligatory Zakat", "ar": "الصدقة — التبرع الطوعي فوق الزكاة الواجبة", "fr": "L'aumône volontaire donnée au-delà de la Zakat obligatoire"}},
        {"word": "Itikaf", "hint": {"en": "Spiritual retreat in the mosque, especially during the last ten days of Ramadan", "ar": "الاعتكاف — خلوة روحية في المسجد، خاصة في العشر الأواخر من رمضان", "fr": "La retraite spirituelle à la mosquée, surtout les dix derniers jours du Ramadan"}},
        {"word": "Janazah", "hint": {"en": "The funeral prayer performed for a deceased Muslim", "ar": "صلاة الجنازة — الصلاة على المسلم المتوفى", "fr": "La prière funéraire accomplie pour un musulman décédé"}},
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
        {"word": "Ukhuwwah", "hint": {"en": "Brotherhood — the bond of faith uniting all Muslims", "ar": "الأخوة — رابطة الإيمان التي تجمع المسلمين", "fr": "La fraternité — le lien de foi unissant tous les musulmans"}},
        {"word": "Iffah", "hint": {"en": "Chastity and self-restraint, protecting one's honor", "ar": "العفة — ضبط النفس وحفظ العرض", "fr": "La chasteté et la maîtrise de soi, protégeant son honneur"}},
        {"word": "Hilm", "hint": {"en": "Forbearance and gentleness, controlling anger with wisdom", "ar": "الحلم — التسامح واللطف، ضبط الغضب بحكمة", "fr": "L'indulgence et la douceur, maîtriser la colère avec sagesse"}},
        {"word": "Shura", "hint": {"en": "Mutual consultation — making decisions through collective counsel", "ar": "الشورى — اتخاذ القرارات من خلال التشاور الجماعي", "fr": "La consultation mutuelle — prendre des décisions par le conseil collectif"}},
        {"word": "Rifq", "hint": {"en": "Gentleness and kindness in dealing with others", "ar": "الرفق — اللطف واللين في التعامل مع الآخرين", "fr": "La douceur et la gentillesse dans les relations avec autrui"}},
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
        {"word": "Ijma", "hint": {"en": "Scholarly consensus — agreement of Muslim scholars on a legal ruling", "ar": "الإجماع — اتفاق العلماء المسلمين على حكم شرعي", "fr": "Le consensus savant — accord des savants musulmans sur un jugement juridique"}},
        {"word": "Qiyas", "hint": {"en": "Analogical reasoning — deriving rulings by comparing to established cases", "ar": "القياس — استنباط الأحكام بالمقارنة مع حالات ثابتة", "fr": "Le raisonnement analogique — dériver des jugements par comparaison avec des cas établis"}},
        {"word": "Isnad", "hint": {"en": "Chain of narration — the sequence of transmitters for a hadith", "ar": "الإسناد — سلسلة الرواة الذين نقلوا الحديث", "fr": "La chaîne de narration — la séquence des transmetteurs d'un hadith"}},
        {"word": "Matn", "hint": {"en": "The text or content of a hadith, as opposed to its chain of narration", "ar": "المتن — نص الحديث ومحتواه، مقابل سلسلة الإسناد", "fr": "Le texte ou contenu d'un hadith, par opposition à sa chaîne de narration"}},
        {"word": "Jarh", "hint": {"en": "Hadith criticism — the science of evaluating narrator reliability", "ar": "الجرح والتعديل — علم تقييم موثوقية الرواة", "fr": "La critique du hadith — la science d'évaluation de la fiabilité des narrateurs"}},
        {"word": "Maqasid", "hint": {"en": "Higher objectives of Islamic law — preservation of life, faith, intellect, lineage, and wealth", "ar": "مقاصد الشريعة — حفظ النفس والدين والعقل والنسل والمال", "fr": "Les objectifs supérieurs de la loi islamique — préservation de la vie, foi, intellect, lignée et richesse"}},
        {"word": "Ilm al-Rijal", "hint": {"en": "Science of hadith narrators — biographical evaluation of transmitters", "ar": "علم الرجال — التقييم السيري لرواة الحديث", "fr": "La science des narrateurs de hadith — évaluation biographique des transmetteurs"}},
    ],
    "Companions & Figures": [
        {"word": "Abu Bakr", "hint": {"en": "The first Caliph and closest companion of the Prophet, known as al-Siddiq", "ar": "أبو بكر الصديق — أول الخلفاء الراشدين وأقرب صحابي للنبي", "fr": "Le premier calife et plus proche compagnon du Prophète, surnommé al-Siddiq"}},
        {"word": "Umar", "hint": {"en": "The second Caliph, known as al-Faruq for his strong sense of justice", "ar": "عمر بن الخطاب — الخليفة الثاني، لُقب بالفاروق لعدله", "fr": "Le deuxième calife, surnommé al-Faruq pour son sens aigu de la justice"}},
        {"word": "Uthman", "hint": {"en": "The third Caliph who compiled the Quran into a single standard text", "ar": "عثمان بن عفان — الخليفة الثالث الذي جمع القرآن في مصحف واحد", "fr": "Le troisième calife qui compila le Coran en un texte unique et standard"}},
        {"word": "Ali", "hint": {"en": "The fourth Caliph, cousin and son-in-law of the Prophet, known for his bravery and knowledge", "ar": "علي بن أبي طالب — الخليفة الرابع، ابن عم النبي وصهره، عُرف بشجاعته وعلمه", "fr": "Le quatrième calife, cousin et gendre du Prophète, connu pour sa bravoure et son savoir"}},
        {"word": "Bilal", "hint": {"en": "The first muezzin of Islam, an Abyssinian freed slave who endured persecution for his faith", "ar": "بلال بن رباح — أول مؤذن في الإسلام، عبد حبشي مُعتق صبر على الأذى في سبيل إيمانه", "fr": "Le premier muezzin de l'islam, un esclave abyssin affranchi qui endura la persécution pour sa foi"}},
        {"word": "Khalid", "hint": {"en": "Khalid ibn al-Walid, the Sword of Allah, one of Islam's greatest military commanders", "ar": "خالد بن الوليد — سيف الله المسلول، أحد أعظم القادة العسكريين في الإسلام", "fr": "Khalid ibn al-Walid, le Sabre d'Allah, l'un des plus grands commandants militaires de l'islam"}},
        {"word": "Aisha", "hint": {"en": "Wife of the Prophet and renowned scholar who narrated over 2,000 hadiths", "ar": "عائشة بنت أبي بكر — زوجة النبي وعالمة روت أكثر من 2000 حديث", "fr": "Épouse du Prophète et savante renommée qui rapporta plus de 2 000 hadiths"}},
        {"word": "Fatimah", "hint": {"en": "Daughter of the Prophet, wife of Ali, and mother of Hasan and Husayn", "ar": "فاطمة الزهراء — بنت النبي وزوجة علي وأم الحسن والحسين", "fr": "Fille du Prophète, épouse d'Ali et mère de Hasan et Husayn"}},
        {"word": "Hamza", "hint": {"en": "Uncle of the Prophet, known as the Lion of Allah, martyred at Uhud", "ar": "حمزة بن عبد المطلب — عم النبي، أسد الله، استُشهد في أحد", "fr": "Oncle du Prophète, surnommé le Lion d'Allah, martyr à Uhud"}},
        {"word": "Salman", "hint": {"en": "Salman al-Farisi, the Persian companion who suggested digging the trench at Khandaq", "ar": "سلمان الفارسي — الصحابي الفارسي الذي اقترح حفر الخندق", "fr": "Salman al-Farisi, le compagnon perse qui suggéra de creuser le fossé à Khandaq"}},
        {"word": "Abu Hurairah", "hint": {"en": "Companion who narrated the most hadiths, known for his incredible memory", "ar": "أبو هريرة — الصحابي الأكثر رواية للحديث، عُرف بذاكرته الاستثنائية", "fr": "Compagnon qui rapporta le plus de hadiths, connu pour sa mémoire incroyable"}},
        {"word": "Zubayr", "hint": {"en": "Al-Zubayr ibn al-Awwam, one of the ten promised Paradise and the Prophet's disciple", "ar": "الزبير بن العوام — أحد العشرة المبشرين بالجنة وحواري النبي", "fr": "Al-Zubayr ibn al-Awwam, l'un des dix promis au Paradis et disciple du Prophète"}},
        {"word": "Talha", "hint": {"en": "Talha ibn Ubaydullah, one of the ten promised Paradise, who shielded the Prophet at Uhud", "ar": "طلحة بن عبيد الله — أحد العشرة المبشرين بالجنة، حمى النبي يوم أحد", "fr": "Talha ibn Ubaydullah, l'un des dix promis au Paradis, qui protégea le Prophète à Uhud"}},
        {"word": "Saad", "hint": {"en": "Saad ibn Abi Waqqas, the first to shoot an arrow for Islam and conqueror of Persia", "ar": "سعد بن أبي وقاص — أول من رمى بسهم في الإسلام وفاتح فارس", "fr": "Saad ibn Abi Waqqas, le premier à décocher une flèche pour l'islam et conquérant de la Perse"}},
        {"word": "Khadijah", "hint": {"en": "First wife of the Prophet and first person to accept Islam, a successful businesswoman", "ar": "خديجة بنت خويلد — أولى زوجات النبي وأول من أسلم، سيدة أعمال ناجحة", "fr": "Première épouse du Prophète et première personne à accepter l'islam, femme d'affaires prospère"}},
        {"word": "Hafsa", "hint": {"en": "Daughter of Umar and wife of the Prophet, entrusted with the written Quran manuscript", "ar": "حفصة بنت عمر — زوجة النبي، أُودع عندها المصحف المكتوب", "fr": "Fille d'Umar et épouse du Prophète, à qui fut confié le manuscrit du Coran"}},
        {"word": "Umar ibn Abdul Aziz", "hint": {"en": "Umayyad caliph known as the fifth rightly guided caliph for his justice and piety", "ar": "عمر بن عبد العزيز — الخليفة الأموي المعروف بالخليفة الراشد الخامس لعدله وتقواه", "fr": "Calife omeyyade surnommé le cinquième calife bien guidé pour sa justice et sa piété"}},
        {"word": "Tariq ibn Ziyad", "hint": {"en": "Berber commander who led the Muslim conquest of the Iberian Peninsula in 711 CE", "ar": "طارق بن زياد — القائد الأمازيغي الذي فتح شبه الجزيرة الإيبيرية عام 711م", "fr": "Commandant berbère qui mena la conquête musulmane de la péninsule ibérique en 711"}},
        {"word": "Saladin", "hint": {"en": "Salah al-Din al-Ayyubi, who liberated Jerusalem from the Crusaders in 1187 CE", "ar": "صلاح الدين الأيوبي — محرر القدس من الصليبيين عام 1187م", "fr": "Salah al-Din al-Ayyubi, qui libéra Jérusalem des croisés en 1187"}},
        {"word": "Ibn Battuta", "hint": {"en": "Moroccan traveler who journeyed over 120,000 km across the Islamic world in the 14th century", "ar": "ابن بطوطة — الرحالة المغربي الذي قطع أكثر من 120,000 كم في العالم الإسلامي في القرن 14", "fr": "Voyageur marocain qui parcourut plus de 120 000 km à travers le monde islamique au XIVe siècle"}},
    ],
    "Daily Life & Culture": [
        {"word": "Halal", "hint": {"en": "Permissible according to Islamic law, especially regarding food and conduct", "ar": "حلال — ما أباحه الشرع الإسلامي، خاصة في الطعام والسلوك", "fr": "Permis selon la loi islamique, surtout concernant la nourriture et la conduite"}},
        {"word": "Haram", "hint": {"en": "Forbidden according to Islamic law, the opposite of Halal", "ar": "حرام — ما حرمه الشرع الإسلامي، عكس الحلال", "fr": "Interdit selon la loi islamique, l'opposé du Halal"}},
        {"word": "Hijab", "hint": {"en": "Modest head covering worn by Muslim women as an act of faith", "ar": "الحجاب — غطاء الرأس المحتشم الذي ترتديه المسلمات تعبيراً عن إيمانهن", "fr": "Le voile modeste porté par les femmes musulmanes comme acte de foi"}},
        {"word": "Niqab", "hint": {"en": "Face veil that covers the face except the eyes, worn by some Muslim women", "ar": "النقاب — غطاء الوجه الذي يكشف العينين فقط، ترتديه بعض المسلمات", "fr": "Le voile facial qui couvre le visage sauf les yeux, porté par certaines femmes musulmanes"}},
        {"word": "Thobe", "hint": {"en": "Traditional long garment worn by men in many Muslim countries", "ar": "الثوب — لباس طويل تقليدي يرتديه الرجال في كثير من البلدان الإسلامية", "fr": "Vêtement long traditionnel porté par les hommes dans de nombreux pays musulmans"}},
        {"word": "Kufi", "hint": {"en": "Rounded cap worn by Muslim men, especially during prayer", "ar": "الكوفية — طاقية مستديرة يرتديها الرجال المسلمون، خاصة أثناء الصلاة", "fr": "Calotte arrondie portée par les hommes musulmans, surtout pendant la prière"}},
        {"word": "Miswak", "hint": {"en": "Natural tooth-cleaning twig from the Arak tree, a Prophetic tradition", "ar": "المسواك — عود تنظيف الأسنان الطبيعي من شجرة الأراك، سنة نبوية", "fr": "Bâtonnet naturel de nettoyage des dents issu de l'arbre Arak, une tradition prophétique"}},
        {"word": "Attar", "hint": {"en": "Natural perfume oil, following the Prophetic tradition of wearing fragrance", "ar": "العطر — زيت عطري طبيعي، اتباعاً لسنة النبي في التطيب", "fr": "Huile de parfum naturelle, suivant la tradition prophétique de porter du parfum"}},
        {"word": "Dates", "hint": {"en": "The fruit recommended by the Prophet for breaking fast, staple of Islamic culture", "ar": "التمر — الفاكهة التي أوصى بها النبي للإفطار، من أساسيات الثقافة الإسلامية", "fr": "Le fruit recommandé par le Prophète pour rompre le jeûne, incontournable de la culture islamique"}},
        {"word": "Zamzam", "hint": {"en": "Sacred well in Mecca, miraculously provided for Hajar and baby Ismail", "ar": "زمزم — البئر المقدسة في مكة، أُنبعت بمعجزة لهاجر والطفل إسماعيل", "fr": "Puits sacré à La Mecque, miraculeusement fourni pour Hajar et le bébé Ismaël"}},
        {"word": "Oud", "hint": {"en": "Fragrant agarwood incense, deeply rooted in Islamic hospitality traditions", "ar": "العود — بخور خشب العقر العطري، متجذر في تقاليد الضيافة الإسلامية", "fr": "L'encens de bois d'agar parfumé, profondément ancré dans les traditions d'hospitalité islamique"}},
        {"word": "Henna", "hint": {"en": "Natural plant dye used for body art, especially at Islamic weddings and celebrations", "ar": "الحناء — صبغة نباتية طبيعية تُستخدم لتزيين الجسم، خاصة في الأعراس والمناسبات", "fr": "Teinture végétale naturelle utilisée pour l'art corporel, surtout lors des mariages et célébrations islamiques"}},
        {"word": "Bismillah", "hint": {"en": "'In the name of Allah' — phrase said before beginning any action", "ar": "بسم الله — عبارة تُقال قبل البدء بأي عمل", "fr": "'Au nom d'Allah' — formule prononcée avant de commencer toute action"}},
        {"word": "Masha'Allah", "hint": {"en": "'As God has willed' — expression of appreciation and protection from envy", "ar": "ما شاء الله — تعبير عن الإعجاب والحماية من الحسد", "fr": "'Comme Dieu l'a voulu' — expression d'appréciation et de protection contre l'envie"}},
        {"word": "SubhanAllah", "hint": {"en": "'Glory be to God' — expression of awe and glorification of Allah", "ar": "سبحان الله — تعبير عن الإعجاب وتنزيه الله", "fr": "'Gloire à Dieu' — expression d'émerveillement et de glorification d'Allah"}},
        {"word": "Alhamdulillah", "hint": {"en": "'Praise be to God' — expression of gratitude said on all occasions", "ar": "الحمد لله — تعبير عن الشكر يُقال في كل المناسبات", "fr": "'Louange à Dieu' — expression de gratitude dite en toute occasion"}},
        {"word": "In sha Allah", "hint": {"en": "'God willing' — said when referring to a future event or intention", "ar": "إن شاء الله — تُقال عند الإشارة إلى حدث مستقبلي أو نية", "fr": "'Si Dieu le veut' — dit en se référant à un événement futur ou une intention"}},
        {"word": "Barakah", "hint": {"en": "Divine blessing and abundance that Allah places in things, time, or people", "ar": "البركة — النعمة والزيادة الإلهية التي يضعها الله في الأشياء أو الأوقات أو الناس", "fr": "La bénédiction divine et l'abondance qu'Allah place dans les choses, le temps ou les personnes"}},
        {"word": "Waqf", "hint": {"en": "Islamic endowment — donating property for charitable purposes in perpetuity", "ar": "الوقف — تخصيص ملكية للأعمال الخيرية بشكل دائم", "fr": "La dotation islamique — don de propriété à des fins charitables à perpétuité"}},
        {"word": "Nikah", "hint": {"en": "The Islamic marriage contract, a sacred bond between husband and wife", "ar": "النكاح — عقد الزواج الإسلامي، رابطة مقدسة بين الزوجين", "fr": "Le contrat de mariage islamique, un lien sacré entre mari et femme"}},
    ],
    "Sacred Places & Architecture": [
        {"word": "Kaaba", "hint": {"en": "The cube-shaped sacred house in Mecca, the qibla toward which Muslims pray", "ar": "الكعبة — البيت الحرام المكعب في مكة، القبلة التي يصلي إليها المسلمون", "fr": "La maison sacrée cubique à La Mecque, la qibla vers laquelle les musulmans prient"}},
        {"word": "Al-Aqsa", "hint": {"en": "The farthest mosque in Jerusalem, destination of the Prophet's Night Journey", "ar": "المسجد الأقصى — المسجد في القدس، وجهة رحلة الإسراء والمعراج", "fr": "La mosquée la plus éloignée à Jérusalem, destination du Voyage nocturne du Prophète"}},
        {"word": "Dome of the Rock", "hint": {"en": "Iconic golden-domed shrine in Jerusalem built over the sacred rock", "ar": "قبة الصخرة — المعلم ذو القبة الذهبية في القدس المبني فوق الصخرة المقدسة", "fr": "Le sanctuaire emblématique au dôme doré à Jérusalem, construit sur le rocher sacré"}},
        {"word": "Arafat", "hint": {"en": "The plain where pilgrims stand in prayer on the 9th of Dhul Hijjah, the essence of Hajj", "ar": "عرفات — السهل الذي يقف فيه الحجاج يوم التاسع من ذي الحجة، ركن الحج الأعظم", "fr": "La plaine où les pèlerins se tiennent en prière le 9 Dhul Hijjah, l'essence du Hajj"}},
        {"word": "Muzdalifah", "hint": {"en": "Open area between Arafat and Mina where pilgrims spend the night and collect pebbles", "ar": "مزدلفة — منطقة مفتوحة بين عرفات ومنى يبيت فيها الحجاج ويجمعون الحصى", "fr": "Zone ouverte entre Arafat et Mina où les pèlerins passent la nuit et ramassent des cailloux"}},
        {"word": "Mina", "hint": {"en": "Valley near Mecca where pilgrims perform the stoning of the Jamarat during Hajj", "ar": "منى — وادٍ قرب مكة يرمي فيه الحجاج الجمرات أثناء الحج", "fr": "Vallée près de La Mecque où les pèlerins effectuent la lapidation des Jamarat pendant le Hajj"}},
        {"word": "Safa", "hint": {"en": "One of the two hills between which pilgrims walk during Sai, linked to Hajar's search for water", "ar": "الصفا — أحد التلين اللذين يسعى بينهما الحجاج، مرتبط بسعي هاجر بحثاً عن الماء", "fr": "L'une des deux collines entre lesquelles les pèlerins marchent pendant le Sai, liée à la quête d'eau de Hajar"}},
        {"word": "Marwa", "hint": {"en": "The second hill of Sai, where Hajar ran searching for water for baby Ismail", "ar": "المروة — التل الثاني في السعي، حيث ركضت هاجر بحثاً عن الماء لإسماعيل", "fr": "La seconde colline du Sai, où Hajar courut à la recherche d'eau pour le bébé Ismaël"}},
        {"word": "Quba", "hint": {"en": "Site of the first mosque built in Islam, in Medina, with the reward of an Umrah for praying there", "ar": "قباء — موقع أول مسجد بُني في الإسلام بالمدينة، الصلاة فيه كأجر عمرة", "fr": "Site de la première mosquée construite en islam, à Médine, avec la récompense d'une Omra pour y prier"}},
        {"word": "Hira", "hint": {"en": "The cave on Jabal al-Nur where the Prophet received the first revelation", "ar": "غار حراء — الغار في جبل النور حيث نزل الوحي الأول على النبي", "fr": "La grotte sur le Jabal al-Nur où le Prophète reçut la première révélation"}},
        {"word": "Thawr", "hint": {"en": "The cave where the Prophet and Abu Bakr hid during the Hijrah migration", "ar": "غار ثور — الغار الذي اختبأ فيه النبي وأبو بكر أثناء الهجرة", "fr": "La grotte où le Prophète et Abu Bakr se cachèrent pendant la migration de l'Hégire"}},
        {"word": "Jabal Nur", "hint": {"en": "Mountain of Light in Mecca, home to the Cave of Hira", "ar": "جبل النور — جبل في مكة يحتضن غار حراء", "fr": "La Montagne de Lumière à La Mecque, abritant la grotte de Hira"}},
        {"word": "Black Stone", "hint": {"en": "The sacred stone set in the eastern corner of the Kaaba, kissed during Tawaf", "ar": "الحجر الأسود — الحجر المقدس في الركن الشرقي للكعبة، يُقبّل أثناء الطواف", "fr": "La pierre sacrée placée dans le coin est de la Kaaba, embrassée pendant le Tawaf"}},
        {"word": "Mihrab", "hint": {"en": "The prayer niche in a mosque wall indicating the direction of Mecca", "ar": "المحراب — التجويف في جدار المسجد يشير إلى اتجاه مكة", "fr": "La niche de prière dans le mur d'une mosquée indiquant la direction de La Mecque"}},
        {"word": "Minbar", "hint": {"en": "The pulpit in a mosque from which the imam delivers the Friday sermon", "ar": "المنبر — المنصة في المسجد التي يلقي منها الإمام خطبة الجمعة", "fr": "La chaire dans une mosquée d'où l'imam prononce le sermon du vendredi"}},
        {"word": "Minaret", "hint": {"en": "The tower of a mosque from which the call to prayer is announced", "ar": "المئذنة — برج المسجد الذي يُؤذَّن منه للصلاة", "fr": "La tour d'une mosquée d'où l'appel à la prière est annoncé"}},
    ],
}


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
