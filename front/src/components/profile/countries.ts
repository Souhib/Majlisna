/**
 * Countries as the server stores them: ISO 3166-1 alpha-3 codes, exactly the set
 * pycountry accepts (backend `UserBase.country_code`). Names come from the browser in
 * the page's language (Intl.DisplayNames needs the alpha-2 code), so no list of 249
 * names has to be translated and kept in three locale files.
 */

// alpha-3 + alpha-2, five letters per country (pycountry 249 entries)
const PAIRS =
  "ABWAW AFGAF AGOAO AIAAI ALAAX ALBAL ANDAD AREAE ARGAR ARMAM ASMAS ATAAQ ATFTF ATGAG AUSAU AUTAT AZEAZ BDIBI BELBE BENBJ BESBQ BFABF BGDBD BGRBG BHRBH BHSBS BIHBA BLMBL BLRBY BLZBZ BMUBM BOLBO BRABR BRBBB BRNBN BTNBT BVTBV BWABW CAFCF CANCA CCKCC CHECH CHLCL CHNCN CIVCI CMRCM CODCD COGCG COKCK COLCO COMKM CPVCV CRICR CUBCU CUWCW CXRCX CYMKY CYPCY CZECZ DEUDE DJIDJ DMADM DNKDK DOMDO DZADZ ECUEC EGYEG ERIER ESHEH ESPES ESTEE ETHET FINFI FJIFJ FLKFK FRAFR FROFO FSMFM GABGA GBRGB GEOGE GGYGG GHAGH GIBGI GINGN GLPGP GMBGM GNBGW GNQGQ GRCGR GRDGD GRLGL GTMGT GUFGF GUMGU GUYGY HKGHK HMDHM HNDHN HRVHR HTIHT HUNHU IDNID IMNIM INDIN IOTIO IRLIE IRNIR IRQIQ ISLIS ISRIL ITAIT JAMJM JEYJE JORJO JPNJP KAZKZ KENKE KGZKG KHMKH KIRKI KNAKN KORKR KWTKW LAOLA LBNLB LBRLR LBYLY LCALC LIELI LKALK LSOLS LTULT LUXLU LVALV MACMO MAFMF MARMA MCOMC MDAMD MDGMG MDVMV MEXMX MHLMH MKDMK MLIML MLTMT MMRMM MNEME MNGMN MNPMP MOZMZ MRTMR MSRMS MTQMQ MUSMU MWIMW MYSMY MYTYT NAMNA NCLNC NERNE NFKNF NGANG NICNI NIUNU NLDNL NORNO NPLNP NRUNR NZLNZ OMNOM PAKPK PANPA PCNPN PERPE PHLPH PLWPW PNGPG POLPL PRIPR PRKKP PRTPT PRYPY PSEPS PYFPF QATQA REURE ROURO RUSRU RWARW SAUSA SDNSD SENSN SGPSG SGSGS SHNSH SJMSJ SLBSB SLESL SLVSV SMRSM SOMSO SPMPM SRBRS SSDSS STPST SURSR SVKSK SVNSI SWESE SWZSZ SXMSX SYCSC SYRSY TCATC TCDTD TGOTG THATH TJKTJ TKLTK TKMTM TLSTL TONTO TTOTT TUNTN TURTR TUVTV TWNTW TZATZ UGAUG UKRUA UMIUM URYUY USAUS UZBUZ VATVA VCTVC VENVE VGBVG VIRVI VNMVN VUTVU WLFWF WSMWS YEMYE ZAFZA ZMBZM ZWEZW"

const ALPHA2 = new Map(PAIRS.split(" ").map((p) => [p.slice(0, 3), p.slice(3)]))

export const COUNTRY_CODES: string[] = [...ALPHA2.keys()]

function displayNames(lang: string): Intl.DisplayNames | null {
  try {
    return new Intl.DisplayNames([lang, "en"], { type: "region" })
  } catch {
    return null
  }
}

/** The country's name in `lang` ("Morocco", « Maroc », «المغرب»); the code itself when unknown. */
export function countryName(alpha3: string | null | undefined, lang: string): string | null {
  if (!alpha3) return null
  const a2 = ALPHA2.get(alpha3.toUpperCase())
  if (!a2) return alpha3
  return displayNames(lang)?.of(a2) ?? alpha3
}

/** Every country as { code, name }, sorted by name in the page's language. */
export function countryOptions(lang: string): { code: string; name: string }[] {
  const names = displayNames(lang)
  const collator = new Intl.Collator(lang)
  return COUNTRY_CODES.map((code) => ({ code, name: names?.of(ALPHA2.get(code) as string) ?? code })).sort((a, b) =>
    collator.compare(a.name, b.name),
  )
}
