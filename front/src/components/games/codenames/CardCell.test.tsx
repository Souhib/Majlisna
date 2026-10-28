import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CardCell } from './CardCell'
import type { CodenamesCard } from './model'

function makeCard(overrides: Partial<CodenamesCard> = {}): CodenamesCard {
  return {
    word: 'QURAN',
    word_ar: 'قرآن',
    card_type: 'red',
    revealed: false,
    ...overrides,
  }
}

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    card: makeCard(),
    index: 3,
    isSpymaster: false,
    canGuess: true,
    isFinished: false,
    onGuess: vi.fn(),
    ...overrides,
  }
}

const card = () => screen.getByTestId('codenames-card')

describe('CardCell', () => {
  it('renders the word and its Arabic form', () => {
    render(<CardCell {...defaultProps()} />)
    expect(screen.getByText('QURAN')).toBeInTheDocument()
    expect(screen.getByText('قرآن')).toHaveAttribute('lang', 'ar')
  })

  it('prefers the vocalised Arabic form', () => {
    render(<CardCell {...defaultProps({ card: makeCard({ word_ar_vocalized: 'قُرْآن' }) })} />)
    expect(screen.getByText('قُرْآن')).toBeInTheDocument()
  })

  it('starts its accessible name with the word (the E2E helpers match /^Word\\b/)', () => {
    render(<CardCell {...defaultProps()} />)
    expect(card().getAttribute('aria-label')).toMatch(/^QURAN\b/)
  })

  it('calls onGuess with index when clicked', () => {
    const onGuess = vi.fn()
    render(<CardCell {...defaultProps({ onGuess, index: 7 })} />)
    fireEvent.click(card())
    expect(onGuess).toHaveBeenCalledWith(7)
  })

  it('is disabled when canGuess is false', () => {
    render(<CardCell {...defaultProps({ canGuess: false })} />)
    expect(card()).toBeDisabled()
  })

  it('is disabled when revealed and without a meaning', () => {
    render(<CardCell {...defaultProps({ card: makeCard({ revealed: true }) })} />)
    expect(card()).toBeDisabled()
  })

  it('is disabled when game is finished and the card has no meaning', () => {
    render(<CardCell {...defaultProps({ isFinished: true })} />)
    expect(card()).toBeDisabled()
  })

  it('a revealed card with a meaning opens it instead of voting, and reports the view once', () => {
    const onGuess = vi.fn()
    const onHintViewed = vi.fn()
    render(<CardCell {...defaultProps({ onGuess, onHintViewed, card: makeCard({ revealed: true, hint: 'The Book' }) })} />)
    expect(card()).toBeEnabled()
    expect(card()).toHaveAttribute('data-act', 'meaning')
    fireEvent.click(card())
    expect(onGuess).not.toHaveBeenCalled()
    expect(onHintViewed).toHaveBeenCalledWith('QURAN')
    expect(screen.getByText('The Book')).toBeInTheDocument()
  })

  it('never nests a control inside the card', () => {
    const { container } = render(<CardCell {...defaultProps({ card: makeCard({ revealed: true, hint: 'The Book' }) })} />)
    expect(container.querySelectorAll('button button')).toHaveLength(0)
  })

  it('shows the initials of teammates pointing', () => {
    render(<CardCell {...defaultProps({ voters: [{ id: 'u1', name: 'Maryam' }, { id: 'u2', name: 'Idris Ali' }] })} />)
    expect(screen.getByText('MA')).toBeInTheDocument()
    expect(screen.getByText('IA')).toBeInTheDocument()
    expect(card()).toHaveAttribute('data-pointed', 'true')
  })

  it('shows a count badge when voters are not named', () => {
    render(<CardCell {...defaultProps({ voteCount: 3 })} />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('hides pointing when the card is revealed', () => {
    render(<CardCell {...defaultProps({ voters: [{ id: 'u1', name: 'Maryam' }], card: makeCard({ revealed: true }) })} />)
    expect(screen.queryByText('MA')).not.toBeInTheDocument()
    expect(card()).not.toHaveAttribute('data-pointed')
  })

  it('marks your own choice', () => {
    render(<CardCell {...defaultProps({ isMyVote: true })} />)
    expect(card()).toHaveAttribute('data-mine', 'true')
  })

  it('does not mark your choice once revealed', () => {
    render(<CardCell {...defaultProps({ isMyVote: true, card: makeCard({ revealed: true }) })} />)
    expect(card()).not.toHaveAttribute('data-mine')
  })

  it('a revealed card is dyed in its wool, with its glyph', () => {
    const { container } = render(<CardCell {...defaultProps({ card: makeCard({ card_type: 'blue', revealed: true }) })} />)
    expect(card()).toHaveAttribute('data-face', 'wool')
    expect(card()).toHaveAttribute('data-team', 'indigo')
    expect(container.querySelector('svg.cn-glyph')).toBeInTheDocument()
  })

  it('the spymaster sees the key on unrevealed cards', () => {
    render(<CardCell {...defaultProps({ isSpymaster: true, canGuess: false, card: makeCard({ card_type: 'assassin' }) })} />)
    expect(card()).toHaveAttribute('data-face', 'key')
    expect(card()).toHaveAttribute('data-team', 'assassin')
  })

  it('an operative sees a bare card, without team', () => {
    const { container } = render(<CardCell {...defaultProps({ card: makeCard({ card_type: null }) })} />)
    expect(card()).toHaveAttribute('data-face', 'bare')
    expect(card()).not.toHaveAttribute('data-team')
    expect(container.querySelector('svg.cn-glyph')).not.toBeInTheDocument()
  })

  it('at the end, a card nobody turned reads as the key', () => {
    render(<CardCell {...defaultProps({ isFinished: true, played: false, card: makeCard({ revealed: true }) })} />)
    expect(card()).toHaveAttribute('data-face', 'key')
  })

  it('the Arabic word leads in the Arabic interface', () => {
    render(<CardCell {...defaultProps({ arabicLeads: true })} />)
    expect(card()).toHaveAttribute('data-lead', 'ar')
    expect(card()).toHaveAttribute('dir', 'rtl')
    expect(card().getAttribute('aria-label')).toMatch(/^قرآن، QURAN/)
  })
})
