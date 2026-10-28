import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { VotingPhase } from './VotingPhase'

describe('VotingPhase', () => {
  const defaultProps = {
    players: [
      { id: 'u1', username: 'Alice', is_alive: true, is_mayor: false },
      { id: 'u2', username: 'Bob', is_alive: true, is_mayor: false },
      { id: 'u3', username: 'Charlie', is_alive: true, is_mayor: false },
      { id: 'u4', username: 'Dead Dave', is_alive: false, is_mayor: false },
    ],
    descriptions: { u1: 'big place', u2: 'worship' } as Record<string, string>,
    descriptionOrder: [
      { user_id: 'u1', username: 'Alice' },
      { user_id: 'u2', username: 'Bob' },
    ],
    isAlive: true,
    hasVoted: false,
    selectedVote: null as string | null,
    votedPlayers: [] as string[],
    currentUserId: 'u1',
    onSelectPlayer: vi.fn(),
    onConfirmVote: vi.fn(),
  }

  const candidateButtons = () => screen.queryAllByRole('button', { name: /game\.undercover\.voteFor/ })

  it('heads the phase with "Discuss and vote"', () => {
    render(<VotingPhase {...defaultProps} />)
    expect(screen.getByRole('heading', { name: 'game.undercover.discussAndVote' })).toBeInTheDocument()
  })

  it('recalls what everyone wrote', () => {
    render(<VotingPhase {...defaultProps} />)
    expect(screen.getByText('big place')).toBeInTheDocument()
    expect(screen.getByText('worship')).toBeInTheDocument()
  })

  it('offers every living player but you as a candidate', () => {
    render(<VotingPhase {...defaultProps} />)
    const buttons = candidateButtons()
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveTextContent('Bob')
    expect(buttons[1]).toHaveTextContent('Charlie')
  })

  it('selects a candidate on click', () => {
    const onSelectPlayer = vi.fn()
    render(<VotingPhase {...defaultProps} onSelectPlayer={onSelectPlayer} />)
    fireEvent.click(candidateButtons()[0])
    expect(onSelectPlayer).toHaveBeenCalledWith('u2')
  })

  it('marks the chosen candidate as pressed', () => {
    render(<VotingPhase {...defaultProps} selectedVote="u2" />)
    expect(candidateButtons()[0]).toHaveAttribute('aria-pressed', 'true')
    expect(candidateButtons()[1]).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows the Mayor next to their name', () => {
    render(
      <VotingPhase
        {...defaultProps}
        players={[
          { id: 'u1', username: 'Alice', is_alive: true, is_mayor: false },
          { id: 'u2', username: 'Bob', is_alive: true, is_mayor: true },
        ]}
      />,
    )
    expect(candidateButtons()[0]).toHaveTextContent('game.undercover.mayorLabel')
  })

  it('keeps "Vote to eliminate" disabled until a name is chosen, and says why', () => {
    render(<VotingPhase {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'game.undercover.voteToEliminate' })).toBeDisabled()
    expect(screen.getByText('game.undercover.chooseFirst')).toBeInTheDocument()
  })

  it('confirms the vote once a name is chosen', () => {
    const onConfirmVote = vi.fn()
    render(<VotingPhase {...defaultProps} selectedVote="u2" onConfirmVote={onConfirmVote} />)
    fireEvent.click(screen.getByRole('button', { name: 'game.undercover.voteToEliminate' }))
    expect(onConfirmVote).toHaveBeenCalledOnce()
  })

  it('after voting: says for whom, then exactly one "waiting" line, and no candidates', () => {
    render(<VotingPhase {...defaultProps} hasVoted={true} selectedVote="u2" votedPlayers={['u1']} />)
    expect(screen.getByText('game.undercover.votedFor')).toBeInTheDocument()
    expect(screen.getAllByText('game.undercover.waitingForVotes')).toHaveLength(1)
    expect(candidateButtons()).toHaveLength(0)
  })

  it('an eliminated player sees the notice, never the candidates', () => {
    render(<VotingPhase {...defaultProps} isAlive={false} />)
    expect(screen.getByTestId('you-are-eliminated')).toHaveTextContent('game.undercover.youAreDead')
    expect(candidateButtons()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'game.undercover.voteToEliminate' })).not.toBeInTheDocument()
  })

  it('a spectator watches: no candidates, no "eliminated" notice', () => {
    render(<VotingPhase {...defaultProps} isAlive={true} isSpectator={true} currentUserId="s1" />)
    expect(candidateButtons()).toHaveLength(0)
    expect(screen.queryByTestId('you-are-eliminated')).not.toBeInTheDocument()
    expect(screen.getByText('game.undercover.spectatorVoting')).toBeInTheDocument()
  })

  it('asks only those who can still vote to choose a name', () => {
    const { rerender } = render(<VotingPhase {...defaultProps} />)
    expect(screen.getByText('game.undercover.selectPlayerToVote')).toBeInTheDocument()
    rerender(<VotingPhase {...defaultProps} isAlive={false} />)
    expect(screen.queryByText('game.undercover.selectPlayerToVote')).not.toBeInTheDocument()
    rerender(<VotingPhase {...defaultProps} isSpectator={true} currentUserId="s1" />)
    expect(screen.queryByText('game.undercover.selectPlayerToVote')).not.toBeInTheDocument()
    rerender(<VotingPhase {...defaultProps} hasVoted={true} votedPlayers={['u1']} />)
    expect(screen.queryByText('game.undercover.selectPlayerToVote')).not.toBeInTheDocument()
  })

  it('counts the votes among the living, never naming a target', () => {
    render(<VotingPhase {...defaultProps} votedPlayers={['u2', 'u3']} />)
    expect(screen.getByText('game.undercover.votesCast')).toBeInTheDocument()
  })

  it('lists the table once: the seats themselves are the candidates (no second grid)', () => {
    render(<VotingPhase {...defaultProps} eliminated={[{ user_id: 'u4', role: 'undercover' }]} />)
    expect(screen.getAllByRole('list')).toHaveLength(1)
    const list = screen.getByRole('list', { name: 'game.undercover.descriptionOrder' })
    // every seat once: you, the two candidates, and the emptied seat with its role
    expect(list.querySelectorAll('li')).toHaveLength(4)
    expect(list).toHaveTextContent('game.eliminated · games.undercover.roles.undercover')
  })

  it('says on each living seat whether it has voted, never for whom', () => {
    render(<VotingPhase {...defaultProps} hasVoted selectedVote="u2" votedPlayers={['u1', 'u3']} />)
    const list = screen.getByRole('list', { name: 'game.undercover.descriptionOrder' })
    expect(list.querySelectorAll('li')[0]).toHaveTextContent('game.undercover.hasVoted')
    expect(list.querySelectorAll('li')[1]).toHaveTextContent('game.undercover.notVotedYet')
  })
})
