import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EliminationOverlay } from './EliminationOverlay'

describe('EliminationOverlay (the verdict for a player who missed it)', () => {
  const defaultProps = {
    round: 2,
    eliminatedUsername: 'Alice',
    eliminatedRole: 'civilian',
    eliminatedUserId: 'u1',
    votes: [{ voter: 'Bob', voter_id: 'u2', target: 'Alice', target_id: 'u1' }],
    currentUserId: 'u3',
    onDismiss: vi.fn(),
  }

  it('carries the elimination-overlay test id', () => {
    render(<EliminationOverlay {...defaultProps} />)
    expect(screen.getByTestId('elimination-overlay')).toBeInTheDocument()
  })

  it('names who the table chose', () => {
    render(<EliminationOverlay {...defaultProps} />)
    expect(screen.getByRole('heading', { name: 'game.undercover.verdict.chose' })).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it.each([
    ['civilian', 'games.undercover.roles.civilian'],
    ['undercover', 'games.undercover.roles.undercover'],
    ['mr_white', 'games.undercover.roles.mrWhite'],
  ])('turns the tablet over to show the role: %s', (role, label) => {
    render(<EliminationOverlay {...defaultProps} eliminatedRole={role} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('says who voted for whom', () => {
    render(<EliminationOverlay {...defaultProps} />)
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('game.undercover.verdict.votedFor')).toBeInTheDocument()
  })

  it('"Continue" dismisses it', () => {
    const onDismiss = vi.fn()
    render(<EliminationOverlay {...defaultProps} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.undercover.continueGame' }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('without a name, only says the votes are in', () => {
    render(<EliminationOverlay {...defaultProps} eliminatedUsername={undefined} />)
    expect(screen.getByRole('heading', { name: 'game.undercover.verdict.noOne' })).toBeInTheDocument()
  })
})
