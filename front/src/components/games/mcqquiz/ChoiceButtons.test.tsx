import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChoiceButtons } from './ChoiceButtons'

const choices = ['Makkah', 'Madinah', 'Jerusalem', 'Damascus']

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    choices,
    onSelect: vi.fn(),
    disabled: false,
    selectedIndex: null,
    correctIndex: null,
    roundPhase: 'playing',
    ...overrides,
  }
}

describe('ChoiceButtons', () => {
  it('renders the four choices as radio buttons in a group', () => {
    render(<ChoiceButtons {...defaultProps()} />)
    expect(screen.getByRole('radiogroup')).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(4)
    expect(screen.getByText('Makkah')).toBeInTheDocument()
    expect(screen.getByText('Damascus')).toBeInTheDocument()
  })

  it('letters them A, B, C, D in a Latin interface', () => {
    render(<ChoiceButtons {...defaultProps()} />)
    expect(screen.getByLabelText('A: Makkah')).toBeInTheDocument()
    expect(screen.getByLabelText('B: Madinah')).toBeInTheDocument()
    expect(screen.getByLabelText('C: Jerusalem')).toBeInTheDocument()
    expect(screen.getByLabelText('D: Damascus')).toBeInTheDocument()
  })

  it('calls onSelect with index when choice is clicked', () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect })} />)
    fireEvent.click(screen.getByLabelText('B: Madinah'))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('does not call onSelect when disabled', () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect, disabled: true })} />)
    fireEvent.click(screen.getByLabelText('A: Makkah'))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('marks the chosen one with aria-checked and the chosen state', () => {
    render(<ChoiceButtons {...defaultProps({ selectedIndex: 2 })} />)
    expect(screen.getByLabelText('C: Jerusalem')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText('C: Jerusalem')).toHaveAttribute('data-state', 'chosen')
    expect(screen.getByLabelText('A: Makkah')).toHaveAttribute('aria-checked', 'false')
  })

  it('is one tab stop, and the arrow keys move between the choices and choose', () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect, selectedIndex: 1 })} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.getAttribute('tabindex'))).toEqual(['-1', '0', '-1', '-1'])
    radios[1].focus()
    fireEvent.keyDown(radios[1], { key: 'ArrowDown' })
    expect(onSelect).toHaveBeenLastCalledWith(2)
    expect(document.activeElement).toBe(radios[2])
    fireEvent.keyDown(radios[2], { key: 'ArrowUp' })
    expect(onSelect).toHaveBeenLastCalledWith(1)
    fireEvent.keyDown(radios[1], { key: 'End' })
    expect(onSelect).toHaveBeenLastCalledWith(3)
    fireEvent.keyDown(radios[3], { key: 'ArrowRight' })
    expect(onSelect).toHaveBeenLastCalledWith(0)
  })

  it('after the reveal: a list, the right one in brass, a wrong pick struck on its letter', () => {
    const { container } = render(
      <ChoiceButtons {...defaultProps({ roundPhase: 'results', correctIndex: 0, selectedIndex: 1 })} />,
    )
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    const items = container.querySelectorAll('li.quiz-choice')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveAttribute('data-state', 'right')
    expect(items[1]).toHaveAttribute('data-state', 'wrong')
    expect(items[2]).not.toHaveAttribute('data-state')
    // the choice's words carry no strike: only the letter does (CSS ::after on .choice-letter)
    expect(items[1].querySelector('.choice-text')).toHaveTextContent('Madinah')
    expect(items[0]).toHaveTextContent('game.quiz.mcq.rightAnswer')
    expect(items[1]).toHaveTextContent('game.quiz.mcq.yourWrongAnswer')
  })

  it('prints the tags at the end of each choice', () => {
    render(<ChoiceButtons {...defaultProps({ roundPhase: 'results', correctIndex: 2, tags: [null, 'you', '3 players', null] })} />)
    expect(screen.getByText('you')).toBeInTheDocument()
    expect(screen.getByText('3 players')).toBeInTheDocument()
  })
})
