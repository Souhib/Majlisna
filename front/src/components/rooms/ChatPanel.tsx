import { ChevronDown, MessageCircle, Send } from "lucide-react"
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getMessagesApiV1RoomsRoomIdMessagesGet, sendMessageApiV1RoomsRoomIdMessagesPost } from "@/api/generated"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/chip"
import { Input } from "@/components/ui/field"
import { Panel } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { roomErrorMessage } from "./errors"

export interface ChatMessage {
  id: string
  room_id: string
  user_id: string
  username: string
  message: string
  created_at: string
}

interface ChatPanelProps {
  roomId: string
  currentUserId: string
  incomingMessage: ChatMessage | null
  className?: string
}

/**
 * The lobby's chat: a hairline panel whose header opens and closes it (open by default).
 * The history loads once over REST; new lines arrive from Socket.IO through
 * `incomingMessage`. Your own lines sit at the inline end on a brass tint (what is
 * yours), everyone else's at the start under their name. Messages keep their own
 * direction (`dir="auto"`), so Arabic reads right to left in an English room.
 */
export function ChatPanel({ roomId, currentUserId, incomingMessage, className }: ChatPanelProps) {
  const { t } = useTranslation()
  const uid = useId()
  const bodyId = `${uid}-body`
  const [isOpen, setIsOpen] = useState(true)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const isOpenRef = useRef(isOpen)
  const loadedRef = useRef(false)

  isOpenRef.current = isOpen

  const scrollToBottom = useCallback(() => {
    const container = messagesContainerRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, [])

  // Load initial messages once
  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    const loadMessages = async () => {
      try {
        const initialMessages = (await getMessagesApiV1RoomsRoomIdMessagesGet({ room_id: roomId }, { limit: 50 })) as ChatMessage[]
        // a line pushed over the socket while the history loaded must not be lost
        setMessages((live) => [...initialMessages, ...live.filter((m) => !initialMessages.some((h) => h.id === m.id))])
        setTimeout(scrollToBottom, 50)
      } catch {
        // The history is a courtesy: the live chat works without it.
      }
    }
    loadMessages()
  }, [roomId, scrollToBottom])

  // Handle incoming Socket.IO messages
  useEffect(() => {
    if (!incomingMessage) return
    setMessages((prev) => {
      if (prev.some((m) => m.id === incomingMessage.id)) return prev
      return [...prev, incomingMessage]
    })
    if (!isOpenRef.current) {
      setUnreadCount((prev) => prev + 1)
    }
    setTimeout(scrollToBottom, 50)
  }, [incomingMessage, scrollToBottom])

  useEffect(() => {
    if (isOpen) {
      setUnreadCount(0)
      setTimeout(scrollToBottom, 100)
    }
  }, [isOpen, scrollToBottom])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    const trimmed = newMessage.trim()
    if (!trimmed || isSending) return
    setIsSending(true)
    try {
      await sendMessageApiV1RoomsRoomIdMessagesPost({ room_id: roomId }, { message: trimmed })
      setNewMessage("")
    } catch (err) {
      toast.error(roomErrorMessage(err, t("chat.sendFailed")))
    } finally {
      setIsSending(false)
    }
  }

  return (
    <Panel flush className={cn("overflow-hidden", className)}>
      <h2 className="type-panel">
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          aria-expanded={isOpen}
          aria-controls={bodyId}
          className="flex min-h-12 w-full cursor-pointer items-center gap-3 px-4 py-3 text-start transition-colors duration-(--dur-state) hover:bg-[color-mix(in_oklch,var(--brass)_6%,transparent)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus sm:px-5"
        >
          <MessageCircle className="size-[18px] shrink-0 text-brass" aria-hidden="true" />
          <span>{t("chat.title")}</span>
          {unreadCount > 0 && (
            <Badge tone="brass">
              <span aria-hidden="true">{unreadCount > 99 ? "99+" : unreadCount}</span>
              <span className="sr-only">{t("chat.unread", { count: unreadCount })}</span>
            </Badge>
          )}
          <ChevronDown
            className={cn("ms-auto size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-state) motion-reduce:transition-none", isOpen && "rotate-180")}
            aria-hidden="true"
          />
        </button>
      </h2>

      {isOpen ? (
        <div id={bodyId} className="border-t border-line">
          <div
            ref={messagesContainerRef}
            role="log"
            aria-label={t("chat.title")}
            className="max-h-[280px] min-h-[120px] overflow-y-auto px-4 py-3 sm:px-5"
          >
            {messages.length === 0 ? (
              <p className="py-6 text-center text-[14px] leading-normal text-muted-foreground">{t("chat.noMessages")}</p>
            ) : (
              <ul className="grid gap-3">
                {messages.map((msg) => {
                  const isOwn = msg.user_id === currentUserId
                  return (
                    <li key={msg.id} className={cn("flex min-w-0 flex-col gap-1", isOwn ? "items-end" : "items-start")}>
                      {!isOwn && (
                        <span className="type-meta max-w-full truncate">
                          <bdi>{msg.username}</bdi>
                        </span>
                      )}
                      <p
                        dir="auto"
                        className={cn(
                          "max-w-[85%] rounded-sm border px-3 py-2 text-[15px] leading-normal break-words whitespace-pre-wrap text-foreground",
                          isOwn
                            ? "border-line-brass bg-[color-mix(in_oklch,var(--brass)_12%,var(--surface))]"
                            : "border-line bg-surface-2",
                        )}
                      >
                        {msg.message}
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <form onSubmit={handleSend} className="flex items-center gap-2 border-t border-line p-3">
            <Input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder={t("chat.placeholder")}
              aria-label={t("chat.placeholder")}
              maxLength={500}
              autoComplete="off"
              dir="auto"
              className="h-11 min-w-0 flex-1 text-[15px]"
            />
            <Button
              type="submit"
              size="icon"
              disabled={isSending || !newMessage.trim()}
              aria-label={t("chat.send")}
            >
              <Send className="rtl-flip" aria-hidden="true" />
            </Button>
          </form>
        </div>
      ) : null}
    </Panel>
  )
}
