import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ClueHistory } from './ClueHistory'
import type { ClueHistoryEntry } from './model'

function renderClueHistory(history: ClueHistoryEntry[]) {
  return render(<ClueHistory history={history} />)
}

describe('ClueHistory', () => {
  it('returns null when history is empty', () => {
    const { container } = renderClueHistory([])
    expect(container.innerHTML).toBe('')
  })

  it('renders heading when history is present', () => {
    renderClueHistory([{ team: 'red', clue_word: 'mosque', clue_number: 2, guesses: [] }])
    expect(screen.getByRole('heading', { name: 'game.codenames.clueHistory' })).toBeInTheDocument()
  })

  it('renders entries in reverse order (most recent first)', () => {
    renderClueHistory([
      { team: 'red', clue_word: 'first', clue_number: 1, guesses: [] },
      { team: 'blue', clue_word: 'second', clue_number: 2, guesses: [] },
      { team: 'red', clue_word: 'third', clue_number: 3, guesses: [] },
    ])
    const entries = screen.getAllByTestId('clue-history-entry')
    expect(entries[0]).toHaveTextContent('third')
    expect(entries[1]).toHaveTextContent('second')
    expect(entries[2]).toHaveTextContent('first')
  })

  it('names the team for assistive tech, never by colour alone', () => {
    renderClueHistory([{ team: 'red', clue_word: 'prayer', clue_number: 1, guesses: [] }])
    expect(screen.getByText(/game\.codenames\.teams\.red/)).toHaveClass('sr-only')
  })

  it('shows clue word and number, and ∞ for no limit', () => {
    renderClueHistory([
      { team: 'blue', clue_word: 'charity', clue_number: 4, guesses: [] },
      { team: 'red', clue_word: 'mercy', clue_number: 0, guesses: [] },
    ])
    const [mercy, charity] = screen.getAllByTestId('clue-history-entry')
    expect(charity).toHaveTextContent('charity')
    expect(charity).toHaveTextContent('4')
    expect(mercy).toHaveTextContent('∞')
    expect(mercy).toHaveTextContent('game.codenames.composer.unlimited')
  })

  it('sets an Arabic clue in the hand', () => {
    renderClueHistory([{ team: 'red', clue_word: 'صبر', clue_number: 1, guesses: [] }])
    expect(screen.getByText('صبر')).toHaveClass('font-hand')
  })

  it('marks a correct guess and a miss in words', () => {
    renderClueHistory([
      {
        team: 'red',
        clue_word: 'faith',
        clue_number: 1,
        guesses: [
          { word: 'Quran', card_type: 'red', correct: true },
          { word: 'Sand', card_type: 'neutral', correct: false },
        ],
      },
    ])
    expect(screen.getByText('Quran').closest('li')).toHaveTextContent('game.codenames.correct')
    expect(screen.getByText('Sand').closest('li')).toHaveTextContent('game.codenames.wrong')
    expect(screen.getByText('Sand').closest('li')).toHaveClass('border-dashed')
  })

  it('renders multiple guesses per entry', () => {
    renderClueHistory([
      {
        team: 'blue',
        clue_word: 'worship',
        clue_number: 3,
        guesses: [
          { word: 'Salah', card_type: 'blue', correct: true },
          { word: 'Dua', card_type: 'blue', correct: true },
          { word: 'Fasting', card_type: 'red', correct: false },
        ],
      },
    ])
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('Dua')).toBeInTheDocument()
    expect(screen.getByText('Fasting')).toBeInTheDocument()
  })
})
