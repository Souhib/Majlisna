import { ChevronDown, ChevronUp, MessageCircle, Send } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { getMessagesApiV1RoomsRoomIdMessagesGet, sendMessageApiV1RoomsRoomIdMessagesPost } from "@/api/generated"
import { cn } from "@/lib/utils"

interface ChatMessage {
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
}

export function ChatPanel({ roomId, currentUserId }: ChatPanelProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(true)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const lastMessageIdRef = useRef<string | null>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const scrollToBottom = useCallback(() => {
    const container = messagesContainerRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, [])

  const fetchMessages = useCallback(async () => {
    try {
      const params: Record<string, string | number> = { limit: 50 }
      if (lastMessageIdRef.current) {
        params.after_id = lastMessageIdRef.current
      }
      const newMessages = await getMessagesApiV1RoomsRoomIdMessagesGet(
        { room_id: roomId },
        params as Record<string, string | number>,
      ) as ChatMessage[]
      if (newMessages.length > 0) {
        lastMessageIdRef.current = newMessages[newMessages.length - 1].id
        if (lastMessageIdRef.current && messages.length > 0) {
          setMessages((prev) => [...prev, ...newMessages])
          if (!isOpen) {
            setUnreadCount((prev) => prev + newMessages.length)
          }
        } else {
          setMessages(newMessages)
        }
        if (isOpen) {
          setTimeout(scrollToBottom, 50)
        }
      }
    } catch {
      // Silently fail on polling errors
    }
  }, [roomId, isOpen, messages.length, scrollToBottom])

  useEffect(() => {
    fetchMessages()
    pollIntervalRef.current = setInterval(fetchMessages, 2000)
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [fetchMessages])

  useEffect(() => {
    if (isOpen) {
      setUnreadCount(0)
      setTimeout(scrollToBottom, 100)
    }
  }, [isOpen, scrollToBottom])

  const handleSend = async () => {
    const trimmed = newMessage.trim()
    if (!trimmed || isSending) return
    setIsSending(true)
    try {
      await sendMessageApiV1RoomsRoomIdMessagesPost({ room_id: roomId }, { message: trimmed })
      setNewMessage("")
      await fetchMessages()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="glass rounded-2xl border border-border/30 overflow-hidden transition-all duration-300 mt-6">
      {/* Header — always visible, acts as toggle */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-muted/30 transition-colors duration-200 cursor-pointer"
      >
        <div className="flex items-center gap-2.5">
          <MessageCircle className="h-4.5 w-4.5 text-primary" />
          <span className="text-sm font-bold tracking-tight">{t("chat.title")}</span>
          {unreadCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-bold text-primary-foreground animate-scale-in">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* Collapsible body */}
      <div
        className={cn(
          "transition-all duration-300 ease-out overflow-hidden",
          isOpen ? "max-h-[400px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <div className="border-t border-border/30" />

        {/* Messages */}
        <div ref={messagesContainerRef} className="overflow-y-auto px-4 py-3 space-y-2.5" style={{ maxHeight: "280px", minHeight: "120px" }}>
          {messages.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-6">{t("chat.noMessages")}</p>
          ) : (
            messages.map((msg) => {
              const isOwn = msg.user_id === currentUserId
              return (
                <div key={msg.id} className={cn("flex flex-col", isOwn ? "items-end" : "items-start")}>
                  {!isOwn && (
                    <span className="mb-0.5 text-[10px] font-semibold text-muted-foreground">{msg.username}</span>
                  )}
                  <div
                    className={cn(
                      "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm break-words",
                      isOwn
                        ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground"
                        : "bg-muted/60",
                    )}
                  >
                    {msg.message}
                  </div>
                </div>
              )
            })
          )}
          <div />
        </div>

        {/* Input */}
        <div className="border-t border-border/30 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder={t("chat.placeholder")}
              maxLength={500}
              className="flex-1 rounded-xl border border-border/50 bg-background/80 px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30 transition-all duration-200"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={isSending || !newMessage.trim()}
              className="rounded-xl bg-gradient-to-r from-primary to-primary/90 p-2.5 text-primary-foreground shadow-sm hover:shadow-md transition-all duration-200 disabled:opacity-50 cursor-pointer"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
