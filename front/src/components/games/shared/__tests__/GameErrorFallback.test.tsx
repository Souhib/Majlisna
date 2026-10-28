import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GameErrorFallback } from '../GameErrorFallback'

const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

describe('GameErrorFallback', () => {
  it('renders the error heading and says what to do', () => {
    render(<GameErrorFallback />)
    expect(screen.getByRole('heading', { name: 'common.error' })).toBeInTheDocument()
    expect(screen.getByText('game.quiz.errorBody')).toBeInTheDocument()
  })

  it('renders the error message in an alert when there is one', () => {
    render(<GameErrorFallback error={new Error('Something went wrong')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
  })

  it('does not render an error alert when there is no error', () => {
    render(<GameErrorFallback />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('renders retry button when onReset is provided', () => {
    render(<GameErrorFallback onReset={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'common.retry' })).toBeInTheDocument()
  })

  it('does not render retry button when onReset is not provided', () => {
    render(<GameErrorFallback />)
    expect(screen.queryByText('common.retry')).not.toBeInTheDocument()
  })

  it('calls onReset when retry button is clicked', () => {
    const onReset = vi.fn()
    render(<GameErrorFallback onReset={onReset} />)
    fireEvent.click(screen.getByText('common.retry'))
    expect(onReset).toHaveBeenCalledOnce()
  })

  it('navigates to /rooms when back button is clicked', () => {
    render(<GameErrorFallback />)
    fireEvent.click(screen.getByRole('button', { name: 'game.backToRoom' }))
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/rooms' })
  })
})
