import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { McqRoundResults } from './McqRoundResults'

const roundResults = [
  { user_id: 'u1', username: 'Alice', chose_correct: true, points: 3 },
  { user_id: 'u2', username: 'Bob', chose_correct: false, points: 0 },
]

const explanation = 'The Shahada is the first pillar of Islam.'

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    explanation,
    roundResults,
    isHost: false,
    onNextRound: vi.fn(),
    isAdvancing: false,
    ...overrides,
  }
}

describe('McqRoundResults', () => {
  it('renders the explanation, keeping its text verbatim', () => {
    const { container } = render(<McqRoundResults {...defaultProps()} />)
    expect(container.querySelector('.quiz-why')?.textContent).toBe(explanation)
    expect(screen.getByText('game.mcqQuiz.explanation')).toBeInTheDocument()
  })

  it('sets the right answer in bold where the explanation names it', () => {
    const { container } = render(<McqRoundResults {...defaultProps({ correctChoice: 'the Shahada' })} />)
    expect(container.querySelector('.quiz-why b')?.textContent).toBe('The Shahada')
    expect(container.querySelector('.quiz-why')?.textContent).toBe(explanation)
  })

  it('does not render explanation when null', () => {
    render(<McqRoundResults {...defaultProps({ explanation: null })} />)
    expect(screen.queryByText('game.mcqQuiz.explanation')).not.toBeInTheDocument()
  })

  it('renders every player with how they did', () => {
    render(<McqRoundResults {...defaultProps()} />)
    const rows = screen.getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('Alice')
    expect(rows[0]).toHaveTextContent('game.quiz.mcq.right')
    expect(rows[0]).toHaveTextContent('+3')
    expect(rows[1]).toHaveTextContent('Bob')
    expect(rows[1]).toHaveTextContent('game.quiz.mcq.missed')
  })

  it('gives the host the next-question button', () => {
    render(<McqRoundResults {...defaultProps({ isHost: true })} />)
    expect(screen.getByRole('button', { name: 'game.mcqQuiz.nextRound' })).toBeInTheDocument()
  })

  it('offers a non-host the ready button instead of next round', () => {
    const onNextRound = vi.fn()
    render(<McqRoundResults {...defaultProps({ isHost: false, onNextRound })} />)
    expect(screen.queryByText('game.mcqQuiz.nextRound')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'game.readyUp' }))
    expect(onNextRound).toHaveBeenCalledOnce()
  })

  it('disables the ready button once the player is ready', () => {
    render(<McqRoundResults {...defaultProps({ isHost: false, isReady: true, readyCount: 2 })} />)
    expect(screen.getByRole('button', { name: 'game.readyWaiting' })).toBeDisabled()
  })

  it('calls onNextRound when clicked', () => {
    const onNextRound = vi.fn()
    render(<McqRoundResults {...defaultProps({ isHost: true, onNextRound })} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.mcqQuiz.nextRound' }))
    expect(onNextRound).toHaveBeenCalledOnce()
  })

  it('shows the next-question button as busy while advancing', () => {
    render(<McqRoundResults {...defaultProps({ isHost: true, isAdvancing: true })} />)
    expect(screen.getByRole('button', { name: /game.mcqQuiz.nextRound/ })).toHaveAttribute('aria-busy', 'true')
  })

  it('names the letter each player chose, and who did not answer', () => {
    // Prepare
    const results = [
      { user_id: 'u1', username: 'Alice', chose_correct: true, points: 3, choice_index: 2 },
      { user_id: 'u2', username: 'Bob', chose_correct: false, points: 0, choice_index: 1 },
      { user_id: 'u3', username: 'Cara', chose_correct: false, points: 0, choice_index: null },
    ]

    // Act
    render(<McqRoundResults {...defaultProps({ roundResults: results, choices: ['w', 'x', 'y', 'z'] })} />)
    const rows = screen.getAllByRole('listitem')

    // Assert
    expect(rows[0]).toHaveTextContent('C · game.quiz.mcq.right')
    expect(rows[1]).toHaveTextContent('B · game.quiz.mcq.missed')
    expect(rows[2]).toHaveTextContent('game.quiz.mcq.noAnswer')
  })
})

