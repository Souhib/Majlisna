/**
 * What this app never sweeps, strikes or wipes across (DESIGN.md §7, "nothing ever passes over a
 * sacred name"): a name of Allah (Allah, -illah, -ullah, ar-Rahman, ﷲ, ﷻ, and the words the hints
 * use for Him in English and French), the Prophet ﷺ, the prophets and the words for them, Jibril,
 * the Qur'an and the Kaaba, in the three languages. One list for every gesture that would pass
 * over a text: the samar riddle's line (`SamarRiddle`) and the Codenames clue (`ClueBanner`),
 * which the spymaster types freely. The Quiz strikes an option's letter, never the word, for the
 * same reason. A wider net only turns a sweep into a fade: about a quarter of the riddles' rung-1
 * lines fade, the rest are written.
 */

// Harakat, the dagger alif, Qur'anic marks and the tatweel: "اللَّه" is "الله".
const ARABIC_MARKS = /[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]/g
const SACRED_LATIN = new RegExp(
  [
    "llah",
    "rahm[aâā]n",
    "\\b(?:god|lord|dieu|seigneur|muhammad|mohammed|mohamed|prophets?|proph[eè]tes?|messengers?|messagers?|apostles?|jibr[iī]l|gabriel|qur.?an|coran|kaaba|ka.?bah",
    "adam|idris|enoch|nuh|noah|no[eé]|hud|salih|ibrahim|abraham|lut|lot|isma[iï]l|ishmael|ishaq|isaac|ya[qc]ub|jacob|yusuf|joseph",
    "ayyub|job|shu[ae]yb|musa|moses|mo[iï]se|harun|aaron|dhul[- ]?kifl|dawud|david|sulayman|solomon|salomon|ilyas|elijah|[eé]lie",
    "al[- ]?yasa|elisha|yunus|jonah|jonas|zakariy?y?a|zechariah|zacharie|yahya|john|jean|isa|jesus|j[eé]sus)\\b",
  ].join("|"),
  "i",
)
const SACRED_ARABIC =
  /لله|رحمن|محمد|نبي|أنبياء|انبياء|رسول|رسل|آدم|ادم|إدريس|نوح|هود|صالح|إبراهيم|ابراهيم|لوط|إسماعيل|إسحاق|يعقوب|يوسف|أيوب|شعيب|موسى|هارون|الكفل|داود|سليمان|إلياس|اليسع|يونس|زكريا|يحيى|عيسى|جبريل|قرآن|الكعبة|[\ufdf2\ufdfa\ufdfb]/

/**
 * Whether a line holds a name of Allah, of the Prophet ﷺ or of a prophet, or names the
 * Qur'an or the Kaaba. Such a line is never swept or wiped across (DESIGN.md §7, "nothing
 * ever passes over a sacred name"): it fades in.
 */
export function holdsSacredName(text: string): boolean {
  return SACRED_LATIN.test(text) || SACRED_ARABIC.test(text.replace(ARABIC_MARKS, ""))
}
