import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { UndercoverPlayerList } from './UndercoverPlayerList'

const players = [
  { id: 'u1', username: 'Maryam', is_alive: true, is_mayor: true },
  { id: 'u2', username: 'Bilal', is_alive: false },
  { id: 'u3', username: 'Idris', is_alive: true },
]

describe('UndercoverPlayerList (the table)', () => {
  it('counts who is still seated', () => {
    render(<UndercoverPlayerList players={players} />)
    expect(screen.getByText('2/3')).toBeInTheDocument()
  })

  it('names an emptied seat "Eliminated" with the role its tablet showed', () => {
    render(<UndercoverPlayerList players={players} eliminated={[{ user_id: 'u2', role: 'undercover' }]} />)
    expect(screen.getByText(/game\.eliminated · games\.undercover\.roles\.undercover/)).toBeInTheDocument()
  })

  it('marks the Mayor', () => {
    render(<UndercoverPlayerList players={players} />)
    expect(screen.getByText('game.undercover.mayorLabel')).toBeInTheDocument()
  })

  it('during the vote, marks who has voted (and only the living)', () => {
    render(<UndercoverPlayerList players={players} voted={['u1']} />)
    expect(screen.getAllByText('game.undercover.hasVoted')).toHaveLength(1)
    expect(screen.getAllByText('game.undercover.notVotedYet')).toHaveLength(1)
  })

  it('outside the vote, says nothing about votes', () => {
    render(<UndercoverPlayerList players={players} />)
    expect(screen.queryByText('game.undercover.hasVoted')).not.toBeInTheDocument()
  })
})
