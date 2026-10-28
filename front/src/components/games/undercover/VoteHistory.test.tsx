import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { VoteHistory } from './VoteHistory'

describe('VoteHistory', () => {
  const sampleHistory = [
    {
      round: 1,
      votes: [
        { voter: 'Alice', voter_id: 'u1', target: 'Bob', target_id: 'u2' },
        { voter: 'Charlie', voter_id: 'u3', target: 'Bob', target_id: 'u2' },
      ],
      eliminated: { username: 'Bob', role: 'undercover', user_id: 'u2' },
    },
    {
      round: 2,
      votes: [{ voter: 'Alice', voter_id: 'u1', target: 'Charlie', target_id: 'u3' }],
      eliminated: { username: 'Charlie', role: 'civilian', user_id: 'u3' },
    },
  ]

  const roundButton = (n: number) => screen.getAllByRole('button')[n]

  it('renders nothing without history', () => {
    const { container } = render(<VoteHistory history={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('lists every round with the seat that emptied and its role', () => {
    render(<VoteHistory history={sampleHistory} />)
    expect(screen.getAllByText('game.undercover.round')).toHaveLength(2)
    expect(roundButton(0)).toHaveTextContent('Bob')
    expect(roundButton(0)).toHaveTextContent('games.undercover.roles.undercover')
    expect(roundButton(1)).toHaveTextContent('games.undercover.roles.civilian')
  })

  it('opens the latest round only', () => {
    render(<VoteHistory history={sampleHistory} />)
    expect(roundButton(0)).toHaveAttribute('aria-expanded', 'false')
    expect(roundButton(1)).toHaveAttribute('aria-expanded', 'true')
  })

  it('toggles a round open and closed', () => {
    render(<VoteHistory history={sampleHistory} />)
    fireEvent.click(roundButton(0))
    expect(roundButton(0)).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Alice and Charlie')).toBeVisible()
    fireEvent.click(roundButton(0))
    expect(roundButton(0)).toHaveAttribute('aria-expanded', 'false')
  })

  it('at the end, shows every round open without toggles', () => {
    render(<VoteHistory history={sampleHistory} expandAll />)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.getByText('Alice and Charlie')).toBeVisible()
  })

  it('says when a round emptied no seat', () => {
    render(<VoteHistory history={[{ round: 1, votes: [], eliminated: null }]} />)
    expect(screen.getByText('game.undercover.noElimination')).toBeInTheDocument()
  })
})
