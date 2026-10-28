import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HOLD_MS, Lawh, TurnedLawh, isArabicScript, wordFit } from './Lawh'

const word = { arabic: 'حِلْم', latin: 'Hilm' }

function tablet() {
  return screen.getByRole('button', { name: /game\.undercover\.lawh\.label/ })
}

describe('Lawh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps the word out of the DOM at rest', () => {
    render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
    expect(screen.queryByText('Hilm')).not.toBeInTheDocument()
    expect(screen.getByText('game.undercover.lawh.hold')).toBeInTheDocument()
    expect(screen.getByText('game.undercover.lawh.notRead')).toBeInTheDocument()
  })

  it('shows the word while held, after the hold threshold, and counts the read', () => {
    const onRead = vi.fn()
    render(<Lawh round={2} word={word} reads={0} onRead={onRead} />)
    fireEvent.pointerDown(tablet(), { pointerType: 'touch', pointerId: 1 })
    // not yet: the ring is still filling
    act(() => {
      vi.advanceTimersByTime(HOLD_MS / 3)
    })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2)
    })
    expect(within(tablet()).getByText('حِلْم')).toBeInTheDocument()
    expect(screen.getByText('Hilm')).toBeInTheDocument()
    expect(onRead).toHaveBeenCalledOnce()

    fireEvent.pointerUp(tablet(), { pointerType: 'touch', pointerId: 1 })
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
  })

  it('a press shorter than the threshold reveals nothing', () => {
    const onRead = vi.fn()
    render(<Lawh round={1} word={word} reads={0} onRead={onRead} />)
    fireEvent.pointerDown(tablet(), { pointerType: 'touch', pointerId: 1 })
    act(() => {
      vi.advanceTimersByTime(HOLD_MS / 4)
    })
    fireEvent.pointerUp(tablet(), { pointerType: 'touch', pointerId: 1 })
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 3)
    })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
    expect(onRead).not.toHaveBeenCalled()
  })

  it('holds with the keyboard (Space down, Space up)', () => {
    render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    fireEvent.keyDown(tablet(), { key: ' ' })
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2)
    })
    expect(within(tablet()).getByText('حِلْم')).toBeInTheDocument()
    fireEvent.keyUp(tablet(), { key: ' ' })
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
  })

  it('"show until I hide it" pins the word open, and hides it again', () => {
    render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    fireEvent.click(screen.getByText('game.undercover.lawh.cantHold'))
    expect(within(tablet()).getByText('حِلْم')).toBeInTheDocument()
    expect(screen.getByText('game.undercover.lawh.pinnedAct')).toBeInTheDocument()
    fireEvent.click(screen.getByText('game.undercover.lawh.hideAgain'))
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
  })

  it('an assistive-tech click (no pointer: detail 0) toggles the word', () => {
    render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    fireEvent.click(tablet(), { detail: 0 })
    expect(within(tablet()).getByText('حِلْم')).toBeInTheDocument()
  })

  it('a mouse click (detail 1) does not pin the word', () => {
    render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    fireEvent.click(tablet(), { detail: 1 })
    expect(within(tablet()).queryByText('حِلْم')).not.toBeInTheDocument()
  })

  it('Mr. White reads a dashed page: no word', () => {
    render(<Lawh round={1} word={null} reads={0} onRead={vi.fn()} />)
    fireEvent.click(screen.getByText('game.undercover.lawh.cantHold'))
    expect(screen.getByText('game.undercover.lawh.noWord')).toBeInTheDocument()
    expect(screen.getByText('game.undercover.lawh.noWordNote')).toBeInTheDocument()
  })

  it('offers the meaning on every tablet, and records a view only for a real meaning', () => {
    const onMeaningOpen = vi.fn()
    const { rerender } = render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} hint={null} onMeaningOpen={onMeaningOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.hintButton' }))
    expect(onMeaningOpen).not.toHaveBeenCalled()
    rerender(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} hint="Forbearance" onMeaningOpen={onMeaningOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.hintButton' }))
    fireEvent.click(screen.getByRole('button', { name: 'game.hintButton' }))
    expect(onMeaningOpen).toHaveBeenCalled()
  })

  it('Mr. White has the same controls as everyone (nothing on screen gives him away)', () => {
    const onMeaningOpen = vi.fn()
    render(<Lawh round={1} word={null} reads={0} onRead={vi.fn()} onMeaningOpen={onMeaningOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.hintButton' }))
    expect(onMeaningOpen).not.toHaveBeenCalled()
  })

  it('writes the meaning under the word once it has been asked for', () => {
    render(<Lawh round={1} word={word} reads={1} onRead={vi.fn()} hint="Forbearance" meaningShown />)
    fireEvent.click(screen.getByText('game.undercover.lawh.cantHold'))
    expect(screen.getAllByText('Forbearance').length).toBeGreaterThan(0)
  })

  it('falls back to the Latin word when there is no Arabic form', () => {
    render(<Lawh round={1} word={{ arabic: null, latin: 'Hajj' }} reads={0} onRead={vi.fn()} />)
    fireEvent.click(screen.getByText('game.undercover.lawh.cantHold'))
    expect(within(tablet()).getByText('Hajj')).toBeInTheDocument()
  })

  it('speaks the word from a live region outside the button (a button hides its content)', () => {
    const { container } = render(<Lawh round={1} word={word} reads={0} onRead={vi.fn()} />)
    const live = container.querySelector('p[aria-live="polite"]')
    expect(live).not.toBeNull()
    expect(tablet().contains(live)).toBe(false)
    expect(live).toBeEmptyDOMElement()
    fireEvent.click(screen.getByText('game.undercover.lawh.cantHold'))
    expect(live).toHaveTextContent('حِلْم, Hilm')
    expect(live?.querySelector('[lang="ar"]')).toHaveTextContent('حِلْم')
  })
})

describe('TurnedLawh', () => {
  it('shows the role band and what the seat held, never another player\'s word', () => {
    render(<TurnedLawh name="Bilal" round={2} role="undercover" />)
    expect(screen.getByText('Bilal')).toBeInTheDocument()
    expect(screen.getByText('games.undercover.roles.undercover')).toBeInTheDocument()
    expect(screen.getByText('game.undercover.lawh.heldUndercover')).toBeInTheDocument()
  })

  it('shows your own word on your own tablet', () => {
    render(<TurnedLawh name="You" round={2} role="civilian" word={word} />)
    expect(screen.getByText('حِلْم')).toBeInTheDocument()
  })

  it('Mr. White\'s tablet says he had no word', () => {
    render(<TurnedLawh name="Idris" round={3} role="mr_white" />)
    expect(screen.getByText('game.undercover.lawh.heldNone')).toBeInTheDocument()
    expect(screen.getByText('games.undercover.roles.mrWhite')).toBeInTheDocument()
  })
})

describe('word helpers', () => {
  it('detects Arabic script', () => {
    expect(isArabicScript('صبر')).toBe(true)
    expect(isArabicScript('patience')).toBe(false)
  })

  it('shrinks long words, ignoring the harakat', () => {
    expect(wordFit('حِلْم')).toBe(1)
    expect(wordFit('خَالِدُ بْنُ الْوَلِيد')).toBeLessThan(1)
  })
})
