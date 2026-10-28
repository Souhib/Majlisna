import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RoundAdvanceButton } from '../RoundAdvanceButton'

function props(overrides: Record<string, unknown> = {}) {
  return {
    isHost: false,
    isReady: false,
    readyCount: 0,
    isAdvancing: false,
    advanceLabel: 'Next round',
    onAdvance: vi.fn(),
    ...overrides,
  }
}

describe('RoundAdvanceButton', () => {
  it('lets the host advance, and tells them where the table stands', () => {
    const onAdvance = vi.fn()
    render(<RoundAdvanceButton {...props({ isHost: true, onAdvance, readyCount: 1, readyTotal: 3 })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next round' }))
    expect(onAdvance).toHaveBeenCalledOnce()
    expect(screen.getByText('game.quiz.hostNote')).toBeInTheDocument()
  })

  it('asks a player to mark themselves ready, and says how the round moves on', () => {
    const onAdvance = vi.fn()
    render(<RoundAdvanceButton {...props({ onAdvance })} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.readyUp' }))
    expect(onAdvance).toHaveBeenCalledOnce()
    expect(screen.getByText('game.quiz.notReadyNote')).toBeInTheDocument()
  })

  it('once ready, disables the button and says why', () => {
    render(<RoundAdvanceButton {...props({ isReady: true, readyCount: 2, readyTotal: 3 })} />)
    expect(screen.getByRole('button', { name: 'game.readyWaiting' })).toBeDisabled()
    expect(screen.getByText('game.quiz.readyOf')).toBeInTheDocument()
    expect(screen.getByText(/game.quiz.readyNote/)).toBeInTheDocument()
  })

  it('falls back to the plain ready count without a total', () => {
    render(<RoundAdvanceButton {...props({ isReady: true, readyCount: 2 })} />)
    expect(screen.getByText('game.readyCount')).toBeInTheDocument()
  })

  it('is busy, not clickable twice, while advancing', () => {
    const onAdvance = vi.fn()
    render(<RoundAdvanceButton {...props({ isHost: true, isAdvancing: true, onAdvance })} />)
    const button = screen.getByRole('button', { name: /Next round/ })
    expect(button).toHaveAttribute('aria-busy', 'true')
    fireEvent.click(button)
    expect(onAdvance).not.toHaveBeenCalled()
  })

  it('gives a spectator no button, only where the table stands', () => {
    render(<RoundAdvanceButton {...props({ isSpectator: true, readyCount: 1, readyTotal: 2 })} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText(/game.quiz.spectatorWaits/)).toBeInTheDocument()
  })
})
