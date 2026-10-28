import { describe, expect, it } from 'vitest'
import {
  arabicForm,
  cardFace,
  cardGlyph,
  endReason,
  fitLatin,
  latinEm,
  guessStatus,
  isArabicScript,
  longestSegment,
  otherTeam,
  playedWords,
  spymasterOf,
  teamWool,
  votersByCard,
  type ClueHistoryEntry,
} from './model'

const history: ClueHistoryEntry[] = [
  {
    team: 'red',
    clue_word: 'faith',
    clue_number: 2,
    guesses: [
      { word: 'Salah', card_type: 'red', correct: true },
      { word: 'Sand', card_type: 'neutral', correct: false },
    ],
  },
  {
    team: 'blue',
    clue_word: 'place',
    clue_number: 1,
    guesses: [{ word: 'Makkah', card_type: 'assassin', correct: false }],
  },
]

describe('codenames model', () => {
  it('maps server teams to wool and back', () => {
    expect(teamWool('red')).toBe('madder')
    expect(teamWool('blue')).toBe('indigo')
    expect(otherTeam('red')).toBe('blue')
    expect(otherTeam('blue')).toBe('red')
  })

  it('maps card types to glyphs, hidden cards to none', () => {
    expect(cardGlyph('red')).toBe('madder')
    expect(cardGlyph('blue')).toBe('indigo')
    expect(cardGlyph('neutral')).toBe('bystander')
    expect(cardGlyph('assassin')).toBe('assassin')
    expect(cardGlyph(null)).toBeNull()
  })

  it('prefers the vocalised Arabic form', () => {
    expect(arabicForm({ word_ar: 'صبر', word_ar_vocalized: 'صَبْر' })).toBe('صَبْر')
    expect(arabicForm({ word_ar: 'صبر', word_ar_vocalized: null })).toBe('صبر')
    expect(arabicForm({ word_ar: '  ', word_ar_vocalized: undefined })).toBeNull()
  })

  it('detects Arabic script', () => {
    expect(isArabicScript('صبر')).toBe(true)
    expect(isArabicScript('Sabr')).toBe(false)
  })

  it('measures the longest unbreakable run', () => {
    expect(longestSegment('Alhamdulillah')).toBe(13)
    expect(longestSegment('Umar ibn Abdul Aziz')).toBe(5)
    expect(longestSegment('Dhul-Kifl')).toBe(4)
    expect(longestSegment('صَبْر')).toBe(3)
  })

  it('estimates a Latin width from Readex glyph widths', () => {
    expect(latinEm('ill')).toBeCloseTo(0.89)
    expect(latinEm('mmm')).toBeCloseTo(2.85)
  })

  it('gives very long Latin words one soft hyphen at a natural break', () => {
    expect(fitLatin('SubhanAllah').text).toBe('Subhan\u00ADAllah')
    expect(fitLatin('Hudaybiyyah').text).toBe('Huday\u00ADbiyyah')
    expect(fitLatin('Alhamdulillah').text).toBe('Alham\u00ADdulillah')
    // sized for the longer of the two lines, hyphen included
    expect(fitLatin('SubhanAllah').em).toBeCloseTo(latinEm('Subhan-'))
    // short words and multi-word names are left whole
    expect(fitLatin('Muhammad')).toEqual({ text: 'Muhammad', em: latinEm('Muhammad') })
    expect(fitLatin('Umar ibn Abdul Aziz')).toEqual({ text: 'Umar ibn Abdul Aziz', em: latinEm('Abdul') })
    // an existing hyphen is already a break
    expect(fitLatin('Dhul-Kifl').em).toBeCloseTo(latinEm('Dhul-'))
    // digraphs are never split
    expect(fitLatin('Tashahhudun').text).not.toContain('s\u00ADh')
  })

  it('chooses the face a card shows', () => {
    const hidden = { revealed: false, card_type: null }
    const keyed = { revealed: false, card_type: 'red' as const }
    const turned = { revealed: true, card_type: 'blue' as const }
    expect(cardFace(hidden, { isSpymaster: false, isFinished: false })).toBe('bare')
    expect(cardFace(keyed, { isSpymaster: true, isFinished: false })).toBe('key')
    expect(cardFace(turned, { isSpymaster: false, isFinished: false })).toBe('wool')
    // at the end every card comes back revealed: the unturned ones read as the key
    expect(cardFace(turned, { isSpymaster: false, isFinished: true, played: false })).toBe('key')
    expect(cardFace(turned, { isSpymaster: false, isFinished: true, played: true })).toBe('wool')
    expect(cardFace(turned, { isSpymaster: false, isFinished: true })).toBe('wool')
  })

  it('lists the words turned during play, in order, once', () => {
    expect(playedWords(history)).toEqual(['Salah', 'Sand', 'Makkah'])
    expect(playedWords(undefined)).toEqual([])
  })

  it('counts guesses: N + 1 with the bonus, 0 means no limit', () => {
    expect(guessStatus({ clue_number: 2, guesses_made: 0 })).toEqual({ made: 0, left: 2, bonus: true, unlimited: false })
    expect(guessStatus({ clue_number: 2, guesses_made: 2 })).toEqual({ made: 2, left: 0, bonus: true, unlimited: false })
    expect(guessStatus({ clue_number: 0, guesses_made: 3 })).toEqual({ made: 3, left: 0, bonus: false, unlimited: true })
  })

  it('tells how a game was decided', () => {
    expect(endReason('red', { red: 0, blue: 3 }, history)).toBe('all-found')
    expect(endReason('red', { red: 2, blue: 3 }, history)).toBe('assassin')
    expect(endReason('blue', { red: 2, blue: 3 }, history)).toBe('forfeit')
  })

  it('groups votes by card', () => {
    const map = votersByCard({ u1: 3, u2: 3, u3: 7 })
    expect(map.get(3)).toEqual(['u1', 'u2'])
    expect(map.get(7)).toEqual(['u3'])
    expect(votersByCard(undefined).size).toBe(0)
  })

  it('finds a team spymaster', () => {
    const players = [
      { user_id: 'a', username: 'A', team: 'red', role: 'operative' },
      { user_id: 'b', username: 'B', team: 'red', role: 'spymaster' },
    ]
    expect(spymasterOf(players, 'red')?.username).toBe('B')
    expect(spymasterOf(players, 'blue')).toBeUndefined()
  })
})
