import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getMessagesApiV1RoomsRoomIdMessagesGet, sendMessageApiV1RoomsRoomIdMessagesPost } from '@/api/generated'
import { ChatPanel } from './ChatPanel'

vi.mock('@/api/generated', () => ({
  getMessagesApiV1RoomsRoomIdMessagesGet: vi.fn().mockResolvedValue([]),
  sendMessageApiV1RoomsRoomIdMessagesPost: vi.fn().mockResolvedValue({}),
}))

vi.mock('@/api/client', () => ({
  getApiErrorMessage: (err: unknown) => String(err),
}))

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    roomId: 'room-1',
    currentUserId: 'user-1',
    incomingMessage: null,
    ...overrides,
  }
}

/**
 * Render the panel and let its history load settle inside act: the load resolves after
 * the first render, and asserting before it left a state update outside act (a warning
 * per test, and assertions made against a half-rendered panel).
 */
async function renderPanel(props: ReturnType<typeof defaultProps>) {
  let result!: ReturnType<typeof render>
  await act(async () => {
    result = render(<ChatPanel {...props} />)
  })
  return result
}

describe('ChatPanel', () => {
  it('renders the chat title as the toggle of an open panel', async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText('chat.title')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /chat\.title/ })).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows empty state message when no messages', async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText('chat.noMessages')).toBeInTheDocument()
  })

  it('renders the message input', async () => {
    await renderPanel(defaultProps())
    expect(screen.getByPlaceholderText('chat.placeholder')).toBeInTheDocument()
  })

  it('send button is disabled when input is empty', async () => {
    await renderPanel(defaultProps())
    expect(screen.getByRole('button', { name: 'chat.send' })).toBeDisabled()
  })

  it('sends the trimmed message and clears the field', async () => {
    // Prepare
    await renderPanel(defaultProps())
    const input = screen.getByPlaceholderText('chat.placeholder')

    // Act
    fireEvent.change(input, { target: { value: '  Salam  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'chat.send' }))

    // Assert
    await waitFor(() => expect(input).toHaveValue(''))
    expect(sendMessageApiV1RoomsRoomIdMessagesPost).toHaveBeenCalledWith({ room_id: 'room-1' }, { message: 'Salam' })
  })

  it('collapses and expands the panel', async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText('chat.noMessages')).toBeVisible()

    fireEvent.click(screen.getByText('chat.title'))
    expect(screen.queryByText('chat.noMessages')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /chat\.title/ })).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(screen.getByText('chat.title'))
    expect(screen.getByText('chat.noMessages')).toBeVisible()
  })

  it('renders incoming messages', async () => {
    const incomingMessage = {
      id: 'msg-1',
      room_id: 'room-1',
      user_id: 'user-2',
      username: 'Alice',
      message: 'Salam everyone!',
      created_at: '2026-01-01T00:00:00Z',
    }
    await renderPanel(defaultProps({ incomingMessage }))
    expect(screen.getByText('Salam everyone!')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('keeps a message that arrives while the history is loading', async () => {
    // Prepare
    const history = [{ id: 'old', room_id: 'room-1', user_id: 'user-2', username: 'Alice', message: 'Earlier', created_at: '2026-01-01T00:00:00Z' }]
    vi.mocked(getMessagesApiV1RoomsRoomIdMessagesGet).mockResolvedValueOnce(history as never)
    const incomingMessage = { ...history[0], id: 'live', message: 'Just now' }

    // Act
    await renderPanel(defaultProps({ incomingMessage }))

    // Assert
    expect(await screen.findByText('Earlier')).toBeInTheDocument()
    expect(screen.getByText('Just now')).toBeInTheDocument()
  })

  it('does not show username for own messages', async () => {
    const incomingMessage = {
      id: 'msg-1',
      room_id: 'room-1',
      user_id: 'user-1',
      username: 'Me',
      message: 'My own message',
      created_at: '2026-01-01T00:00:00Z',
    }
    await renderPanel(defaultProps({ incomingMessage }))
    expect(screen.getByText('My own message')).toBeInTheDocument()
    expect(screen.queryByText('Me')).not.toBeInTheDocument()
  })
})
