import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HintDisplay } from './HintDisplay'

const hints = ['A place of worship', 'Has a dome', 'Muslims pray here', 'Contains a mihrab']

const rungs = () => screen.getAllByRole('listitem')

describe('HintDisplay (the ladder)', () => {
  it('draws one rung per hint of the full ladder, not of the prefix it holds', () => {
    render(<HintDisplay hints={hints.slice(0, 2)} hintsRevealed={2} maxHints={6} />)
    expect(rungs()).toHaveLength(6)
  })

  it('numbers each rung with what a right answer is worth while it is the newest: 6 down to 1', () => {
    const { container } = render(<HintDisplay hints={hints} hintsRevealed={2} maxHints={6} />)
    const worths = Array.from(container.querySelectorAll('.rung-worth > span')).map((n) => n.textContent)
    expect(worths).toEqual(['6', '5', '4', '3', '2', '1'])
  })

  it('marks passed rungs, the rung in play, and the hidden ones', () => {
    render(<HintDisplay hints={hints} hintsRevealed={3} maxHints={6} />)
    expect(rungs().map((r) => r.getAttribute('data-state'))).toEqual(['past', 'past', 'now', 'hidden', 'hidden', 'hidden'])
    expect(rungs()[2]).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('game.quiz.kalimat.now')).toBeInTheDocument()
  })

  it('only shows the hints up to hintsRevealed', () => {
    render(<HintDisplay hints={hints} hintsRevealed={2} maxHints={6} />)
    expect(screen.getByText('A place of worship')).toBeInTheDocument()
    expect(screen.getByText('Has a dome')).toBeInTheDocument()
    expect(screen.queryByText('Muslims pray here')).not.toBeInTheDocument()
  })

  // The server ships only the hints it has released: a clock running ahead of the
  // fetch must never claim a rung whose text it does not hold.
  it('never reveals more rungs than the hints it holds', () => {
    render(<HintDisplay hints={hints.slice(0, 2)} hintsRevealed={4} maxHints={6} />)
    expect(rungs().filter((r) => r.getAttribute('data-state') !== 'hidden')).toHaveLength(2)
    expect(screen.queryByText('Muslims pray here')).not.toBeInTheDocument()
  })

  it('tells when the next hint arrives, on the next rung only', () => {
    render(<HintDisplay hints={hints} hintsRevealed={2} maxHints={6} nextHintIn={6} />)
    expect(rungs()[2]).toHaveTextContent('game.quiz.kalimat.nextIn')
    expect(rungs()[2]).toHaveTextContent('0:06')
    expect(rungs()[3]).not.toHaveTextContent('0:06')
  })

  it('says nothing about a next hint when none will come', () => {
    render(<HintDisplay hints={hints} hintsRevealed={2} maxHints={6} nextHintIn={null} />)
    expect(screen.queryByText('game.quiz.kalimat.nextIn')).not.toBeInTheDocument()
  })

  it('names every rung by its place on the ladder, with no hidden "#n" test hook', () => {
    render(<HintDisplay hints={hints} hintsRevealed={2} maxHints={6} />)
    for (const rung of rungs()) expect(rung).toHaveTextContent('game.quiz.kalimat.rungLabel')
    expect(screen.queryByText('#1')).not.toBeInTheDocument()
    expect(screen.queryByText('#2')).not.toBeInTheDocument()
  })
})
