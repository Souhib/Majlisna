import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RoleRevealPhase } from './RoleRevealPhase'

describe('RoleRevealPhase (the first reading)', () => {
  it('shows the same heading for every role: nobody is told their side', () => {
    render(<RoleRevealPhase onDismiss={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'game.undercover.firstReading.title' })).toBeInTheDocument()
  })

  it('shows how each role appears once a seat empties', () => {
    render(<RoleRevealPhase onDismiss={vi.fn()} />)
    expect(screen.getByText('games.undercover.roles.civilian')).toBeInTheDocument()
    expect(screen.getByText('games.undercover.roles.undercover')).toBeInTheDocument()
    expect(screen.getByText('games.undercover.roles.mrWhite')).toBeInTheDocument()
  })

  it('calls onDismiss when "I understand" is clicked', () => {
    const onDismiss = vi.fn()
    render(<RoleRevealPhase onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.undercover.iUnderstand' }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
