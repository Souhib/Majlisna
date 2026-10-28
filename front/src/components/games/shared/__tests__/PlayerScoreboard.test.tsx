import { render, screen, within } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { PlayerScoreboard } from '../PlayerScoreboard'

const players = [
  { user_id: 'u1', username: 'Alice', total_score: 10, current_round_answered: true, current_round_points: 3 },
  { user_id: 'u2', username: 'Bob', total_score: 20, current_round_answered: false, current_round_points: 0 },
  { user_id: 'u3', username: 'Charlie', total_score: 15, current_round_answered: true, current_round_points: 5 },
]

const rows = () => within(screen.getByTestId('quiz-scoreboard')).getAllByRole('listitem')

describe('PlayerScoreboard', () => {
  it('renders the scores heading', () => {
    render(<PlayerScoreboard players={players} />)
    expect(screen.getByRole('heading', { name: 'game.quiz.scores' })).toBeInTheDocument()
  })

  it('lists players by total score, descending, with their scores', () => {
    render(<PlayerScoreboard players={players} />)
    expect(rows().map((r) => r.textContent)).toEqual(['1Bob20', '2Charlie15', '3Alice10'])
  })

  it('lets a tie share its place', () => {
    render(<PlayerScoreboard players={[...players, { ...players[0], user_id: 'u4', username: 'Dina', total_score: 15 }]} />)
    expect(rows().map((r) => r.firstElementChild?.textContent)).toEqual(['1', '2', '2', '4'])
  })

  it('marks your own row', () => {
    render(<PlayerScoreboard players={players} currentUserId="u2" />)
    expect(rows()[0]).toHaveAttribute('data-you', 'true')
    expect(rows()[0]).toHaveTextContent('game.quiz.you')
    expect(rows()[1]).not.toHaveAttribute('data-you')
  })

  it('says who has answered this round, in words, only when asked to', () => {
    const { rerender } = render(<PlayerScoreboard players={players} />)
    expect(screen.queryByRole('img', { name: 'game.quiz.hasAnswered' })).not.toBeInTheDocument()
    rerender(<PlayerScoreboard players={players} showAnswered />)
    expect(screen.getAllByRole('img', { name: 'game.quiz.hasAnswered' })).toHaveLength(2)
    expect(screen.getAllByRole('img', { name: 'game.quiz.stillThinking' })).toHaveLength(1)
    expect(screen.getByText('game.quiz.answeredCount')).toBeInTheDocument()
  })

  it('shows the totals the server sends, without taking this round’s points off again', () => {
    // The Quiz's server already holds a round's points back while its question is open;
    // the scoreboard must not subtract `current_round_points` a second time.
    render(<PlayerScoreboard players={players} />)
    expect(rows().map((r) => r.textContent)).toEqual(['1Bob20', '2Charlie15', '3Alice10'])
  })

  it('renders with empty players array', () => {
    render(<PlayerScoreboard players={[]} />)
    expect(screen.getByRole('heading', { name: 'game.quiz.scores' })).toBeInTheDocument()
  })
})
